"""Connect: greedy best-first on the semantic heuristic.

Ported from ../Wikipedia Speedrun/greedy_search.py. That version's loop guard is
dead code — do not carry it over; write a real visited check.

The algorithm: from the seed, repeatedly hop to the single unvisited neighbour that
looks *closest to the target* — where "close" is cosine similarity between page-title
embeddings (decision B), and "neighbour" is capped to the top-K links by that same
score (decision C). Pure greedy: it commits to the local best every tick and never
backtracks. It takes its knobs from the `RunParams` handed to `run()` — whose defaults
come from `config` (contract 1) — and yields a `Step` per tick (contract 2); it knows
nothing of the renderer or transport.

Why the visited check is load-bearing and not optional: the highest-similarity
neighbour of a page is very often the page you just came from (they're semantically
adjacent). Without tracking visited nodes, greedy ping-pongs between two pages
forever. The predecessor "guarded" against this with code that never actually ran —
the one bug we refuse to carry over.
"""

from collections.abc import Iterator

from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.config import RunParams
from wikimap.graph.contracts import Edge, Node, Step


class GreedyConnect(ConnectAlgorithm):
    """Greedy best-first Connect search. See module docstring."""

    def run(
        self, seed: str, target: str, params: RunParams | None = None
    ) -> Iterator[Step]:
        # None means "use the defaults". Built here rather than as a default argument
        # value because a mutable/shared default object would be created once at
        # function-definition time and reused by every call — the classic Python
        # default-argument trap. A fresh one per run is both correct and cheap.
        if params is None:
            params = RunParams()

        # All state below is LOCAL, not on self. That is what lets one shared
        # GreedyConnect instance serve concurrent runs: each call to run() gets its
        # own generator frame, so two searches can never see each other's `visited`.
        visited = {seed}
        current = seed
        depth = 0
        # Every DISTINCT page ever emitted — not just the ones walked to. Two separate
        # sets on purpose: `visited` is the path (where greedy has stood, which drives
        # the loop guard), `seen` is the drawing (every node the frontend has been sent,
        # which is what `max_nodes` caps). A running `+= len(top)` conflated them and
        # re-counted pages that appeared in more than one fan-out.
        seen = {seed}

        # Emit the seed first so it's born with real attributes. If we let the first
        # tick's edges create it implicitly, networkx would conjure it as a blank node
        # (no score/depth) — edges auto-create missing endpoints. Nodes-before-edges.
        yield Step(
            nodes=[Node(id=seed, score=self._embed_cache.similarity(seed, target), depth=0)],
            note=f"start: {seed!r} (target {target!r})",
        )

        while current != target:
            if depth >= params.max_depth or len(seen) >= params.max_nodes:
                yield Step(
                    note=f"stopped: hit cap at {current!r} "
                    f"(depth {depth}, {len(seen)} nodes)"
                )
                return

            # Fetch every link, score each by similarity to the TARGET (the Connect
            # anchor — Explore will anchor to the seed instead), keep the top-K.
            links = self._link_cache.get_links(current)
            scored = sorted(
                ((link, self._embed_cache.similarity(link, target)) for link in links),
                key=lambda pair: pair[1],
                reverse=True,
            )
            top = scored[: params.top_k]
            # Recorded here, next to the slice it counts, so it covers BOTH exits below
            # (the dead-end yield and the normal one) — these nodes are emitted either
            # way. A set, so a page appearing in two fan-outs still counts once.
            seen.update(link for link, _ in top)

            nodes = [Node(id=link, score=score, depth=depth + 1) for link, score in top]
            edges = [Edge(source=current, target=link) for link, _ in top]

            # The genuine visited check: pick the best link we haven't already been to.
            best = next((link for link, _ in top if link not in visited), None)
            if best is None:
                # Every top candidate is already visited — greedy has nowhere new to
                # go. Show the fan-out, then stop rather than loop.
                yield Step(
                    nodes=nodes,
                    edges=edges,
                    note=f"dead end at {current!r}: all top candidates already visited",
                )
                return

            best_score = next(score for link, score in top if link == best)
            yield Step(
                nodes=nodes,
                edges=edges,
                note=f"{current!r} -> {best!r} (score {best_score:.3f})",
            )

            visited.add(best)
            current = best
            depth += 1
