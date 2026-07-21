"""Embeddings + cosine similarity (roadmap step 2).

Two layers of testing, mirroring test_wiki_client.py:
  - Fast, mocked: cosine math on hand-made vectors, and the two-layer cache
    behavior (memory hit, disk-survives-restart) using a fake embedder.
  - Slow, real model (`@pytest.mark.slow`): the brief's actual proof that related
    pages score higher than unrelated ones. Skipped unless run explicitly, since
    it downloads ~80MB on first run.
"""

import json

import numpy as np
import pytest

from wikimap.embed import EmbeddingCache, cosine_similarity


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        v = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector_does_not_divide_by_zero(self):
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 1.0])
        assert cosine_similarity(a, b) == 0.0


class _FakeEmbedder:
    """Stand-in for Embedder: returns a fixed vector per title and counts calls,
    so tests can prove the cache short-circuits before reaching the model."""

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = vectors
        self.calls: list[str] = []

    def embed(self, title: str) -> np.ndarray:
        self.calls.append(title)
        return np.array(self._vectors[title])


class TestEmbeddingCache:
    def test_second_call_hits_memory_not_model(self, tmp_path):
        embedder = _FakeEmbedder({"Page": [1.0, 0.0, 0.0]})
        cache = EmbeddingCache(embedder, data_dir=tmp_path)

        first = cache.embed("Page")
        second = cache.embed("Page")

        assert np.array_equal(first, second)
        assert embedder.calls == ["Page"]  # model touched exactly once

    def test_cache_survives_restart_via_disk(self, tmp_path):
        warm = _FakeEmbedder({"Page": [0.1, 0.2, 0.3]})
        EmbeddingCache(warm, data_dir=tmp_path).embed("Page")

        # Fresh instance, same dir, empty memory, an embedder that errors if called.
        cold = _FakeEmbedder({})
        cold_cache = EmbeddingCache(cold, data_dir=tmp_path)

        restored = cold_cache.embed("Page")
        assert restored == pytest.approx([0.1, 0.2, 0.3])
        assert cold.calls == []  # served from disk, model never ran

    def test_writes_json_to_disk(self, tmp_path):
        embedder = _FakeEmbedder({"Aliens: The Ride": [1.0, 2.0]})
        cache = EmbeddingCache(embedder, data_dir=tmp_path)

        cache.embed("Aliens: The Ride")

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert json.loads(files[0].read_text()) == [1.0, 2.0]

    def test_similarity_uses_cached_embeddings(self, tmp_path):
        # Two identical vectors -> similarity 1.0, and each title embedded once.
        embedder = _FakeEmbedder({"A": [1.0, 1.0], "B": [1.0, 1.0]})
        cache = EmbeddingCache(embedder, data_dir=tmp_path)

        assert cache.similarity("A", "B") == pytest.approx(1.0)
        assert sorted(embedder.calls) == ["A", "B"]


@pytest.mark.slow
class TestRealModel:
    """The brief's proof: related pages score higher than unrelated ones.
    Uses the real model — run with `pytest -m slow` (downloads ~80MB first time)."""

    def test_related_pages_score_higher_than_unrelated(self, tmp_path):
        from wikimap.embed import Embedder

        cache = EmbeddingCache(Embedder(), data_dir=tmp_path)

        related = cache.similarity(
            "Python (programming language)", "Programming language"
        )
        unrelated = cache.similarity("Python (programming language)", "Banana")

        assert related > unrelated
