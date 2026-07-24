"""Connect: greedy best-first on the semantic heuristic.

Ported from ../Wikipedia Speedrun/greedy_search.py. That version's loop guard is
dead code — do not carry it over; write a real visited check.

The algorithm: from the seed, repeatedly hop to the single unvisited neighbour that
looks *closest to the target* — where "close" is cosine similarity between page-title
embeddings (decision B), and "neighbour" is capped to the top-K links by that same
score (decision C). Pure greedy: it commits to the local best every tick and never
backtracks. It reads its knobs from `config` (contract 1) and yields a `Step` per
tick (contract 2); it knows nothing of the renderer or transport.

Why the visited check is load-bearing and not optional: the highest-similarity
neighbour of a page is very often the page you just came from (they're semantically
adjacent). Without tracking visited nodes, greedy ping-pongs between two pages
forever. The predecessor "guarded" against this with code that never actually ran —
the one bug we refuse to carry over.
"""

from collections.abc import Iterator

from wikimap import config
from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.graph.contracts import Edge, Node, Step


class GreedyConnect(ConnectAlgorithm):
    """Greedy best-first Connect search. See module docstring."""

    def run(self, seed: str, target: str) -> Iterator[Step]:
        visited = {seed}
        current = seed
        depth = 0
        node_count = 1  # the seed itself

        # Emit the seed first so it's born with real attributes. If we let the first
        # tick's edges create it implicitly, networkx would conjure it as a blank node
        # (no score/depth) — edges auto-create missing endpoints. Nodes-before-edges.
        yield Step(
            nodes=[Node(id=seed, score=self._embed_cache.similarity(seed, target), depth=0)],
            note=f"start: {seed!r} (target {target!r})",
        )

        while current != target:
            if depth >= config.MAX_DEPTH or node_count >= config.MAX_NODES:
                yield Step(
                    note=f"stopped: hit cap at {current!r} "
                    f"(depth {depth}, {node_count} nodes)"
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
            top = scored[: config.TOP_K]

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
            node_count += len(top)
            current = best
            depth += 1
