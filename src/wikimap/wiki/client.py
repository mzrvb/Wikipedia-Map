"""MediaWiki API access — the single entry point to Wikipedia.

Rules: namespace 0 only, filtered with `p.ns == 0` (never a colon-in-title check);
descriptive User-Agent from .env as `appname/version (contact)`; retry with a small
delay on failure. Synchronous (`wikipedia-api`) until caching proves insufficient.

Outbound links go through `wikipedia-api`. Backlinks do NOT — see `get_backlinks`
for why the library's version is unusable here. Both still live in this one class,
so the rule "nothing else talks to Wikipedia directly" is intact.
"""

import logging
import os
import time

import requests
import wikipediaapi
from dotenv import load_dotenv

from wikimap.config import BACKLINK_LIMIT

load_dotenv()

logger = logging.getLogger(__name__)

# Per-request page cap the MediaWiki API enforces on list=backlinks.
_API_MAX_PER_REQUEST = 500


class WikiClient:
    """Thin wrapper around wikipedia-api. Nothing else in the codebase should
    import wikipediaapi directly — everything goes through here.
    """

    def __init__(self, language: str = "en", retries: int = 3, delay: float = 2.0) -> None:
        user_agent = os.getenv("USER_AGENT")
        if not user_agent:
            raise RuntimeError(
                "USER_AGENT is not set. Copy .env.example to .env and fill it in — "
                "Wikimedia throttles or blocks generic user agents at volume."
            )

        self._wiki = wikipediaapi.Wikipedia(user_agent=user_agent, language=language)
        self._retries = retries
        self._delay = delay
        # Kept for the raw backlinks query below, which doesn't go through wikipediaapi
        # and so has to set its own headers.
        self._user_agent = user_agent
        self._api_url = f"https://{language}.wikipedia.org/w/api.php"

    def exists(self, title: str) -> bool:
        return self._wiki.page(title).exists()

    def get_links(self, title: str) -> list[str]:
        """Return `title`'s outbound links, restricted to article namespace (ns == 0).

        `page.links` returns {title: WikipediaPage}, with `.ns` already populated —
        filtering on it costs no extra API call. This is the fix for the old repo's
        `if ':' not in title` check, which silently dropped real articles whose
        titles happen to contain a colon (e.g. "Aliens: The Ride").

        Retries on transient API failures; returns [] once retries are exhausted —
        but LOGS first. See the note on the except block below.
        """
        for attempt in range(1, self._retries + 1):
            try:
                page = self._wiki.page(title)
                return [t for t, p in page.links.items() if p.ns == 0]
            except Exception:
                # Deliberately broad (a timeout, a 429, a malformed payload all mean
                # "retry"), which also means it catches OUR bugs — an AttributeError
                # from a typo would be swallowed and returned as []. And [] is
                # indistinguishable from "this page genuinely has no links", so the
                # search would just quietly find nothing. The log is what keeps a
                # programming error from masquerading as a data answer.
                logger.warning(
                    "get_links(%r) attempt %d/%d failed",
                    title,
                    attempt,
                    self._retries,
                    exc_info=True,
                )
                if attempt == self._retries:
                    return []
                time.sleep(self._delay)
        return []

    def get_summary(self, title: str) -> dict | None:
        """Return {"summary": ..., "url": ...} for `title`, or None if it doesn't exist
        or every retry failed — the same collapsed-together contract as get_links'
        [] (see its docstring): a real bug and "not found" both come back falsy, and
        the log is what tells them apart.

        One page object (self._wiki.page(title)), read once — .summary and .fullurl
        are both attributes of it, so there's no reason to fetch the page twice.
        """
        for attempt in range(1, self._retries + 1):
            try:
                page = self._wiki.page(title)
                summary = page.summary
                if not page.exists():
                    return None
                return {"summary": summary, "url": page.fullurl}
            except Exception:
                logger.warning(
                    "get_summary(%r) attempt %d/%d failed",
                    title,
                    attempt,
                    self._retries,
                    exc_info=True,
                )
                if attempt == self._retries:
                    return None
                time.sleep(self._delay)
        return None

    def get_backlinks(self, title: str, limit: int = BACKLINK_LIMIT) -> list[str]:
        """Return pages that link TO `title` (ns0 only), capped at `limit`.

        This is the reverse direction of `get_links`, and it exists for bidirectional
        Connect search: walking forward from the seed and backward from the target
        turns a K^L search into roughly 2 * K^(L/2).

        Why this bypasses wikipedia-api. The library exposes `page.backlinks`, but it
        is unusable at our scale for two reasons, both read out of its source:

        1. It paginates to exhaustion — a `while "continue" in raw` loop with no cap.
           "Cat" has six figures of backlinks, so one property access becomes hundreds
           of requests and minutes of hanging. There is no public way to stop it early.
        2. Its continuation requests are built from the *original* params dict, so any
           kwargs you pass (like `blnamespace=0`) are silently dropped after the first
           page — you would get ns0 results followed by unfiltered ones.

        So the query is issued directly here instead: capped, and with `blnamespace=0`
        re-sent on every continuation. That keeps namespace filtering server-side,
        which is cheaper than fetching everything and filtering locally. This is still
        the only class talking to Wikipedia, so the data-layer rule holds — and CLAUDE.md
        already names the raw MediaWiki API as the documented upgrade path.

        Retries on transient failures; returns [] once retries are exhausted, matching
        `get_links` rather than raising into the middle of a search.
        """
        base_params = {
            "action": "query",
            "list": "backlinks",
            "bltitle": title,
            "blnamespace": 0,  # ns0 server-side — the same rule as get_links' p.ns == 0
            "bllimit": min(limit, _API_MAX_PER_REQUEST),
            "format": "json",
            "formatversion": 2,
        }

        for attempt in range(1, self._retries + 1):
            try:
                titles: list[str] = []
                params = dict(base_params)
                while len(titles) < limit:
                    response = requests.get(
                        self._api_url,
                        params=params,
                        headers={"User-Agent": self._user_agent},
                        timeout=30,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    titles.extend(
                        entry["title"]
                        for entry in payload.get("query", {}).get("backlinks", [])
                    )
                    token = payload.get("continue", {}).get("blcontinue")
                    if not token:
                        break
                    # Rebuilt from base_params, not mutated in place — this is exactly
                    # the bug noted above, and rebuilding is what avoids it.
                    params = dict(base_params, blcontinue=token)
                return titles[:limit]
            except Exception:
                # Same reasoning as get_links: broad on purpose, logged so our own
                # bugs can't hide inside an empty result.
                logger.warning(
                    "get_backlinks(%r) attempt %d/%d failed",
                    title,
                    attempt,
                    self._retries,
                    exc_info=True,
                )
                if attempt == self._retries:
                    return []
                time.sleep(self._delay)
        return []
