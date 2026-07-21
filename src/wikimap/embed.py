"""Page-title embeddings and cosine similarity.

Powers both the top-K branching cap (decision C) and feedback's distance estimate
(decision B). Two-layer cached (memory -> disk) keyed by page title: embedding
~300 links per node is the dominant cost, so pay it once per page.
"""
