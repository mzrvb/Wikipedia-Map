"""Every tunable knob, in one place, as data.

Contract 1: modes and algorithms read their settings from here and never hardcode.
Depth, node caps, branch caps (K=20), beam width, heuristic weights all live here.
Explore mode exists to watch these values reshape the graph.
"""

# Sentence-transformers model used for page-title embeddings (step 2). Small, fast,
# a standard default for semantic similarity — ~80MB, 384-dim output. Lives here (not
# hardcoded in embed.py) so it's a swappable knob like everything else.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
