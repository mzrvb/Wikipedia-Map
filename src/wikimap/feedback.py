"""Chess-style move grading — the ONLY grader in the codebase.

Contract 3: every move (AI or human) produces a MoveEvaluation
{from, to, grade, delta, note}, grade in
{Brilliant, Best, Good, Inaccuracy, Mistake, Blunder}.
`delta` is the change in estimated distance-to-target (semantic, per decision B).
Nothing else assigns grades; the UI only renders them.

Grading is RANK-based, not an absolute cosine threshold. "How good was this move"
only means something relative to what was actually available from that page — a
0.3-similarity link can be the best (or only) option on one page and a lazy pick on
another. So a move is graded by where its chosen page ranks, by similarity to the
target, among every real (ns0) link the page it was played from actually offered.
Reaching the target directly is graded Brilliant unconditionally, regardless of
rank — finding the winning move is always the best outcome a rank comparison could
ever express, so there's nothing to compare it against.

The five PCTL boundaries below are a PLACEHOLDER, the same status as config.py's
MAX_DEPTH: reasonable-looking guesses, not yet tuned against real human play. See
HISTORY before changing them without live data to justify it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wikimap.graph.contracts import Grade, MoveEvaluation

if TYPE_CHECKING:
    from wikimap.embed import EmbeddingCache
    from wikimap.wiki.cache import LinkCache

# Fraction of a page's ranked, available links a move must fall within (0.0 = the
# single best option) to earn each grade. Best and Brilliant are handled as special
# cases outside this table (rank 0, and "reached the target", respectively).
_GOOD_PCTL = 0.25
_INACCURACY_PCTL = 0.5
_MISTAKE_PCTL = 0.75


def evaluate_move(
    from_: str,
    to: str,
    target: str,
    link_cache: LinkCache,
    embed_cache: EmbeddingCache,
) -> MoveEvaluation:
    """Grade one committed move from `from_` to `to`, aiming at `target`.

    `link_cache`/`embed_cache` are the same shared, long-lived caches every
    algorithm already uses (Option A injection) — grading a move costs nothing new
    to fetch when the page was just rendered for the player to click through.
    """
    before = embed_cache.similarity(from_, target)
    after = embed_cache.similarity(to, target)
    delta = after - before

    if to == target:
        return MoveEvaluation(
            from_=from_,
            to=to,
            grade=Grade.BRILLIANT,
            delta=delta,
            note=f"reached {target!r}",
        )

    # Every real link `from_` offered, ranked by similarity to the target — the
    # same top-K ranking default.py uses to pick candidates, reused here to judge
    # one that was already picked. Not restricted to top-K: the player could see
    # (and click) any of the page's ns0 links, not just the algorithm's top 20.
    available = link_cache.get_links(from_)
    scores = embed_cache.similarity_many(available, target)
    ranked_titles = sorted(scores, key=lambda title: scores[title], reverse=True)

    n = len(ranked_titles)
    if to in ranked_titles:
        rank = ranked_titles.index(to)
        percentile = rank / max(n - 1, 1)
    else:
        # Defensive only: a real caller only ever grades a move the player was
        # shown as a clickable (ns0, from this exact page) link, so `to` should
        # always be in `available`. Treat an out-of-band title as the worst case
        # rather than crashing the grading of an otherwise-finished run.
        rank = n
        percentile = 1.0

    if percentile == 0:
        grade = Grade.BEST
    elif percentile <= _GOOD_PCTL:
        grade = Grade.GOOD
    elif percentile <= _INACCURACY_PCTL:
        grade = Grade.INACCURACY
    elif percentile <= _MISTAKE_PCTL:
        grade = Grade.MISTAKE
    else:
        grade = Grade.BLUNDER

    return MoveEvaluation(
        from_=from_,
        to=to,
        grade=grade,
        delta=delta,
        note=f"{grade.value} — ranked {rank + 1} of {n} available links",
    )
