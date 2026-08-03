"""Turn raw Wikipedia article HTML into browser-safe HTML for Connect's human-play
mode: every real move stays clickable, everything else goes inert.

Deliberately separate from client.py even though it's Wikipedia-shaped data,
because this module never talks to Wikipedia — it only rewrites a string
`WikiClient.get_article_html` already fetched. The "is this link real" question
is answered by a LOOKUP against `LinkCache.get_links(title)` (the same ns0-
filtered list every algorithm already trusts), never by inspecting the href or
title text itself — that would be the exact colon-in-title mistake CLAUDE.md's
Wikipedia data layer rules already warn against, just relocated into a regex.
"""

from __future__ import annotations

import html as html_lib
from html.parser import HTMLParser
from urllib.parse import unquote

# Tags whose entire contents get dropped, not just the tag itself — MediaWiki's
# own parser output doesn't include <script> (its Sanitizer strips it server-side
# before this HTML ever reaches us), so this is belt-and-suspenders, not the
# primary defense.
_STRIPPED_TAGS = frozenset({"script", "style"})


def _title_from_href(href: str) -> str | None:
    """`/wiki/Cat_(disambiguation)` -> "Cat (disambiguation)".

    None for anything that isn't a plain internal wiki link — an external URL, a
    same-page `#section` anchor, a `/w/index.php?...` edit/history link. None of
    those can ever be a real move, whatever LinkCache says, so they're rejected
    here before a lookup is even attempted.
    """
    if not href.startswith("/wiki/"):
        return None
    path = href[len("/wiki/") :].split("#", 1)[0]
    if not path:
        return None
    return unquote(path).replace("_", " ")


class _LinkAnnotator(HTMLParser):
    """Rewrites every `<a>` tag; everything else passes through byte-for-byte.

    A real link becomes `<a class="wm-link" data-title="...">` (href stripped to
    `#` — navigation is the frontend's job, triggered off `data-title`, never a
    real browser page load). Anything else becomes `<a class="wm-disabled">`,
    with its href removed entirely so it cannot navigate anywhere.
    """

    def __init__(self, real_links: set[str]) -> None:
        super().__init__(convert_charrefs=True)
        self._real_links = real_links
        self._skip_depth = 0
        self.output: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _STRIPPED_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag != "a":
            self.output.append(self.get_starttag_text() or "")
            return

        href = next((value for name, value in attrs if name == "href" and value), "")
        title = _title_from_href(href)
        if title is not None and title in self._real_links:
            escaped = html_lib.escape(title, quote=True)
            self.output.append(f'<a href="#" class="wm-link" data-title="{escaped}">')
        else:
            self.output.append('<a class="wm-disabled">')

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # Base HTMLParser's default handle_startendtag calls handle_starttag THEN
        # handle_endtag for a self-closed tag like `<br />`. Only the starttag
        # half is wanted here — voidelements never had a real closing tag in the
        # source, so synthesizing one would emit a spurious `</br>`.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _STRIPPED_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        # Re-escape: convert_charrefs=True already decoded entities like &amp;
        # into plain text, so this text is about to be spliced back into an HTML
        # string that will be parsed again by the browser — an un-escaped "&" or
        # "<" that came from decoded source would corrupt (or, worse, could be
        # exploited in) that second parse.
        self.output.append(html_lib.escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        pass  # dropped entirely — no reason to ship HTML comments to the browser


def annotate_links(html: str, real_links: set[str]) -> str:
    """Rewrite `html` (as returned by `WikiClient.get_article_html`) so every
    real (ns0) link is clickable and everything else is inert. See
    `_LinkAnnotator` for the rewrite rules.
    """
    parser = _LinkAnnotator(real_links)
    parser.feed(html)
    parser.close()
    return "".join(parser.output)
