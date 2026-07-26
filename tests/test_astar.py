"""A* Connect search (roadmap step 7).

All fast: fake caches supply canned links and canned similarity scores, so no network
and no model ever load. Same fake shape as test_greedy.py — the point of the ABC is
that both algorithms consume identical inputs.

The tests that matter most here are the ones about the *weight*: A* is only worth
building instead of a separate BFS because W spans the spectrum, so "W=0 behaves
breadth-first" and "large W behaves greedily" are behavioural claims, not comments.
"""

import pytest

from wikimap.algorithms.connect.astar import AStarConnect
from wikimap.config import RunParams
from wikimap.graph.contracts import Edge, Node, Step


class _FakeLinkCache:
    def __init__(self, links: dict[str, list[str]]):
        self._links = links

    def get_links(self, title: str) -> list[str]:
        return self._links.get(title, [])


class _FakeEmbedCache:
    """`similarity(x, target)` from a title -> score table; a page is maximally
    similar to itself, so a link that IS the target always ranks first."""

    def __init__(self, scores: dict[str, float]):
        self._scores = scores

    def similarity(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        return self._scores.get(a, 0.0)


def _run(links, scores, seed, target, params=None) -> list[Step]:
    algo = AStarConnect(_FakeLinkCache(links), _FakeEmbedCache(scores))
    return list(algo.run(seed, target, params))


def _expanded(steps: list[Step]) -> list[str]:
    """Which page each tick expanded, read from the note.

    Deliberately NOT `step.edges[0].source`: a page with no outbound links expands
    perfectly normally but emits a Step with zero edges, so an edge-based reading
    silently drops it. That mistake made five of these tests fail against correct
    code — the same trap as step 4's score-ordering mix-up (see LEARN.md).
    """
    return [s.note.split("'")[1] for s in steps if s.note.startswith("expand ")]


class TestReachesTarget:
    def test_finds_the_target_and_reports_the_path(self):
        links = {"A": ["B", "C"], "B": ["D"], "C": ["A"]}
        scores = {"A": 0.1, "B": 0.6, "C": 0.5, "D": 1.0}

        steps = _run(links, scores, seed="A", target="D")

        assert "reached 'D'" in steps[-1].note
        assert "A -> B -> D" in steps[-1].note

    def test_seed_equal_to_target_terminates_immediately(self):
        steps = _run({"A": ["B"]}, {"A": 1.0}, seed="A", target="A")

        assert "reached 'A' in 0 hops" in steps[-1].note
        assert _expanded(steps) == []  # nothing was ever expanded

    def test_reports_exhaustion_when_no_route_exists(self):
        links = {"A": ["B"], "B": []}
        scores = {"A": 0.1, "B": 0.2}

        steps = _run(links, scores, seed="A", target="Unreachable")

        assert "exhausted" in steps[-1].note


class TestTheWeightSpansTheSpectrum:
    """f = g + W * h. These pin the two endpoints the config comment claims."""

    def test_zero_weight_orders_by_hops_alone(self):
        """W=0 discards the heuristic, so ordering is by cost-so-far — which on
        unit-cost edges is breadth-first: everything at depth 1 before depth 2."""
        links = {
            "A": ["Near", "Far"],
            "Near": ["Deep"],  # depth 2
            "Far": [],
        }
        # "Near" looks great, "Far" looks terrible. Under BFS ordering both depth-1
        # pages must still be expanded before the depth-2 "Deep".
        scores = {"Near": 0.95, "Far": 0.01, "Deep": 0.99}

        steps = _run(
            links, scores, seed="A", target="T", params=RunParams(heuristic_weight=0.0)
        )

        order = _expanded(steps)
        assert order[0] == "A"
        assert set(order[1:3]) == {"Near", "Far"}  # both depth-1 pages first

    def test_large_weight_behaves_greedily(self):
        """A huge W drowns out g, so A* chases the best-looking page regardless of
        how deep it is — the greedy endpoint."""
        links = {
            "A": ["Near", "Far"],
            "Near": ["Deep"],
            "Far": [],
        }
        scores = {"Near": 0.95, "Far": 0.01, "Deep": 0.99}

        steps = _run(
            links, scores, seed="A", target="T", params=RunParams(heuristic_weight=25.0)
        )

        order = _expanded(steps)
        # Dives: A -> Near -> Deep, taking the depth-2 winner before the poor
        # depth-1 sibling, which is exactly what greedy would do.
        assert order[:3] == ["A", "Near", "Deep"]

    def test_hop_scale_of_zero_also_flattens_the_heuristic(self):
        """h = hop_scale * (1 - cos). Zero scale means h is always 0, so this is a
        second route to BFS ordering — and the reason both knobs exist separately."""
        links = {"A": ["Near", "Far"], "Near": ["Deep"], "Far": []}
        scores = {"Near": 0.95, "Far": 0.01, "Deep": 0.99}

        steps = _run(
            links, scores, seed="A", target="T", params=RunParams(hop_scale=0.0)
        )

        order = _expanded(steps)
        assert set(order[1:3]) == {"Near", "Far"}


class TestCaps:
    def test_top_k_caps_the_candidates_per_tick(self):
        links = {"A": [f"L{i}" for i in range(30)]}
        scores = {f"L{i}": i / 100 for i in range(30)}

        fanout = _run(links, scores, seed="A", target="T", params=RunParams(top_k=4))[1]

        assert len(fanout.nodes) == 4
        assert len(fanout.edges) == 4

    def test_depth_cap_skips_deep_pages_but_keeps_searching(self):
        """The behavioural difference from greedy: greedy walks one path, so its
        depth cap ends the run. A* holds a frontier, so a too-deep page is skipped
        while shallower candidates are still expanded."""
        links = {
            "A": ["B", "Sibling"],
            "B": ["TooDeep"],
            "TooDeep": ["Never"],
            "Sibling": [],
        }
        scores = {"B": 0.9, "Sibling": 0.05, "TooDeep": 0.95, "Never": 1.0}

        steps = _run(
            links, scores, seed="A", target="T", params=RunParams(max_depth=2)
        )

        order = _expanded(steps)
        assert "Never" not in order  # depth 3 was never expanded
        assert "Sibling" in order  # but the shallow branch still got its turn
        assert "exhausted" in steps[-1].note

    def test_node_cap_stops_the_run(self):
        # A branching tree so the frontier never runs dry before the cap trips.
        links = {f"N{i}": [f"N{i * 5 + j}" for j in range(1, 6)] for i in range(200)}
        scores = {f"N{i}": 0.5 for i in range(1000)}

        steps = _run(
            links, scores, seed="N0", target="T", params=RunParams(max_nodes=20)
        )

        assert "node cap" in steps[-1].note


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
            emitted = {n.id for n in s.nodes}
            for e in s.edges:
                assert e.target in emitted

    def test_seed_step_carries_its_similarity(self):
        steps = _run({"A": ["B"]}, {"A": 0.3, "B": 0.9}, seed="A", target="T")

        seed_node = steps[0].nodes[0]
        assert seed_node.id == "A"
        assert seed_node.score == pytest.approx(0.3)
        assert seed_node.depth == 0

    def test_note_reports_g_h_and_f(self):
        """The numbers are the point of A* — a run log that only said "expanded X"
        would hide whether the weight is doing anything."""
        steps = _run({"A": ["B"]}, {"A": 0.5, "B": 0.9}, seed="A", target="T")

        fanout_note = steps[1].note
        assert "g=0" in fanout_note
        assert "h=" in fanout_note
        assert "f=" in fanout_note


class TestSharedInstanceIsSafe:
    def test_two_runs_from_one_instance_do_not_interfere(self):
        """The server holds one AStarConnect for every request, so its per-run state
        must live in run()'s locals, not on self."""
        algo = AStarConnect(
            _FakeLinkCache({"A": ["B"], "B": ["C"], "X": ["Y"], "Y": ["Z"]}),
            _FakeEmbedCache({"B": 0.5, "C": 1.0, "Y": 0.5, "Z": 1.0}),
        )

        first = algo.run("A", "C")
        second = algo.run("X", "Z")
        # Interleave them deliberately: pull from each in turn.
        next(first)
        next(second)

        assert "reached 'C'" in list(first)[-1].note
        assert "reached 'Z'" in list(second)[-1].note
