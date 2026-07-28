"""Two-layer cache: in-memory dict -> disk (data/) -> network.

Checked in that order; a network fetch writes to BOTH layers. Must be disk-backed
or every launch re-crawls from cold. No TTL for now — staleness is accepted.

Caches both directions of the link graph: outbound links (`get_links`) and inbound
ones (`get_backlinks`, for bidirectional Connect search). They are the same lookup
shape over different data, so they share `_lookup` and differ only in which client
method they call and which directory they persist to. Deliberately one class rather
than two: algorithms receive a single cache object, so adding the reverse direction
did not change `ConnectAlgorithm.__init__`.
"""

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from wikimap.wiki.client import WikiClient

# Anchored to the project root, NOT left as a relative path. `Path("data/links")`
# resolves against whatever directory the process happened to be launched from, so
# starting uvicorn from anywhere but the repo root would silently miss the warm cache,
# re-crawl every page from cold, and scatter a stray `data/` folder wherever you stood.
# A cache whose location depends on your shell's cwd is not a cache.
#
# parents[] walks up from this file: [0] wiki/ -> [1] wikimap/ -> [2] src/ -> [3] root.
# Correct for the editable install this project uses (`pip install -e .`), where the
# source tree IS the installed package. Revisit if it is ever installed non-editably
# or containerised — at that point this should become an env var / settings value.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = _PROJECT_ROOT / "data" / "links"
DEFAULT_BACKLINK_DIR = _PROJECT_ROOT / "data" / "backlinks"


class LinkCache:
    """Two-layer cache in front of WikiClient's link lookups.

    Checked in order: in-memory dict -> disk (one JSON file per title) -> network.
    A network fetch writes to both layers, so the *next* call for the same title —
    even after a restart, since the disk layer persists — never touches the network.

    Forward and backward links are cached in separate directories. They must never
    share a namespace: both are "a list of titles related to X", so a collision
    would return backlinks where links were asked for, silently and plausibly.
    """

    def __init__(
        self,
        client: WikiClient,
        data_dir: Path | str = DEFAULT_DATA_DIR,
        backlink_dir: Path | str = DEFAULT_BACKLINK_DIR,
    ) -> None:
        self._client = client
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._backlink_dir = Path(backlink_dir)
        self._backlink_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, list[str]] = {}
        self._backlink_memory: dict[str, list[str]] = {}

    def get_links(self, title: str) -> list[str]:
        """Pages `title` links out to (ns0 only)."""
        return self._lookup(
            title, self._memory, self._data_dir, self._client.get_links
        )

    def get_backlinks(self, title: str) -> list[str]:
        """Pages that link in to `title` (ns0 only, capped by config.BACKLINK_LIMIT).

        The backward half of a bidirectional search. Note the cached list is a
        *capped* sample, not the complete backlink set — see the client for why.
        """
        return self._lookup(
            title, self._backlink_memory, self._backlink_dir, self._client.get_backlinks
        )

    def _lookup(
        self,
        title: str,
        memory: dict[str, list[str]],
        directory: Path,
        fetch: Callable[[str], list[str]],
    ) -> list[str]:
        """The memory -> disk -> network chain, once, for either direction.

        `fetch` is the network fallback — passing the bound method in rather than
        branching on a direction flag keeps the chain itself direction-agnostic.
        """
        if title in memory:
            return memory[title]

        path = self._path_for(directory, title)
        if path.exists():
            titles = json.loads(path.read_text(encoding="utf-8"))
            memory[title] = titles
            return titles

        titles = fetch(title)
        memory[title] = titles
        path.write_text(json.dumps(titles), encoding="utf-8")
        return titles

    @staticmethod
    def _path_for(directory: Path, title: str) -> Path:
        # quote() escapes filesystem-unsafe characters (/, :, ?, ...) that show up
        # in real titles ("Aliens: The Ride"), while staying legible on disk.
        return directory / f"{quote(title, safe='')}.json"
