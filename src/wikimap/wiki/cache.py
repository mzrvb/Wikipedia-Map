"""Two-layer cache: in-memory dict -> disk (data/) -> network.

Checked in that order; a network fetch writes to BOTH layers. Must be disk-backed
or every launch re-crawls from cold. No TTL for now — staleness is accepted.
"""

import json
from pathlib import Path
from urllib.parse import quote

from wikimap.wiki.client import WikiClient

DEFAULT_DATA_DIR = Path("data/links")


class LinkCache:
    """Two-layer cache in front of WikiClient.get_links.

    Checked in order: in-memory dict -> disk (one JSON file per title) -> network.
    A network fetch writes to both layers, so the *next* call for the same title —
    even after a restart, since the disk layer persists — never touches the network.
    """

    def __init__(self, client: WikiClient, data_dir: Path | str = DEFAULT_DATA_DIR) -> None:
        self._client = client
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, list[str]] = {}

    def get_links(self, title: str) -> list[str]:
        if title in self._memory:
            return self._memory[title]

        path = self._path_for(title)
        if path.exists():
            links = json.loads(path.read_text(encoding="utf-8"))
            self._memory[title] = links
            return links

        links = self._client.get_links(title)
        self._memory[title] = links
        path.write_text(json.dumps(links), encoding="utf-8")
        return links

    def _path_for(self, title: str) -> Path:
        # quote() escapes filesystem-unsafe characters (/, :, ?, ...) that show up
        # in real titles ("Aliens: The Ride"), while staying legible on disk.
        return self._data_dir / f"{quote(title, safe='')}.json"
