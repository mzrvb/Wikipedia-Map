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
from wikimap.config import RunParams
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


def _run(links, scores, seed, target, params=None) -> list[Step]:
    algo = GreedyConnect(_FakeLinkCache(links), _FakeEmbedCache(scores))
    return list(algo.run(seed, target, params))


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

    def test_node_cap_counts_distinct_pages_not_repeat_sightings(self):
        """max_nodes caps how many pages get DRAWN, so it must count each once.

        "Shared" is linked from every page, so it lands in every single fan-out — but
        it is one circle on screen, not fifty. The old `node_count += len(top)` added
        the whole slice each tick, re-counting Shared every time, so the cap tripped
        early and the number in the note didn't match the graph.

        Note the params: max_nodes=20 because MAX_NODES_BOUNDS floors there and
        RunParams *clamps* rather than raising — asking for 5 silently gives you 20.
        max_depth=12 so the depth cap can't trip first and mask what's under test.
        """
        # Each page: one chain link (highest score, so greedy always advances), three
        # fresh dead-ends, and Shared. Four new pages per tick outruns the depth cap.
        links = {
            f"N{i}": [f"N{i + 1}", f"X{i}a", f"X{i}b", f"X{i}c", "Shared"]
            for i in range(50)
        }
        scores = (
            {f"N{i}": 0.9 for i in range(51)}
            | {f"X{i}{s}": 0.5 for i in range(50) for s in "abc"}
            | {"Shared": 0.1}
        )

        steps = _run(
            links,
            scores,
            seed="N0",
            target="T",
            params=RunParams(max_nodes=20, max_depth=12),
        )

        assert "hit cap" in steps[-1].note
        # The reported figure is the distinct pages emitted, not the running sum of
        # slice lengths — which is what makes the note trustworthy against the canvas.
        emitted = {n.id for s in steps for n in s.nodes}
        assert f"{len(emitted)} nodes" in steps[-1].note
        # Shared really did recur, or the test proves nothing.
        assert sum("Shared" in {n.id for n in s.nodes} for s in steps) > 1


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


class TestRunParams:
    """Step 6: the knobs arrive per run instead of being read off the module."""

    def test_per_run_top_k_overrides_the_default(self):
        links = {"A": ["B", "C", "D", "E"]}
        scores = {"B": 0.9, "C": 0.8, "D": 0.7, "E": 0.6}
        fanout = _run(
            links, scores, seed="A", target="T", params=RunParams(top_k=2)
        )[1]

        assert [n.id for n in fanout.nodes] == ["B", "C"]  # capped at 2, best first

    def test_per_run_max_depth_overrides_the_default(self):
        chain = [f"A{i}" for i in range(8)]
        links = {name: [chain[i + 1]] for i, name in enumerate(chain[:-1])}
        scores = {name: i / 100 for i, name in enumerate(chain)}

        steps = _run(
            links, scores, seed=chain[0], target="T", params=RunParams(max_depth=2)
        )

        assert "hit cap" in steps[-1].note
        assert len(_move_sources(steps)) == 2

    def test_omitting_params_still_uses_config_defaults(self):
        """Non-destructive: every pre-existing call site passes no params at all."""
        links = {"A": [f"L{i}" for i in range(50)]}
        scores = {f"L{i}": i / 100 for i in range(50)}
        fanout = _run(links, scores, seed="A", target="T")[1]

        assert len(fanout.nodes) == config.TOP_K

    def test_values_are_clamped_to_the_locked_ceiling(self):
        """Decision C caps K at 20. A docstring can't enforce that; __post_init__
        does — so no caller, however wrong, can exceed it."""
        assert RunParams(top_k=999).top_k == config.TOP_K_BOUNDS[1]
        assert RunParams(top_k=-5).top_k == config.TOP_K_BOUNDS[0]
        assert RunParams(max_depth=999).max_depth == config.MAX_DEPTH_BOUNDS[1]

    def test_params_are_frozen(self):
        """A run's settings must not change underneath it once it has started."""
        from dataclasses import FrozenInstanceError

        params = RunParams()
        with pytest.raises(FrozenInstanceError):
            params.top_k = 5


class TestABC:
    def test_base_cannot_be_instantiated(self):
        # @abstractmethod makes the bare ABC uninstantiable — only subclasses that
        # implement `run` are real.
        with pytest.raises(TypeError):
            ConnectAlgorithm(None, None)  # type: ignore[abstract]
