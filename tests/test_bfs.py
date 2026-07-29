"""Bidirectional BFS Connect search — the ground-truth check on greedy/A*.

All fast: a fake link cache supplies canned forward links AND canned backlinks, so no
network and no model ever load (BFS never touches the embed cache at all — see
TestNotCosineCapped below, which proves that rather than just asserting it).
"""

from wikimap.algorithms.connect.bfs import BFSConnect
from wikimap.config import RunParams
from wikimap.graph.contracts import Edge, Node, Step


class _FakeLinkCache:
    """Stand-in for LinkCache: two independent title -> [titles] tables, one per
    direction, since real forward/backward link sets are NOT required to be exact
    inverses of each other (the real backlinks fetch is a capped, order-arbitrary
    sample - see wiki/client.py)."""

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


def _run(links, backlinks, seed, target, params=None, embed_cache=None) -> list[Step]:
    algo = BFSConnect(_FakeLinkCache(links, backlinks), embed_cache)
    return list(algo.run(seed, target, params))


class TestReachesTarget:
    def test_finds_the_target_and_reports_the_path(self):
        links = {"seed": ["A"], "A": ["B"], "B": ["target"]}
        backlinks = {"A": ["seed"], "B": ["A"], "target": ["B"]}

        steps = _run(links, backlinks, seed="seed", target="target")

        assert "reached 'target' in 3 hops" in steps[-1].note
        assert "seed -> A -> B -> target" in steps[-1].note

    def test_seed_equal_to_target_terminates_immediately(self):
        steps = _run({}, {}, seed="A", target="A")

        assert "reached 'A' in 0 hops" in steps[-1].note
        assert len(steps) == 1

    def test_reports_exhaustion_when_no_route_exists(self):
        links = {"A": ["B"], "B": []}
        backlinks = {"B": ["A"]}

        steps = _run(links, backlinks, seed="A", target="Unreachable")

        assert "exhausted" in steps[-1].note


class TestBidirectionality:
    def test_backward_search_finds_a_meeting_forward_alone_would_take_longer_to_reach(self):
        """seed fans out to 5 dead-end pages; the real route to target only exists
        through F3. Forward's queue balloons to 5 after the first tick, so the
        smaller-queue rule hands the next several turns to BACKWARD - proving
        get_backlinks is genuinely driving the search, not just decoration."""
        links = {
            "seed": ["F1", "F2", "F3", "F4", "F5"],
            "F3": ["Mid"],
            "Mid": ["target"],
        }
        backlinks = {"target": ["Mid"], "Mid": ["F3"]}

        steps = _run(links, backlinks, seed="seed", target="target")

        notes = [s.note for s in steps]
        assert any(n.startswith("expand->") for n in notes)
        assert any(n.startswith("<-expand") for n in notes)
        # Which node the two searches happen to meet at is an implementation detail
        # (depends on tick-by-tick timing); the path and hop count are not.
        assert "reached 'target' in 3 hops" in steps[-1].note
        assert "seed -> F3 -> Mid -> target" in steps[-1].note


class TestNotCosineCapped:
    def test_never_touches_the_embed_cache(self):
        """A bare object with no `similarity` method: if BFS ever called it, this
        would raise AttributeError instead of silently passing. Proves the "no
        embedding at all" claim rather than just asserting it."""
        links = {"seed": ["A"], "A": ["target"]}
        backlinks = {"A": ["seed"], "target": ["A"]}

        steps = _run(links, backlinks, seed="seed", target="target", embed_cache=object())

        assert "reached 'target'" in steps[-1].note

    def test_does_not_slice_to_top_k(self):
        many = [f"L{i}" for i in range(25)]  # more than TOP_K's default ceiling of 20
        links = {"seed": many}

        steps = _run(links, {}, seed="seed", target="T", params=RunParams(top_k=2))

        fanout = steps[1]
        assert len(fanout.nodes) == 25
        assert len(fanout.edges) == 25


class TestCaps:
    def test_max_depth_caps_each_side_independently(self):
        """A 6-hop chain. With max_depth=2, forward reaches {seed, A, B} and
        backward reaches {target, E, D} - no overlap, so the (real) route is missed
        and the run correctly reports exhaustion rather than a wrong answer."""
        links = {"seed": ["A"], "A": ["B"], "B": ["C"], "C": ["D"], "D": ["E"], "E": ["target"]}
        backlinks = {
            "A": ["seed"], "B": ["A"], "C": ["B"], "D": ["C"], "E": ["D"], "target": ["E"],
        }

        steps = _run(
            links, backlinks, seed="seed", target="target", params=RunParams(max_depth=2)
        )

        assert "exhausted" in steps[-1].note

    def test_max_nodes_stops_the_run(self):
        links = {f"N{i}": [f"N{i * 5 + j}" for j in range(1, 6)] for i in range(200)}

        steps = _run(links, {}, seed="N0", target="Unreachable", params=RunParams(max_nodes=20))

        assert "node cap" in steps[-1].note
        # The cap is checked after every single node's fan-out, not once per whole
        # ply - so overshoot is bounded by one page's fan-out (5 here), not by an
        # entire ply's worth of pages (which, before the fix, let this same graph
        # balloon to 32 nodes before the cap was ever rechecked).
        total_nodes = sum(len(s.nodes) for s in steps)
        assert total_nodes <= 20 + 5

    def test_meeting_found_wins_over_node_cap_on_the_same_discovery(self):
        """16 dead ends pad seed's fan-out so the running total sits at 19 right
        before backward's single node (target) adds the 20th - which is also the
        exact node ('A') the forward search already knows, i.e. the meeting. Checking
        `meeting` before `max_nodes` (see bfs.py) means this must report "reached",
        never "stopped: node cap", even though the same discovery crosses both."""
        dead_ends = [f"D{i}" for i in range(16)]
        links = {"seed": dead_ends + ["A"]}
        backlinks = {"target": ["A"]}

        steps = _run(
            links, backlinks, seed="seed", target="target",
            params=RunParams(max_nodes=20, max_depth=10),
        )

        assert "reached 'target'" in steps[-1].note
        assert "node cap" not in steps[-1].note

    def test_stops_firing_fetches_for_the_rest_of_the_ply_once_meeting_is_found(self):
        """seed fans out to three siblings [A, B, C]; only A leads anywhere (to X,
        which backward has already reached). Once meeting is found while expanding
        A, B and C - later in that same ply, not yet fetched - must never be
        expanded: neither ever appears in any yielded Step's note."""
        links = {"seed": ["A", "B", "C"], "A": ["X"]}
        backlinks = {"target": ["X"]}

        steps = _run(links, backlinks, seed="seed", target="target", params=RunParams(max_depth=10))

        notes = [s.note for s in steps]
        assert not any("'B'" in n for n in notes)
        assert not any("'C'" in n for n in notes)
        assert "reached 'target'" in steps[-1].note


class TestStepShape:
    def test_nodes_never_carry_a_score(self):
        links = {"seed": ["A"], "A": ["target"]}
        backlinks = {"A": ["seed"], "target": ["A"]}

        steps = _run(links, backlinks, seed="seed", target="target")

        for step in steps:
            for node in step.nodes:
                assert node.score is None

    def test_forward_and_backward_nodes_carry_opposite_signed_depth(self):
        links = {"seed": ["A"], "X": ["target"]}
        backlinks = {"target": ["X"]}

        steps = _run(links, backlinks, seed="seed", target="target")

        forward_node = next(n for s in steps for n in s.nodes if n.id == "A")
        backward_node = next(n for s in steps for n in s.nodes if n.id == "X")
        assert forward_node.depth == 1
        assert backward_node.depth == -1

    def test_yields_wellformed_steps(self):
        links = {"seed": ["A", "B"], "A": ["target"]}
        backlinks = {"A": ["seed"], "B": ["seed"], "target": ["A"]}

        steps = _run(links, backlinks, seed="seed", target="target")

        assert all(isinstance(s, Step) for s in steps)
        for s in steps:
            assert all(isinstance(n, Node) for n in s.nodes)
            assert all(isinstance(e, Edge) for e in s.edges)
            assert isinstance(s.note, str)


class TestSharedInstanceIsSafe:
    def test_two_runs_from_one_instance_do_not_interfere(self):
        algo = BFSConnect(
            _FakeLinkCache(
                links={"A": ["B"], "B": ["C"], "X": ["Y"], "Y": ["Z"]},
                backlinks={"B": ["A"], "C": ["B"], "Y": ["X"], "Z": ["Y"]},
            ),
            None,
        )

        first = algo.run("A", "C")
        second = algo.run("X", "Z")
        next(first)
        next(second)

        assert "reached 'C'" in list(first)[-1].note
        assert "reached 'Z'" in list(second)[-1].note
