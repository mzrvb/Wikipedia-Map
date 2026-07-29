"""Connect: bidirectional BFS — the ground-truth check on greedy/A*.

Greedy and A* both rank candidates by cosine similarity to the target and keep only
the top-K (decision C). That is exactly what makes them fast, and exactly what makes
them untrustworthy as a judge of their OWN shortest-path claims: a cosine-capped
search can only ever find routes cosine was willing to consider. It cannot answer
"did greedy miss a shorter route" — it would just reproduce greedy's bias with extra
steps. So this algorithm is deliberately the opposite of decision C on both axes:

- **Not cosine-capped.** Every outbound link is expanded, unranked. No embedding is
  computed at all — Node.score is always None here. That is a real efficiency win
  (embedding is the expensive part of every other algorithm's tick) bought by giving
  up the ability to rank candidates, which BFS never needed anyway.
- **Bidirectional**, and this part is not optional. Real Wikipedia outdegree is large
  enough (~300 on an ordinary page, thousands on a hub) that one-directional uncapped
  BFS is infeasible past a few hops — HISTORY.md's own estimate is roughly 8,421
  expansions for a 4-hop path unidirectionally versus 42 bidirectionally. Expanding
  from the seed forward (`get_links`) and from the target backward (`get_backlinks`)
  turns a K^L search into roughly 2*K^(L/2): the frontiers only need to cover half
  the distance each before they meet.

Unweighted-graph BFS (every hop costs 1) DOES guarantee the shortest path, unlike A*'s
cosine heuristic, which is not admissible. That guarantee is the entire reason to build
this: it is what greedy/A* results get graded against, not a replacement for them at
solve-time (this is still, per decision B, much slower on a cold cache than the
heuristic-guided algorithms — "ground truth" was never claimed to be "cheap").

THE PLY-SYNCHRONIZATION TRAP, found live (2026-07-28), twice over. A first version
picked which side to expand by comparing raw queue *length* after however much of it
had already drained. That let one side race several hops deep while the other side's
shallower, already-known-to-exist frontier just sat there unexpanded — so a longer
meeting could be reported before a shorter one that was genuinely available, because
the shorter one's turn never came in time. Proven wrong live: it returned a 4-hop
`Mitsubishi -> Kanye West` when A* — a heuristic search with NO optimality guarantee —
had already found a 3-hop route. A second attempt fixed the queue-draining problem by
comparing whole-frontier *size* between plies instead — but size is not depth, and the
same failure mode survives in a subtler form: a side whose frontier happens to stay
small (a thin chain, one link per page) keeps "winning" the size comparison and races
ahead in actual hop-depth indefinitely, while the other side's much wider but shallower
frontier never gets a turn. The only thing that is actually safe to compare is DEPTH
LEVEL itself: expand whichever side's current frontier sits at the lower (or equal)
depth number, full level at a time. That bounds the two sides' depths to differ by at
most one at any moment, which is what makes "first meeting found" provably the
shortest — by the time a node at depth d is discovered, every node at depth < d on
BOTH sides has already been fully expanded, so nothing shorter remains to be found.

Depth on emitted nodes: forward-discovered nodes carry +hops-from-seed, exactly like
greedy/A*. Backward-discovered nodes carry -hops-from-target instead of re-using the
same positive scale — there is no single "true" depth for a node discovered walking
backward from the target, and the sign lets "colour by depth" visually separate the
two searches meeting in the middle, which is otherwise invisible in the drawn graph.
"""

from collections.abc import Iterator

from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.config import RunParams
from wikimap.graph.contracts import Edge, Node, Step


class BFSConnect(ConnectAlgorithm):
    """Bidirectional, uncapped BFS Connect search. See module docstring."""

    def run(
        self, seed: str, target: str, params: RunParams | None = None
    ) -> Iterator[Step]:
        if params is None:
            params = RunParams()

        # All state local, as in greedy/A* — one shared instance must be safe for
        # concurrent runs. top_k is never read: this algorithm has no ranked
        # candidates to cap, only the full set (decision to NOT cosine-cap, see
        # module docstring).
        if seed == target:
            yield Step(
                nodes=[Node(id=seed, score=None, depth=0)],
                note=f"reached {target!r} in 0 hops: {seed!r}",
            )
            return

        forward_depth = {seed: 0}
        forward_parent: dict[str, str] = {}
        forward_frontier = [seed]  # nodes at the current depth, not yet expanded

        backward_depth = {target: 0}
        backward_parent: dict[str, str] = {}
        backward_frontier = [target]

        yield Step(
            nodes=[Node(id=seed, score=None, depth=0)],
            note=f"start: {seed!r} (target {target!r}, bidirectional)",
        )

        meeting: str | None = None

        while forward_frontier or backward_frontier:
            # The side sitting at the LOWER depth level goes next — comparing depth
            # NUMBER, not frontier size (see the module docstring: comparing size was
            # the second, subtler version of the same bug). Every node in a frontier
            # list shares one depth, since it was built as one complete ply.
            forward_level = forward_depth[forward_frontier[0]] if forward_frontier else None
            backward_level = backward_depth[backward_frontier[0]] if backward_frontier else None
            expand_forward = forward_frontier and (
                backward_level is None or forward_level <= backward_level
            )

            # max_nodes is checked HERE, after every single node's full (already-fetched,
            # so free) fan-out, not once per whole ply. A ply is every node at one depth
            # level, and BFS never ranks/cuts links (that's the entire point of it being
            # the uncapped ground truth) — so one ply's fan-out has no size limit the way
            # greedy/A*'s top_k gives them. Checking only once per ply let a single wide
            # round blow past the configured cap by 5-10x before anyone noticed. Checking
            # meeting first, and breaking on it before this check is ever reached, is what
            # makes "found the target" always win over "hit the cap" on the same discovery.
            if expand_forward:
                depth = forward_level
                next_frontier: list[str] = []
                if depth < params.max_depth:
                    for current in forward_frontier:
                        nodes, edges = [], []
                        for link in self._link_cache.get_links(current):
                            if link in forward_depth:
                                continue
                            forward_depth[link] = depth + 1
                            forward_parent[link] = current
                            next_frontier.append(link)
                            nodes.append(Node(id=link, score=None, depth=depth + 1))
                            edges.append(Edge(source=current, target=link))
                            if meeting is None and link in backward_depth:
                                meeting = link

                        yield Step(
                            nodes=nodes,
                            edges=edges,
                            note=f"expand->  {current!r} (g={depth}) -> {len(nodes)} new",
                        )

                        if meeting is not None:
                            # Nothing found in the rest of this ply — on either side —
                            # can beat this in hop count (see the depth-level invariant
                            # in the module docstring), so stop firing fetches for the
                            # remaining, not-yet-touched nodes in this frontier.
                            break
                        if len(forward_depth) + len(backward_depth) >= params.max_nodes:
                            yield Step(
                                note=f"stopped: node cap "
                                f"({len(forward_depth) + len(backward_depth)} nodes)"
                            )
                            return
                forward_frontier = next_frontier

            else:
                depth = backward_level
                next_frontier = []
                if depth < params.max_depth:
                    for current in backward_frontier:
                        nodes, edges = [], []
                        # get_backlinks(current) returns pages that link TO current, so
                        # the real hyperlink direction is link -> current.
                        for link in self._link_cache.get_backlinks(current):
                            if link in backward_depth:
                                continue
                            backward_depth[link] = depth + 1
                            backward_parent[link] = current
                            next_frontier.append(link)
                            nodes.append(Node(id=link, score=None, depth=-(depth + 1)))
                            edges.append(Edge(source=link, target=current))
                            if meeting is None and link in forward_depth:
                                meeting = link

                        yield Step(
                            nodes=nodes,
                            edges=edges,
                            note=f"<-expand  {current!r} (g={depth}) -> {len(nodes)} new",
                        )

                        if meeting is not None:
                            break
                        if len(forward_depth) + len(backward_depth) >= params.max_nodes:
                            yield Step(
                                note=f"stopped: node cap "
                                f"({len(forward_depth) + len(backward_depth)} nodes)"
                            )
                            return
                backward_frontier = next_frontier

            if meeting is not None:
                path = _reconstruct(forward_parent, backward_parent, seed, target, meeting)
                total_hops = len(path) - 1
                yield Step(
                    note=f"reached {target!r} in {total_hops} hops (met at {meeting!r}): "
                    f"{' -> '.join(path)}"
                )
                return

        yield Step(note=f"exhausted: no route to {target!r} within the caps")


def _reconstruct(
    forward_parent: dict[str, str],
    backward_parent: dict[str, str],
    seed: str,
    target: str,
    meeting: str,
) -> list[str]:
    """Stitch the seed->meeting and meeting->target halves into one path.

    forward_parent walks toward the seed (meeting -> ... -> seed, reversed below).
    backward_parent walks toward the target in the REAL link direction already —
    backward_parent[x] = y was recorded because x's backlinks include a page that
    links to y, i.e. the real edge is x -> y — so this half needs no reversal.
    """
    forward_half = [meeting]
    while forward_half[-1] != seed:
        forward_half.append(forward_parent[forward_half[-1]])
    forward_half.reverse()

    backward_half = []
    node = meeting
    while node != target:
        node = backward_parent[node]
        backward_half.append(node)

    return forward_half + backward_half