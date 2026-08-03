"""Grade boundaries for MoveEvaluation (contract 3).

All fast: fake caches supply canned links and similarity scores, same pattern
test_default.py uses, so no network and no model ever load.
"""

from wikimap.feedback import evaluate_move
from wikimap.graph.contracts import Grade


class _FakeLinkCache:
    def __init__(self, links: dict[str, list[str]]):
        self._links = links

    def get_links(self, title: str) -> list[str]:
        return self._links.get(title, [])


class _FakeEmbedCache:
    """`similarity(x, y)` ignores `y` and looks `x` up in a title -> score table.
    A page is maximally similar to itself."""

    def __init__(self, scores: dict[str, float]):
        self._scores = scores

    def similarity(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        return self._scores.get(a, 0.0)

    def similarity_many(self, titles: list[str], anchor: str) -> dict[str, float]:
        return {title: self.similarity(title, anchor) for title in titles}


class TestReachingTheTarget:
    def test_moving_directly_to_the_target_is_always_brilliant(self):
        # "Target" would rank last by score here if it were graded by rank at all —
        # proving Brilliant is a special case, not just "happened to rank first."
        links = {"Seed": ["Target", "Other"]}
        scores = {"Seed": 0.1, "Target": 0.0, "Other": 0.9}
        link_cache = _FakeLinkCache(links)
        embed_cache = _FakeEmbedCache(scores)

        result = evaluate_move("Seed", "Target", "Target", link_cache, embed_cache)

        assert result.grade == Grade.BRILLIANT
        assert result.delta == 1.0 - 0.1  # similarity(Target, Target)=1.0 - similarity(Seed, Target)


class TestRankBasedGrading:
    def test_the_top_ranked_available_link_is_best(self):
        links = {"Seed": ["A", "B", "C", "D"]}
        scores = {"Seed": 0.1, "A": 0.9, "B": 0.7, "C": 0.5, "D": 0.2}
        link_cache = _FakeLinkCache(links)
        embed_cache = _FakeEmbedCache(scores)

        result = evaluate_move("Seed", "A", "Target", link_cache, embed_cache)

        assert result.grade == Grade.BEST
        assert result.delta == 0.9 - 0.1

    def test_the_worst_ranked_available_link_is_a_blunder(self):
        links = {"Seed": ["A", "B", "C", "D"]}
        scores = {"Seed": 0.1, "A": 0.9, "B": 0.7, "C": 0.5, "D": 0.2}
        link_cache = _FakeLinkCache(links)
        embed_cache = _FakeEmbedCache(scores)

        result = evaluate_move("Seed", "D", "Target", link_cache, embed_cache)

        assert result.grade == Grade.BLUNDER

    def test_grading_is_relative_to_this_pages_options_not_an_absolute_score(self):
        """The same raw similarity score (0.5) is Best on one page (nothing better
        was on offer) and a Blunder on another (four better options existed) —
        pinning down that grading can't be a fixed threshold on the score alone."""
        link_cache = _FakeLinkCache({"Weak": ["A"], "Strong": ["A", "B", "C", "D", "E"]})
        embed_cache = _FakeEmbedCache(
            {"Weak": 0.1, "Strong": 0.1, "A": 0.5, "B": 0.9, "C": 0.8, "D": 0.7, "E": 0.6}
        )

        weak_page_result = evaluate_move("Weak", "A", "Target", link_cache, embed_cache)
        strong_page_result = evaluate_move("Strong", "A", "Target", link_cache, embed_cache)

        assert weak_page_result.grade == Grade.BEST
        assert strong_page_result.grade == Grade.BLUNDER

    def test_a_middling_rank_lands_in_between(self):
        links = {"Seed": [f"P{i}" for i in range(9)]}  # 9 options, ranks 0..8
        scores = {"Seed": 0.0, **{f"P{i}": 1.0 - i / 10 for i in range(9)}}
        link_cache = _FakeLinkCache(links)
        embed_cache = _FakeEmbedCache(scores)

        # Rank 4 of 8 -> percentile 0.5, right at the inaccuracy/mistake boundary.
        result = evaluate_move("Seed", "P4", "Target", link_cache, embed_cache)

        assert result.grade == Grade.INACCURACY

    def test_note_reports_the_rank_out_of_the_available_count(self):
        links = {"Seed": ["A", "B"]}
        scores = {"Seed": 0.0, "A": 0.9, "B": 0.1}
        link_cache = _FakeLinkCache(links)
        embed_cache = _FakeEmbedCache(scores)

        result = evaluate_move("Seed", "B", "Target", link_cache, embed_cache)

        assert "2 of 2" in result.note
