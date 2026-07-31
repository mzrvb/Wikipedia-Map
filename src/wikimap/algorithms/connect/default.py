"""Connect: bidirectional beam search — the default algorithm.

REDESIGNED 2026-07-30, replacing the turn-based priority-queue version. That version
alternated forward/backward expansion by comparing each side's current best
`f = g + W*h` and letting the lower one go — proven live, on a real search
("israel" -> "john f kennedy"), to let one side monopolize every tick: backward's
frontier is seeded once and its `f` never updates until it's actually picked, so a
forward side that keeps finding decent-scoring candidates can keep winning that
comparison indefinitely — backward can go from turn zero to never. `bfs.py` (removed
2026-07-31 — see HISTORY) fought this exact class of bug twice in its own history
(comparing raw queue length, then whole-frontier size, both proven wrong live) and
landed on "the only safe comparison is depth LEVEL itself." The old default.py
compared `f`, which is worse than either of `bfs.py`'s two already-rejected attempts —
`f` isn't even monotonic the way queue length or frontier size at least were.

THE FIX ISN'T A BETTER COMPARISON, IT'S REMOVING THE COMPARISON. Rather than pick a
side each tick, every tick now expands BOTH sides' ENTIRE current frontier at once:
fetch every link (forward) / backlink (backward) reachable from wherever each side's
wavefront currently sits, score them all, and keep each side's own top-K. There is no
"whose turn" question left to get wrong, because there is no turn. This borrowed
`bfs.py`'s ply-synchronized shape (one full wavefront advances per tick), with
decision C's top-K cosine cap layered back on to keep it cheap and heuristic-guided
instead of exhaustive — that exhaustive, ground-truth job was `bfs.py`'s alone, and
no algorithm here does it anymore now that `bfs.py` is gone (removed 2026-07-31, too
slow to be worth the guarantee — see HISTORY).

PRUNING STAYS PER-SIDE, NOT POOLED — a decision, not an oversight. Forward's
candidates are ranked by similarity to the TARGET; backward's by similarity to the
SEED (decision C, unchanged). Those are two different questions on two different
anchors, not one shared scale. Pooling both sides into a single top-K cut would let
whichever side's neighbourhood happens to score higher THIS TICK crowd out the
other's slots — the exact starvation shape this redesign exists to eliminate, just
relocated from turn-selection into the prune step instead of removed. So it's top-K
forward AND (independently) top-K backward, every tick, always.

REOPENING (astar.py's fix, and the old default.py's) IS GONE, AND THAT'S A
SIMPLIFICATION, NOT A LOST FEATURE. Reopening existed to handle a route that looked
cheap enough to close a page early, only for a genuinely cheaper route to turn up
later — a scenario that needed a persistent priority queue where "later" could mean
"a lower-cost path processed after a higher-cost one already closed that page." Here,
depth increases by exactly one, on both sides, every tick. A link is only ever
first-seen in the ply where SOME survivor of the current frontier reaches it, and
that ply number can only go up. First discovery already IS the best depth this
design's pruning can produce — there is nothing to reopen.

`heuristic_weight` (W) and `hop_scale` are no longer read here. They existed to make
`f = g + W*h` comparable ACROSS a frontier holding candidates at different depths —
the turn-selection heap. Every candidate considered in a single tick now shares the
same depth (this ply's), so blending in `g` compares a constant against itself; pure
similarity ranking is already the right order. `astar.py` still uses both — this file
just doesn't need them, same as `greedy.py` never reads `config` once params landed.

MEETING DETECTION checks three sources each tick, not one: a side's new discoveries
against the OTHER side's pre-existing depths (as before), PLUS — new in this design —
a side's new discoveries against the OTHER side's discoveries from this SAME tick,
since both sides genuinely move at once now, and two independent same-tick
discoveries of one page are a real meeting, not something to defer a tick to notice.

TERMINATION: stop at the first ply where any meeting is found, reporting the cheapest
one if that ply produced more than one (trivial — the whole ply's candidates are
already in hand). This replaces the old default.py's `best_total`/keep-hunting-
across-many-ticks logic, which existed to guard against a naive "stop at the very
first contact" bug in a one-node-at-a-time model. That guard matters less once a
whole ply's worth of candidates is already gathered and compared together before any
decision is made — the same simplification `bfs.py` used to make (it stopped firing
further fetches the instant a ply produced a meeting, reasoning nothing later in that
SAME ply can beat it). Still NOT provably optimal: cosine is a guess on both sides,
and pruning can discard a genuinely-shorter route before it's ever explored. That is
decision C's accepted cost, same as `astar.py` and `greedy.py`. Nothing in this
codebase can currently prove otherwise — `bfs.py` was the only ground truth, and it
was removed 2026-07-31 (too slow relative to that guarantee; see HISTORY).

`max_depth` used to mean "per side," matching `bfs.py`, which is now moot — there is
no other bidirectional algorithm left to compare the convention against. Still
trivially "per side" here, since both sides always advance together, so "per side"
and "total ticks" are the same number by construction.

NO `max_nodes` CHECK — dropped 2026-07-30, matching greedy.py/astar.py the same day
(see HISTORY). Every ply is already capped to top-K per side, so the worst case
across the whole run is bounded by roughly `2 * max_depth * top_k` without a separate
node cap doing anything greedy/astar/default's own caps don't already do. `max_nodes`
stays on `RunParams` for `astar.py` alone (reinstated there 2026-07-31, see HISTORY
and config.py) — `bfs.py` used to be the other reader, deliberately having no
per-tick cap at all (every link expanded, unranked — that's what made it the ground
truth), but it's gone now, and astar remains the one algorithm that can run away
without a node cap.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.config import RunParams
from wikimap.graph.contracts import Edge, Node, Step


class DefaultConnect(ConnectAlgorithm):
    """Bidirectional, ply-synchronized, top-K-pruned beam search. See module docstring."""

    def run(
        self, seed: str, target: str, params: RunParams | None = None
    ) -> Iterator[Step]:
        if params is None:
            params = RunParams()

        if seed == target:
            yield Step(
                nodes=[Node(id=seed, score=None, depth=0)],
                note=f"reached {target!r} in 0 hops: {seed!r}",
                path=[seed],
            )
            return

        # Cosine is symmetric — one lookup serves as both endpoints' display score
        # on the start Step. Not used for ranking (see module docstring: no more
        # f = g + W*h), purely informational.
        seed_target_similarity = self._embed_cache.similarity(seed, target)

        forward_depth = {seed: 0}
        forward_parent: dict[str, str] = {}
        forward_frontier = [seed]

        backward_depth = {target: 0}
        backward_parent: dict[str, str] = {}
        backward_frontier = [target]

        yield Step(
            nodes=[
                Node(id=seed, score=seed_target_similarity, depth=0),
                Node(id=target, score=seed_target_similarity, depth=0),
            ],
            note=f"start: {seed!r} <-> {target!r} (bidirectional beam, K={params.top_k})",
        )

        depth = 0
        while (forward_frontier or backward_frontier) and depth < params.max_depth:
            depth += 1

            # Fetch every frontier node's links/backlinks concurrently (threads —
            # these are blocking network calls, and Python releases the GIL while
            # a thread waits on socket I/O, so this genuinely overlaps the waiting
            # instead of queuing one page's fetch behind the last). Forward and
            # backward parents are always disjoint here (a shared title would have
            # already been caught as a same-tick meeting last iteration and ended
            # the run), so no two threads ever race on the same cache entry.
            with ThreadPoolExecutor(
                max_workers=max(len(forward_frontier) + len(backward_frontier), 1)
            ) as pool:
                forward_fetches = {
                    parent: pool.submit(self._link_cache.get_links, parent)
                    for parent in forward_frontier
                }
                backward_fetches = {
                    parent: pool.submit(self._link_cache.get_backlinks, parent)
                    for parent in backward_frontier
                }
                forward_links_by_parent = {
                    parent: future.result() for parent, future in forward_fetches.items()
                }
                backward_links_by_parent = {
                    parent: future.result() for parent, future in backward_fetches.items()
                }

            forward_candidates = [
                (link, parent)
                for parent in forward_frontier
                for link in forward_links_by_parent[parent]
                if link not in forward_depth
            ]
            backward_candidates = [
                (link, parent)
                for parent in backward_frontier
                for link in backward_links_by_parent[parent]
                if link not in backward_depth
            ]

            # Batched, not one similarity() call per candidate — the whole ply's
            # unseen titles go into a single model.encode(list) forward pass.
            forward_scores = self._embed_cache.similarity_many(
                [link for link, _ in forward_candidates], target
            )
            backward_scores = self._embed_cache.similarity_many(
                [link for link, _ in backward_candidates], seed
            )

            forward_survivors = _rank_and_cap(
                (
                    (link, parent, forward_scores[link])
                    for link, parent in forward_candidates
                ),
                params.top_k,
            )
            backward_survivors = _rank_and_cap(
                (
                    (link, parent, backward_scores[link])
                    for link, parent in backward_candidates
                ),
                params.top_k,
            )

            forward_links = {link for link, _, _ in forward_survivors}
            backward_links = {link for link, _, _ in backward_survivors}
            # Three sources, all real meetings: a side's new find landing on a page
            # the OTHER side already knew (from an earlier ply), in either
            # direction, plus both sides independently finding the same page in
            # this SAME tick.
            meetings = (
                (forward_links & set(backward_depth))
                | (backward_links & set(forward_depth))
                | (forward_links & backward_links)
            )

            new_nodes, new_edges = [], []
            for link, parent, similarity in forward_survivors:
                forward_depth[link] = depth
                forward_parent[link] = parent
                new_nodes.append(Node(id=link, score=similarity, depth=depth))
                new_edges.append(Edge(source=parent, target=link))
            for link, parent, similarity in backward_survivors:
                backward_depth[link] = depth
                backward_parent[link] = parent
                new_nodes.append(Node(id=link, score=similarity, depth=-depth))
                new_edges.append(Edge(source=link, target=parent))

            yield Step(
                nodes=new_nodes,
                edges=new_edges,
                # "round", not "ply" — the internal reasoning in this module's
                # docstring still says "ply" (borrowed from bfs.py's own history,
                # accurate to how that design evolved), but that word implies
                # one-side-at-a-time turn-taking to a reader who hasn't read the
                # docstring, which is backwards: both sides advance in this exact
                # same tick, together. The user-facing text says what it looks
                # like, not where the term came from.
                note=f"round {depth}: {len(forward_survivors)} fwd "
                f"+ {len(backward_survivors)} bwd",
            )

            if meetings:
                # Computed AFTER the commit loops above, so both dicts already
                # reflect this tick's own discoveries — every meeting candidate's
                # depth on both sides is guaranteed to be present.
                meeting = min(
                    meetings, key=lambda m: forward_depth[m] + backward_depth[m]
                )
                path = _reconstruct(
                    forward_parent, backward_parent, seed, target, meeting
                )
                yield Step(
                    note=f"reached {target!r} in {len(path) - 1} hops "
                    f"(met at {meeting!r}): {' -> '.join(path)}",
                    path=path,
                )
                return

            forward_frontier = [link for link, _, _ in forward_survivors]
            backward_frontier = [link for link, _, _ in backward_survivors]

        yield Step(note=f"exhausted: no route to {target!r} within the caps")


def _rank_and_cap(
    candidates: Iterator[tuple[str, str, float]], k: int
) -> list[tuple[str, str, float]]:
    """Dedup a ply's candidates to each link's best-scoring parent edge, then keep
    the top `k` by similarity.

    A link can now be discovered from more than one frontier node in the same ply,
    since a whole frontier expands per tick instead of one node — that duplication
    never existed in the old one-node-per-tick design.
    """
    best: dict[str, tuple[str, float]] = {}
    for link, parent, similarity in candidates:
        if link not in best or similarity > best[link][1]:
            best[link] = (parent, similarity)
    ranked = sorted(
        ((link, parent, similarity) for link, (parent, similarity) in best.items()),
        key=lambda triple: triple[2],
        reverse=True,
    )
    return ranked[:k]


def _reconstruct(
    forward_parent: dict[str, str],
    backward_parent: dict[str, str],
    seed: str,
    target: str,
    meeting: str,
) -> list[str]:
    """Stitch the seed->meeting and meeting->target halves into one path.

    The forward half is walked backwards (meeting -> ... -> seed) then reversed;
    the backward half is already in real edge-direction order and needs no reversal.
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
