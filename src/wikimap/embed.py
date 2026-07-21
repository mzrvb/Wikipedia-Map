"""Page-title embeddings and cosine similarity.

Powers both the top-K branching cap (decision C) and feedback's distance estimate
(decision B). Two-layer cached (memory -> disk) keyed by page title: embedding
~300 links per node is the dominant cost, so pay it once per page.

Layering mirrors wiki/: `Embedder` is the ONLY importer of sentence_transformers
(like WikiClient is the only importer of wikipediaapi), and `EmbeddingCache` wraps
it with the same memory -> disk -> compute lookup chain as wiki/cache.py's LinkCache.
"""

import json
from pathlib import Path
from urllib.parse import quote

import numpy as np

from wikimap.config import EMBEDDING_MODEL

DEFAULT_DATA_DIR = Path("data/embeddings")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine of the angle between two embedding vectors, in [-1, 1].

    Pure math, no state — so a module-level function, not a method. 1.0 means
    identical direction (maximally similar), 0.0 orthogonal (unrelated). This is
    the semantic "distance to target" that decisions B and C are both built on.
    """
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class Embedder:
    """Thin wrapper around a SentenceTransformer model. The only thing in the
    codebase that imports sentence_transformers directly.

    The model is loaded lazily on first embed() — importing this module (and the
    ~80MB model download) shouldn't happen just because something imported embed.py.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL) -> None:
        self._model_name = model_name
        self._model = None  # loaded on first use — see _get_model

    def _get_model(self):
        if self._model is None:
            # Imported here, not at module top, so the heavy dependency only loads
            # when an embedding is actually needed (same lazy spirit as page.links).
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, title: str) -> np.ndarray:
        """Embed a single page title into a dense vector."""
        return self._get_model().encode(title)


class EmbeddingCache:
    """Two-layer cache in front of Embedder.embed, keyed by page title.

    Checked in order: in-memory dict -> disk (one JSON file per title) -> compute.
    Computing an embedding is the expensive step here (the model forward pass),
    playing the same role the network call plays in LinkCache. A cache miss writes
    to both layers so the next call — even after a restart — skips the model.
    """

    def __init__(
        self, embedder: Embedder, data_dir: Path | str = DEFAULT_DATA_DIR
    ) -> None:
        self._embedder = embedder
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, np.ndarray] = {}

    def embed(self, title: str) -> np.ndarray:
        if title in self._memory:
            return self._memory[title]

        path = self._path_for(title)
        if path.exists():
            vector = np.array(json.loads(path.read_text(encoding="utf-8")))
            self._memory[title] = vector
            return vector

        vector = self._embedder.embed(title)
        self._memory[title] = vector
        # JSON can't serialize a numpy array directly — .tolist() drops it to plain
        # Python floats, which json.dumps handles. np.array() reverses it on read.
        path.write_text(json.dumps(vector.tolist()), encoding="utf-8")
        return vector

    def similarity(self, title_a: str, title_b: str) -> float:
        """Cosine similarity between two page titles, using cached embeddings."""
        return cosine_similarity(self.embed(title_a), self.embed(title_b))

    def _path_for(self, title: str) -> Path:
        # Same filesystem-safe encoding as wiki/cache.py: quote() escapes /, :, ?
        # etc. so titles like "Aliens: The Ride" become valid filenames.
        return self._data_dir / f"{quote(title, safe='')}.json"
