"""Connect mode: Wikipedia speedrun from page A to page B.

Top-K branching is ranked by similarity to the TARGET (decision C).

STRIPPED DOWN 2026-07-31: `greedy` and `astar` removed (`bfs` was already removed
earlier the same day). `default.py`'s bidirectional beam search is now the ONLY
Connect algorithm — a direct, informed user call, made after live testing kept
showing the same result on hard cross-domain pairs: greedy dead-ended, astar
plateaued for 7+ minutes, and default solved them in seconds by structurally
avoiding both failure modes. Maintaining three approaches was costing more than
the three-way comparison was worth, and it was standing in the way of actually
polishing the one that works. See HISTORY for the full reasoning.

`ALGORITHMS` stays a registry (rather than every caller importing `DefaultConnect`
directly) so a genuinely new algorithm — not a resurrection of one of these two —
could still drop in later without the server or frontend learning anything new.
"""

from wikimap.algorithms.connect.default import DefaultConnect

ALGORITHMS = {
    "default": DefaultConnect,
}

DEFAULT_ALGORITHM = "default"
