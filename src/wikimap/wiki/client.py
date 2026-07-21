"""MediaWiki API access — the single entry point to Wikipedia.

Rules: namespace 0 only, filtered with `p.ns == 0` (never a colon-in-title check);
descriptive User-Agent from .env as `appname/version (contact)`; retry with a small
delay on failure. Synchronous (`wikipedia-api`) until caching proves insufficient.
"""

import os
import time

import wikipediaapi
from dotenv import load_dotenv

load_dotenv()


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
        
        # it works if it gets here
        self._wiki = wikipediaapi.Wikipedia(user_agent=user_agent, language=language) # wikipedia user shit
        self._retries = retries # set retries
        self._delay = delay # set delay

    def exists(self, title: str) -> bool:
        return self._wiki.page(title).exists()

    def get_links(self, title: str) -> list[str]:
        """Return `title`'s outbound links, restricted to article namespace (ns == 0).

        `page.links` returns {title: WikipediaPage}, with `.ns` already populated —
        filtering on it costs no extra API call. This is the fix for the old repo's
        `if ':' not in title` check, which silently dropped real articles whose
        titles happen to contain a colon (e.g. "Aliens: The Ride").

        Retries on transient API failures; returns [] once retries are exhausted.
        """
        for attempt in range(1, self._retries + 1):
            try:
                page = self._wiki.page(title)
                return [t for t, p in page.links.items() if p.ns == 0]
            except Exception:
                if attempt == self._retries:
                    return []
                time.sleep(self._delay)
        return []
