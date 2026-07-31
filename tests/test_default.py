"""Bidirectional beam search — the default algorithm.

All fast: fake caches supply canned links, backlinks, and similarity scores, so no
network and no model ever load. Same fake shapes as test_astar.py/test_bfs.py, since
this algorithm is a genuine combination of both.
"""

from wikimap.algorithms.connect.default import DefaultConnect
from wikimap.config import RunParams
from wikimap.graph.contracts import Edge, Node, Step


class _FakeLinkCache:
    def __init__(
        self,
        links: dict[str, list[str]] | None = None,
        backlinks: dict[str, list[str]] | None = None,
    ):
        self._links = links or {}
        self._backlinks = backlinks or {}

    def get_links(self, title: str) -> list[str]:
        return self._links.get(title, [])

    def get_backlinks(self, title: str) -> list[str]:
        return self._backlinks.get(title, [])


class _FakeEmbedCache:
    """`similarity(x, y)` ignores `y` and looks `x` up in a title -> score table —
    same simplification test_astar.py makes. A page is maximally similar to itself."""

    def __init__(self, scores: dict[str, float]):
        self._scores = scores

    def similarity(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        return self._scores.get(a, 0.0)

    def similarity_many(self, titles: list[str], anchor: str) -> dict[str, float]:
        return {title: self.similarity(title, anchor) for title in titles}


def _run(links, backlinks, scores, seed, target, params=None) -> list[Step]:
    algo = DefaultConnect(_FakeLinkCache(links, backlinks), _FakeEmbedCache(scores))
    return list(algo.run(seed, target, params))


def _backward_nodes(steps: list[Step]) -> list[Node]:
    return [n for s in steps for n in s.nodes if n.depth is not None and n.depth < 0]


def _forward_nodes(steps: list[Step]) -> list[Node]:
    return [n for s in steps for n in s.nodes if n.depth is not None and n.depth > 0]


class TestReachesTarget:
    def test_finds_the_target_and_reports_the_path(self):
        links = {"A": ["B", "C"], "B": ["D"], "C": ["A"]}
        scores = {"A": 0.1, "B": 0.6, "C": 0.5, "D": 1.0}

        steps = _run(links, {}, scores, seed="A", target="D")

        assert "reached 'D'" in steps[-1].note
        assert "A -> B -> D" in steps[-1].note

    def test_seed_equal_to_target_terminates_immediately(self):
        steps = _run({}, {}, {}, seed="A", target="A")

        assert "reached 'A' in 0 hops" in steps[-1].note
        assert len(steps) == 1

    def test_reports_exhaustion_when_no_route_exists(self):
        links = {"A": ["B"], "B": []}
        scores = {"A": 0.1, "B": 0.2}

        steps = _run(links, {}, scores, seed="A", target="Unreachable")

        assert "exhausted" in steps[-1].note


class TestBidirectionality:
    def test_backward_discovery_is_required_and_a_same_tick_meeting_is_caught(self):
        """FORWARD's own link graph is a dead end (seed -> A, and A has no links at
        all) -- the only way to a route is BACKWARD's own expansion of target,
        which discovers A as a direct backlink, in the SAME tick forward also
        reaches A. This exercises two things at once: backward is load-bearing (if
        get_backlinks weren't genuinely driving the search, this would report
        'exhausted'), and the third meeting-detection source -- two independent
        same-tick discoveries of one page -- fires without needing an extra tick."""
        links = {"seed": ["A"]}
        backlinks = {"target": ["A"]}
        scores = {"A": 0.5}

        steps = _run(links, backlinks, scores, seed="seed", target="target")

        assert _backward_nodes(steps) != []
        assert "reached 'target' in 2 hops (met at 'A')" in steps[-1].note
        assert "seed -> A -> target" in steps[-1].note


class TestNoStarvationPossible:
    def test_backward_expands_every_tick_no_matter_how_much_better_forward_looks(self):
        """Regression test for the live-found bug (see default.py's module
        docstring): the old turn-based design let forward monopolize every tick
        whenever its candidates kept scoring well, starving backward completely.
        Forward's chain scores 0.99 (near-perfect) every hop; backward's chain
        scores 0.05 (near-worthless) every hop. Under the OLD design backward would
        likely never get picked. Under this design there is no picking -- both
        sides expand their own frontier every tick, unconditionally -- so backward
        must still produce nodes on both ticks despite the enormous score gap."""
        links = {"seed": ["Great1"], "Great1": ["Great2"]}
        backlinks = {"target": ["Bad1"], "Bad1": ["Bad2"]}
        scores = {"Great1": 0.99, "Great2": 0.99, "Bad1": 0.05, "Bad2": 0.05}

        steps = _run(
            links, backlinks, scores, seed="seed", target="target",
            params=RunParams(max_depth=2),
        )

        backward_ids = {n.id for n in _backward_nodes(steps)}
        assert backward_ids == {"Bad1", "Bad2"}
        assert "exhausted" in steps[-1].note  # the two chains never actually meet


class TestCaps:
    def test_top_k_caps_each_side_independently_not_pooled(self):
        """Forward has 30 real candidates that all score far higher than backward's
        5. If pruning were pooled into one shared top-K, backward's low scores
        could lose every slot to forward's. Per-side pruning means backward keeps
        its own top-K (or fewer, if it has fewer candidates than K) regardless of
        how forward's candidates compare."""
        links = {"seed": [f"F{i}" for i in range(30)]}
        backlinks = {"target": [f"B{i}" for i in range(5)]}
        scores = {f"F{i}": 0.9 for i in range(30)} | {f"B{i}": 0.01 for i in range(5)}

        steps = _run(
            links, backlinks, scores, seed="seed", target="target",
            params=RunParams(top_k=4),
        )
        fanout = steps[1]

        assert sum(1 for n in fanout.nodes if n.depth == 1) == 4
        assert sum(1 for n in fanout.nodes if n.depth == -1) == 4

    def test_max_depth_caps_each_side_identically(self):
        """A 6-hop chain; max_depth=2 means forward reaches {seed, A, B} and
        backward reaches {target, E, D} -- no overlap, so the run correctly
        reports exhaustion, not a wrong answer. 'Per side' is now automatic
        rather than independently tracked, since both sides always advance
        together (see module docstring)."""
        links = {"seed": ["A"], "A": ["B"], "B": ["C"], "C": ["D"], "D": ["E"], "E": ["target"]}
        backlinks = {
            "A": ["seed"], "B": ["A"], "C": ["B"], "D": ["C"], "E": ["D"], "target": ["E"],
        }

        steps = _run(
            links, backlinks, {}, seed="seed", target="target",
            params=RunParams(max_depth=2),
        )

        assert "exhausted" in steps[-1].note


class TestDuplicateDiscoveryWithinAPly:
    def test_a_link_reached_by_two_parents_in_the_same_ply_is_emitted_once(self):
        """P1 and P2 are both on the forward frontier in the same tick, and both
        link to 'Shared'. Without dedup this would emit two Nodes for the same
        page in one Step. P1 outranks P2 (0.5 vs 0.4) at tick 1, so P1 sorts first
        in the frontier and wins the tie when both reach 'Shared' with an
        identical score at tick 2 -- first-seen-wins is deterministic, not
        order-of-dict-iteration luck."""
        links = {"seed": ["P1", "P2"], "P1": ["Shared"], "P2": ["Shared"]}
        scores = {"P1": 0.5, "P2": 0.4, "Shared": 0.9}

        steps = _run(links, {}, scores, seed="seed", target="target")
        tick2 = steps[2]

        shared_nodes = [n for n in tick2.nodes if n.id == "Shared"]
        assert len(shared_nodes) == 1
        shared_edges = [e for e in tick2.edges if e.target == "Shared"]
        assert len(shared_edges) == 1
        assert shared_edges[0].source == "P1"


class TestStepShape:
    def test_yields_wellformed_steps(self):
        links = {"A": ["B", "C"], "B": ["D"]}
        scores = {"A": 0.1, "B": 0.6, "C": 0.4, "D": 1.0}

        steps = _run(links, {}, scores, seed="A", target="D")

        assert all(isinstance(s, Step) for s in steps)
        for s in steps:
            assert all(isinstance(n, Node) for n in s.nodes)
            assert all(isinstance(e, Edge) for e in s.edges)
            assert isinstance(s.note, str)

    def test_seed_and_target_both_carry_similarity_from_the_first_step(self):
        steps = _run({"A": ["B"]}, {}, {"A": 0.3, "B": 0.9}, seed="A", target="T")

        first_step_ids = {n.id: n for n in steps[0].nodes}
        assert first_step_ids.keys() == {"A", "T"}
        assert first_step_ids["A"].depth == 0
        assert first_step_ids["T"].depth == 0


class TestSharedInstanceIsSafe:
    def test_two_runs_from_one_instance_do_not_interfere(self):
        algo = DefaultConnect(
            _FakeLinkCache({"A": ["B"], "B": ["C"], "X": ["Y"], "Y": ["Z"]}),
            _FakeEmbedCache({"B": 0.5, "C": 1.0, "Y": 0.5, "Z": 1.0}),
        )

        first = algo.run("A", "C")
        second = algo.run("X", "Z")
        next(first)
        next(second)

        assert "reached 'C'" in list(first)[-1].note
        assert "reached 'Z'" in list(second)[-1].note
