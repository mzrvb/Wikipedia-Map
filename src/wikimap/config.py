"""Every tunable knob, in one place, as data.

Contract 1: modes and algorithms read their settings from here and never hardcode.
Depth, node caps, branch caps (K=20), beam width, heuristic weights all live here.
Explore mode exists to watch these values reshape the graph.
"""

# Sentence-transformers model used for page-title embeddings (step 2). Small, fast,
# a standard default for semantic similarity — ~80MB, 384-dim output. Lives here (not
# hardcoded in embed.py) so it's a swappable knob like everything else.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# --- Algorithm / expansion knobs (step 4+) ------------------------------------
# Read by the Connect algorithms; never hardcoded in them (contract 1). Plain
# constants for now — a pre-run settings UI (post-MVP) will add per-knob bounds and
# pass user-set values in per run rather than mutating these globals. See HISTORY.

# Branching cap: fetch every link, but only keep the top-K by cosine similarity to
# the anchor. LOCKED at 20 (decision C) — uncapped expansion hits ~27M nodes by
# depth 3. This is not a placeholder; the other two below are.
TOP_K = 20

# Hop limit: how many moves an algorithm may make before giving up. PLACEHOLDER —
# real speedrun paths are usually 3-6 hops; tune once we watch real runs. Kept small
# enough that a wandering greedy search terminates quickly.
MAX_DEPTH = 6

# Hard ceiling on total candidate nodes emitted across a whole run — the safety net
# so a bad run can't crawl forever even if MAX_DEPTH logic regresses. PLACEHOLDER,
# set comfortably above MAX_DEPTH * TOP_K so depth is the usual limiter, not this.
MAX_NODES = 500
