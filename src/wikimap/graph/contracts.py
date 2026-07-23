"""The load-bearing data shapes: Step (contract 2) and MoveEvaluation (contract 3).

Pure data — this module imports nothing from the rest of the project, on purpose.
Everything depends on these shapes (algorithms emit Steps, feedback emits
MoveEvaluations, the server serializes both, the frontend renders them), so if this
file imported algorithms or the graph you'd get an import cycle. Contracts sit at the
bottom of the dependency stack and point at nobody.

Kept separate from model.py because these shapes are consumed all over the codebase,
while the networkx wrapper in model.py is only one of their consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Grade(str, Enum):
    """The six move grades (contract 3). Inheriting from `str` means each member IS
    a string ("Best" == Grade.BEST), so it serializes straight to JSON for SSE with
    no conversion — the frontend receives the plain word.

    An Enum, not free-form strings, so a typo like "Brillint" is impossible: the set
    of grades is closed and named. feedback.py (the only grader) decides which one a
    move earns; nothing here knows the thresholds — that logic lives behind contract 3.
    """

    BRILLIANT = "Brilliant"
    BEST = "Best"
    GOOD = "Good"
    INACCURACY = "Inaccuracy"
    MISTAKE = "Mistake"
    BLUNDER = "Blunder"


@dataclass(frozen=True)
class Node:
    """One node in a Step's payload. `id` is the page title — the same string used as
    the networkx node id AND as the cache key in wiki/ and embed/. One identity for a
    page everywhere (decision: title as id).

    frozen=True makes this a read-only value object: once an algorithm emits a node it
    can't be mutated out from under the renderer. score/depth are optional because not
    every step carries them (e.g. the seed node has no similarity score yet).
    """

    id: str
    score: float | None = None  # cosine similarity to the anchor (target in Connect, seed in Explore)
    depth: int | None = None  # hops from the seed


@dataclass(frozen=True)
class Edge:
    """A directed link source -> target. Directed because a Wikipedia link is one-way:
    "Cat" linking to "Astronomy" does NOT imply the reverse. That directionality is the
    whole reason model.py wraps a DiGraph and not a plain Graph.
    """

    source: str
    target: str


@dataclass(frozen=True)
class Step:
    """Contract 2: what one tick of an algorithm added to the graph. Algorithms yield a
    stream of these; the server streams them over SSE; the frontend applies them to
    vis-network. The algorithm never learns the renderer or transport exists.

    Note: frozen freezes the *fields*, not the list contents — you still shouldn't mutate
    a Step's `nodes` list after construction. Build the lists first, then wrap them.
    """

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class MoveEvaluation:
    """Contract 3: the grade for a single move (AI or human). The UI renders this and
    nothing else assigns grades.

    `from_` has a trailing underscore because `from` is a Python keyword and can't be a
    field name (PEP 8's convention for exactly this clash). When this is serialized for
    the frontend, that maps back to a plain "from" key. `delta` is the change in the
    semantic distance-to-target estimate (decision B); positive = moved closer.
    """

    from_: str
    to: str
    grade: Grade
    delta: float
    note: str = ""
