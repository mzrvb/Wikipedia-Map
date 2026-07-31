"""Every tunable knob, in one place, as data.

Contract 1: modes and algorithms read their settings from here and never hardcode.
Depth and branch caps (K=20) live here. Explore mode exists to watch these values
reshape the graph.

Two kinds of thing live here, and the distinction matters:

- **Constants** (`TOP_K`, `MAX_DEPTH`, ...) are the defaults. Read them freely; never
  *mutate* them. They are shared by every request, so writing to one to honour a user's
  setting would let two concurrent runs stomp each other.
- **`RunParams`** is the per-run snapshot. The settings UI produces one of these per
  request and it travels *into* `run()` as an argument, which is what makes concurrent
  runs with different settings safe. Its field defaults come from the constants above,
  so a number is still written down in exactly one place.
"""

from dataclasses import dataclass

# Sentence-transformers model used for page-title embeddings (step 2). Small, fast,
# a standard default for semantic similarity — ~80MB, 384-dim output. Lives here (not
# hardcoded in embed.py) so it's a swappable knob like everything else.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# --- Algorithm / expansion knobs (step 4+) ------------------------------------
# Read by the Connect algorithms; never hardcoded in them (contract 1). These are the
# DEFAULTS: each `*_BOUNDS` pair below is published by `/api/config`, enforced at the
# HTTP edge by FastAPI's `ge`/`le`, and enforced again by `RunParams.__post_init__`.
# Per-run values travel as a `RunParams` argument and never mutate these globals.

# Branching cap: fetch every link, but only keep the top-K by cosine similarity to
# the anchor. Uncapped expansion hits ~27M nodes by depth 3, so the cap itself is
# LOCKED (decision C) — what is locked is the *mechanism* (rank by cosine to the
# anchor, keep the best K) and the ceiling.
#
# Resolved 2026-07-26: 20 is the MAXIMUM, not a fixed value. The settings UI may
# vary K over the range below; it may never exceed 20. This is not a placeholder.
# Floor raised 0 -> 1 on 2026-07-27: K=0 keeps no candidates at all, so every run
# dead-ends on its first tick. Since these bounds are served to the browser, a floor
# of 0 meant the UI actively offered a value guaranteed to fail with no explanation.
TOP_K = 20
TOP_K_BOUNDS = (1, 20)

# Hop limit: how many moves an algorithm may make before giving up. PLACEHOLDER —
# real speedrun paths are usually 3-6 hops; tune once we watch real runs. Kept small
# enough that a wandering greedy search terminates quickly.
MAX_DEPTH = 6
MAX_DEPTH_BOUNDS = (1, 12)  # 0 would forbid moving at all; 12 is well past useful

# --- Bidirectional search knobs (Connect) ---------------------------------------

# How many backlinks ("what links here") to pull per page for the backward half of
# a bidirectional search (used by default.py; formerly also by bfs.py, removed
# 2026-07-31 — see HISTORY). 500 is the MediaWiki API's maximum per request, so this
# is exactly one round trip — the point of the cap. Popular pages have six-figure
# backlink counts and an uncapped fetch would page through them forever.
#
# Known bias, accepted: the API returns backlinks in page-id order, NOT by relevance,
# so capping takes an arbitrary 500 rather than the best 500. Nothing cheap fixes
# this — ranking by relevance would require fetching all of them first, which is the
# thing the cap exists to avoid.
BACKLINK_LIMIT = 500

# --- Title autocomplete (seed/target inputs) -----------------------------------

# How many candidate titles /api/suggest returns per keystroke. Not a RunParams
# field and not published via /api/config's "bounds" — unlike everything else in
# this section, it never reaches an algorithm. Contract 1 is about knobs that
# change what a SEARCH does; this only helps the user land on a real title before
# a search starts at all, same category as BACKLINK_LIMIT being a plain constant
# WikiClient reads directly rather than something threaded through RunParams.
SUGGEST_LIMIT = 8


# --- Per-run settings ---------------------------------------------------------


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    """Works for ints and floats alike — max/min preserve the type they're given."""
    low, high = bounds
    return max(low, min(high, value))


@dataclass(frozen=True)
class RunParams:
    """One run's settings — the per-request snapshot of the knobs above.

    Why this exists rather than reading the module constants directly: the constants
    are a single shared cell. If a request wrote to `config.TOP_K` to honour a user's
    slider, a second request running concurrently (two browser tabs) would read the
    first one's value mid-search. Values that vary per request have to *travel* as
    arguments, so this object is built at the server edge and passed into `run()`.

    `frozen=True` for the same reason `Step` is frozen: once a run has started, its
    settings must not change underneath it.

    Defaults are the module constants, so every number is still written in exactly one
    place — change `TOP_K` above and the default here follows. Note defaults bind at
    import time, which is the behaviour we want: a run gets a stable snapshot rather
    than re-reading a global that might have moved.

    Values are **clamped** to the declared bounds rather than trusted. The server
    already rejects out-of-range query params with a 422, so clamping only catches
    internal misuse — but decision C's ceiling of K=20 is a hard architectural
    invariant, and an invariant enforced only by a docstring is not enforced at all.
    """

    top_k: int = TOP_K
    max_depth: int = MAX_DEPTH

    def __post_init__(self) -> None:
        # object.__setattr__ is how you assign inside a frozen dataclass — normal
        # assignment raises FrozenInstanceError. Legitimate here because __post_init__
        # runs during construction, before anyone can observe the unclamped value.
        object.__setattr__(self, "top_k", _clamp(self.top_k, TOP_K_BOUNDS))
        object.__setattr__(self, "max_depth", _clamp(self.max_depth, MAX_DEPTH_BOUNDS))
