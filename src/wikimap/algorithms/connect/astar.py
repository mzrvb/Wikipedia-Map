"""Connect: A* — path cost so far plus the semantic heuristic.

Greedy asks one question: "which neighbour looks closest to the target?" It will
happily walk ten cheerful downhill hops. A* asks a second question — "how far have I
already walked?" — and orders its options by the sum:

    f = g + W * h

where `g` is hops from the seed and `h` estimates hops remaining.

THE UNITS TRAP, which is the whole reason this file has a hop-scale knob. `g` counts
in hops: 1, 2, 3. Cosine similarity lives in [0, 1]. Add them directly and the
heuristic can never outweigh even a single hop, so A* silently collapses into
breadth-first search and the heuristic does nothing. Cosine must first be converted
into hops:

    h = hop_scale * (1 - cosine(page, target))

so "totally unrelated" reads as roughly `hop_scale` hops away and "identical" reads
as zero. Only then does `g + h` mean anything.

What the weight buys (config.HEURISTIC_WEIGHT): W = 0 ignores `h` entirely and orders
purely by cost-so-far, which on unit-cost edges IS breadth-first; W very large ignores
`g` and reduces to greedy best-first. One algorithm and one slider therefore span the
whole spectrum, with greedy and BFS as its endpoints.

NOT OPTIMAL, and the docstring says so on purpose. Textbook A* guarantees a shortest
path only when its heuristic is *admissible* — never overestimating the true remaining
cost. Cosine similarity is a semantic guess with no such bound; nothing stops it being
wildly optimistic. This is a well-directed search, not a proof of the shortest path.
Decision B already accepted an estimate over ground truth; the guarantee does not
sneak back in just because the algorithm is called A*.

Shares greedy's shape everywhere else: it reads its knobs from the `RunParams` handed
to `run()` (contract 1), caps branching to the top-K links by similarity to the target
(decision C), and yields one `Step` per expansion (contract 2) knowing nothing about
the renderer or transport.
"""

import heapq
import itertools
from collections.abc import Iterator

from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.config import RunParams
from wikimap.graph.contracts import Edge, Node, Step


class AStarConnect(ConnectAlgorithm):
    """A* Connect search over the semantic heuristic. See module docstring."""

    def run(
        self, seed: str, target: str, params: RunParams | None = None
    ) -> Iterator[Step]:
        if params is None:
            params = RunParams()

        def hops_remaining(similarity: float) -> float:
            """Cosine -> estimated hops. The rescale the module docstring is about."""
            return params.hop_scale * (1.0 - similarity)

        # Every piece of state is local, so one shared AStarConnect instance can serve
        # concurrent runs — each call gets its own generator frame (same reason greedy
        # keeps `visited` local rather than on self).
        seed_similarity = self._embed_cache.similarity(seed, target)
        # Tiebreaker for the heap. Without it, two entries with equal f would fall
        # through to comparing the next tuple element; a monotonic counter keeps that
        # comparison off the titles and makes ordering deterministic (FIFO on ties).
        tiebreak = itertools.count()
        frontier = [
            (
                params.heuristic_weight * hops_remaining(seed_similarity),
                next(tiebreak),
                seed,
            )
        ]
        # Best known hop-count to each page. Doubles as "have we seen this at all" —
        # and therefore as the node counter. Every link in a `top` slice ends up a key
        # here (either it was already known, which is why it got skipped, or it gets
        # added below), so len() is exactly the number of DISTINCT nodes emitted. That
        # is what `max_nodes` is meant to cap; a running `+= len(top)` would re-count
        # pages that were merely re-encountered and trip the cap early.
        cost_from_seed = {seed: 0}
        came_from: dict[str, str] = {}
        expanded: set[str] = set()

        # Seed first, so it's born with real attributes rather than being conjured
        # blank by an edge that arrives before it (nodes-before-edges, as in greedy).
        yield Step(
            nodes=[Node(id=seed, score=seed_similarity, depth=0)],
            note=f"start: {seed!r} (target {target!r}, W={params.heuristic_weight:g})",
        )

        while frontier:
            _, _, current = heapq.heappop(frontier)

            # A page can sit in the heap several times, once per route that reached it
            # at a better cost. Only the first pop matters; the rest are stale.
            if current in expanded:
                continue
            expanded.add(current)
            depth = cost_from_seed[current]

            if current == target:
                path = _reconstruct(came_from, seed, target)
                yield Step(
                    note=f"reached {target!r} in {depth} hops: {' -> '.join(path)}"
                )
                return

            if depth >= params.max_depth:
                # Too deep to expand — but unlike greedy this is NOT the end of the
                # search. Greedy walks a single path, so its depth cap ends the run.
                # A* holds a whole frontier, and shallower candidates may still be
                # waiting, so skip this one and keep popping.
                continue

            if len(cost_from_seed) >= params.max_nodes:
                yield Step(
                    note=f"stopped: node cap at {current!r} "
                    f"(depth {depth}, {len(cost_from_seed)} nodes)"
                )
                return

            # Same expansion as greedy: fetch every link, score each against the
            # TARGET (the Connect anchor), keep the top-K. Cost here is O(outdegree)
            # regardless of K — K decides how many candidates enter the frontier.
            links = self._link_cache.get_links(current)
            scored = sorted(
                ((link, self._embed_cache.similarity(link, target)) for link in links),
                key=lambda pair: pair[1],
                reverse=True,
            )
            top = scored[: params.top_k]

            step_cost = depth + 1
            queued = 0
            for link, similarity in top:
                if link in expanded:
                    continue
                # Only queue a page if this route reaches it in fewer hops than any
                # route already found. Without this the heap fills with worse
                # duplicates of pages we already have a better path to.
                if link in cost_from_seed and cost_from_seed[link] <= step_cost:
                    continue
                cost_from_seed[link] = step_cost
                came_from[link] = current
                # `similarity` is reused from the ranking above — computing h costs no
                # extra embedding, which is the expensive part of every tick.
                f = step_cost + params.heuristic_weight * hops_remaining(similarity)
                heapq.heappush(frontier, (f, next(tiebreak), link))
                queued += 1

            current_h = hops_remaining(self._embed_cache.similarity(current, target))
            yield Step(
                nodes=[
                    Node(id=link, score=similarity, depth=step_cost)
                    for link, similarity in top
                ],
                edges=[Edge(source=current, target=link) for link, _ in top],
                note=(
                    f"expand {current!r} (g={depth}, h={current_h:.2f}, "
                    f"f={depth + params.heuristic_weight * current_h:.2f}) "
                    f"-> {queued} queued"
                ),
            )

        yield Step(note=f"exhausted: no route to {target!r} within the caps")


def _reconstruct(came_from: dict[str, str], seed: str, target: str) -> list[str]:
    """Walk the came_from chain backwards from target to seed, then flip it.

    A* jumps around its frontier instead of walking one path, so unlike greedy the
    route it found isn't the order pages were visited — it has to be rebuilt from the
    "who queued this page" links recorded during the search.
    """
    path = [target]
    while path[-1] != seed:
        path.append(came_from[path[-1]])
    return list(reversed(path))
