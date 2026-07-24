"""Greedy Connect search (roadmap step 4).

All fast: fake caches supply canned links and canned similarity scores, so no
network and no model ever load. The fakes let each test hand-build a toy link graph
and dictate exactly which neighbour looks "closest to target", which is the only
thing greedy's behaviour turns on.
"""

import pytest

from wikimap import config
from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.algorithms.connect.greedy import GreedyConnect
from wikimap.graph.contracts import Edge, Node, Step


class _FakeLinkCache:
    """Stand-in for LinkCache: returns the canned link list for a title (or [])."""

    def __init__(self, links: dict[str, list[str]]):
        self._links = links

    def get_links(self, title: str) -> list[str]:
        return self._links.get(title, [])


class _FakeEmbedCache:
    """Stand-in for EmbeddingCache: `similarity(x, target)` is looked up from a
    title -> score table. A page is maximally similar to itself (so a link that IS
    the target always scores highest and gets picked), else 0.0 if unlisted."""

    def __init__(self, scores: dict[str, float]):
        self._scores = scores

    def similarity(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        return self._scores.get(a, 0.0)


def _run(links, scores, seed, target) -> list[Step]:
    algo = GreedyConnect(_FakeLinkCache(links), _FakeEmbedCache(scores))
    return list(algo.run(seed, target))


def _move_sources(steps: list[Step]) -> list[str]:
    """The `current` page at each move tick = the shared source of that step's edges.
    The seed/start step and a cap step have no edges, so they're skipped."""
    return [step.edges[0].source for step in steps if step.edges]


class TestReachesTarget:
    def test_reaches_target_on_toy_graph(self):
        # A -> B -> D(target). C is a lower-scoring distraction off A.
        links = {"A": ["B", "C"], "B": ["D", "A"], "C": ["A"]}
        scores = {"A": 0.1, "B": 0.6, "C": 0.5, "D": 1.0}
        steps = _run(links, scores, seed="A", target="D")

        # It arrived: the last move committed to the target (recorded in the note;
        # a step's edges are score-ordered, so edges[-1] is the *worst* candidate,
        # not the one we moved to).
        assert "-> 'D'" in steps[-1].note
        # And it went the sensible way: A then B (never the C distraction).
        assert _move_sources(steps) == ["A", "B"]

    def test_seed_equal_target_yields_only_the_start(self):
        steps = _run({}, {}, seed="A", target="A")
        assert len(steps) == 1
        assert steps[0].nodes[0].id == "A"
        assert steps[0].edges == []


class TestVisitedGuard:
    def test_never_revisits_a_page(self):
        # The trap: from B the highest-scoring link is A — the page we just left.
        # A naive greedy (no visited check) ping-pongs A<->B forever. The real check
        # skips A (visited) and takes D instead.
        links = {"A": ["B"], "B": ["A", "D"]}
        scores = {"A": 0.95, "B": 0.5, "D": 0.90}
        sources = _move_sources(_run(links, scores, seed="A", target="D"))

        assert sources == ["A", "B"]  # each page processed once, in order
        assert len(sources) == len(set(sources))  # no page revisited

    def test_dead_end_when_all_top_candidates_visited(self):
        # A and B only link to each other; neither is the target. Once both are
        # visited greedy has nowhere new to go and stops (no infinite loop).
        links = {"A": ["B"], "B": ["A"]}
        scores = {"A": 0.9, "B": 0.8}
        steps = _run(links, scores, seed="A", target="Z")

        assert "dead end" in steps[-1].note
        # Moved A->B (one real advance), then dead-ended at B — the dead-end step
        # still shows B's fan-out, so B is the source of that final tick.
        assert _move_sources(steps) == ["A", "B"]
        # The point of the guard: no page is ever processed twice.
        assert len(_move_sources(steps)) == len(set(_move_sources(steps)))


class TestCaps:
    def test_respects_top_k(self):
        # Seed fans out to more than TOP_K links; the step must keep only TOP_K.
        many = [f"L{i}" for i in range(config.TOP_K + 10)]
        links = {"A": many}  # each Li links nowhere -> next tick dead-ends
        scores = {name: i / 100 for i, name in enumerate(many)}
        steps = _run(links, scores, seed="A", target="T")

        fanout = steps[1]  # step[0] is the seed; step[1] is A's fan-out
        assert len(fanout.nodes) == config.TOP_K
        assert len(fanout.edges) == config.TOP_K

    def test_respects_max_depth(self):
        # A forward-only chain longer than MAX_DEPTH, target never reached. Greedy
        # walks it until the depth cap trips.
        chain = [f"A{i}" for i in range(config.MAX_DEPTH + 3)]
        links = {name: [chain[i + 1]] for i, name in enumerate(chain[:-1])}
        scores = {name: i / 100 for i, name in enumerate(chain)}
        steps = _run(links, scores, seed=chain[0], target="T")

        assert "hit cap" in steps[-1].note
        assert len(_move_sources(steps)) == config.MAX_DEPTH  # exactly MAX_DEPTH hops


class TestStepShape:
    def test_yields_wellformed_steps(self):
        links = {"A": ["B", "C"], "B": ["D"]}
        scores = {"A": 0.1, "B": 0.6, "C": 0.4, "D": 1.0}
        steps = _run(links, scores, seed="A", target="D")

        assert all(isinstance(s, Step) for s in steps)
        for s in steps:
            assert all(isinstance(n, Node) for n in s.nodes)
            assert all(isinstance(e, Edge) for e in s.edges)
            assert isinstance(s.note, str)
            # Every edge is anchored at the current page and points to an emitted node.
            emitted = {n.id for n in s.nodes}
            for e in s.edges:
                assert e.target in emitted

    def test_candidate_nodes_carry_score_and_depth(self):
        links = {"A": ["B", "C"], "B": ["D"]}
        scores = {"A": 0.1, "B": 0.6, "C": 0.4, "D": 1.0}
        fanout = _run(links, scores, seed="A", target="D")[1]

        b = next(n for n in fanout.nodes if n.id == "B")
        assert b.score == pytest.approx(0.6)
        assert b.depth == 1  # one hop from the seed


class TestABC:
    def test_base_cannot_be_instantiated(self):
        # @abstractmethod makes the bare ABC uninstantiable — only subclasses that
        # implement `run` are real.
        with pytest.raises(TypeError):
            ConnectAlgorithm(None, None)  # type: ignore[abstract]
