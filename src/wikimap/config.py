"""Every tunable knob, in one place, as data.

Contract 1: modes and algorithms read their settings from here and never hardcode.
Depth, node caps, branch caps (K=20), beam width, heuristic weights all live here.
Explore mode exists to watch these values reshape the graph.

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
# Read by the Connect algorithms; never hardcoded in them (contract 1). Plain
# constants for now — a pre-run settings UI (post-MVP) will add per-knob bounds and
# pass user-set values in per run rather than mutating these globals. See HISTORY.

# Branching cap: fetch every link, but only keep the top-K by cosine similarity to
# the anchor. Uncapped expansion hits ~27M nodes by depth 3, so the cap itself is
# LOCKED (decision C) — what is locked is the *mechanism* (rank by cosine to the
# anchor, keep the best K) and the ceiling.
#
# Resolved 2026-07-26: 20 is the MAXIMUM, not a fixed value. The settings UI may
# vary K over the range below; it may never exceed 20. This is not a placeholder.
# Caveat on the lower bound: K=0 keeps no candidates at all, so every Connect run
# dead-ends on its first tick. Legal, useless — consider raising the floor to 1
# when these become real constants during the params work.
TOP_K = 20
TOP_K_BOUNDS = (0, 20)  # (min, max) for the settings UI — not yet wired

# Hop limit: how many moves an algorithm may make before giving up. PLACEHOLDER —
# real speedrun paths are usually 3-6 hops; tune once we watch real runs. Kept small
# enough that a wandering greedy search terminates quickly.
MAX_DEPTH = 6
MAX_DEPTH_BOUNDS = (1, 12)  # 0 would forbid moving at all; 12 is well past useful

# Hard ceiling on total candidate nodes emitted across a whole run — the safety net
# so a bad run can't crawl forever even if MAX_DEPTH logic regresses. PLACEHOLDER,
# set comfortably above MAX_DEPTH * TOP_K so depth is the usual limiter, not this.
MAX_NODES = 500
MAX_NODES_BOUNDS = (20, 5000)  # floor of 20 so at least one full tick can emit

# --- A* heuristic knobs (Connect) ---------------------------------------------
# A* scores a frontier page as f = g + W * h, where g is hops already walked and h
# estimates hops remaining. g counts in HOPS, so h must too — raw cosine lives in
# [0, 1] and adding it to a hop count means the heuristic can never outweigh even one
# hop, which silently degrades A* into BFS. Hence:
#
#     h = HEURISTIC_HOP_SCALE * (1 - cosine(page, target))
#
# HEURISTIC_HOP_SCALE is "how many hops away is a page that looks totally unrelated".
# 4.0 is grounded in published Wikipedia path lengths (~3.4-3.9 clicks between
# arbitrary articles), not invented. PLACEHOLDER in the sense that it should be
# calibrated against our own solved runs rather than left at the literature average.
HEURISTIC_HOP_SCALE = 4.0
HEURISTIC_HOP_SCALE_BOUNDS = (0.0, 20.0)

# The weight W. This dial spans the whole spectrum of search behaviour, which is why
# A* is worth building before BFS:
#   W = 0        -> heuristic ignored, pure cost-so-far ordering == breadth-first
#   W = 1        -> balanced A*
#   W very large -> cost-so-far ignored == greedy best-first
# So one algorithm plus this slider demonstrates greedy and BFS as its endpoints.
HEURISTIC_WEIGHT = 1.0
HEURISTIC_WEIGHT_BOUNDS = (0.0, 25.0)

# --- Bidirectional search knobs (Connect BFS) ---------------------------------

# How many backlinks ("what links here") to pull per page for the backward half of
# a bidirectional search. 500 is the MediaWiki API's maximum per request, so this is
# exactly one round trip — the point of the cap. Popular pages have six-figure
# backlink counts and an uncapped fetch would page through them forever.
#
# Known bias, accepted: the API returns backlinks in page-id order, NOT by relevance,
# so capping takes an arbitrary 500 rather than the best 500. Nothing cheap fixes
# this — ranking by relevance would require fetching all of them first, which is the
# thing the cap exists to avoid. Recorded so the BFS results aren't over-trusted.
BACKLINK_LIMIT = 500


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
    max_nodes: int = MAX_NODES
    # A*-only. Greedy ignores these, which is fine — one params object covers every
    # Connect algorithm rather than each growing its own parallel settings type.
    heuristic_weight: float = HEURISTIC_WEIGHT
    hop_scale: float = HEURISTIC_HOP_SCALE

    def __post_init__(self) -> None:
        # object.__setattr__ is how you assign inside a frozen dataclass — normal
        # assignment raises FrozenInstanceError. Legitimate here because __post_init__
        # runs during construction, before anyone can observe the unclamped value.
        object.__setattr__(self, "top_k", _clamp(self.top_k, TOP_K_BOUNDS))
        object.__setattr__(self, "max_depth", _clamp(self.max_depth, MAX_DEPTH_BOUNDS))
        object.__setattr__(self, "max_nodes", _clamp(self.max_nodes, MAX_NODES_BOUNDS))
        object.__setattr__(
            self,
            "heuristic_weight",
            _clamp(self.heuristic_weight, HEURISTIC_WEIGHT_BOUNDS),
        )
        object.__setattr__(
            self, "hop_scale", _clamp(self.hop_scale, HEURISTIC_HOP_SCALE_BOUNDS)
        )
