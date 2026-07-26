"""Shared ABC(s) for all algorithms.

Every algorithm is a generator of Steps (contract 2) that reads its knobs from
config (contract 1). It never draws and never touches the transport.

`ConnectAlgorithm` is the shared shape for the Connect-mode pathfinders (greedy,
astar, bfs). It fixes the API decided in step 4 (HISTORY, "Option A"): the caches
an algorithm needs are injected once at construction — long-lived and shared, the
same dependency-injection shape `LinkCache(client)` and `EmbeddingCache(embedder)`
already use — while the job (seed -> target) arrives per call. The ABC guarantees
every sibling algorithm exposes the identical `run`, so the server can build any of
them and stream `run(...)` without knowing which one it holds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod #
from collections.abc import Iterator # Iterator from standard python library (collections.abc)
from typing import TYPE_CHECKING

from wikimap.config import RunParams
from wikimap.graph.contracts import Step

if TYPE_CHECKING:
    # Type-only imports: the ABC just stores whatever caches it's handed, so it
    # needs the names for annotations but not at runtime. Guarding them keeps
    # importing an algorithm from dragging in wikipediaapi (via LinkCache/WikiClient)
    # or forcing a model load — the heavy deps only arrive when a cache is built.
    from wikimap.embed import EmbeddingCache
    from wikimap.wiki.cache import LinkCache


class ConnectAlgorithm(ABC):
    """Base shape for a Connect pathfinder. Declares; runs nothing itself.

    Subclasses (GreedyConnect, AStarConnect, ...) are siblings that each *replace*
    `run` — they do not wrap each other. `@abstractmethod` forbids instantiating this
    base directly and forces every subclass to provide its own `run`.
    """

    def __init__(self, link_cache: LinkCache, embed_cache: EmbeddingCache) -> None:
        self._link_cache = link_cache
        self._embed_cache = embed_cache

    @abstractmethod
    def run(
        self, seed: str, target: str, params: RunParams | None = None
    ) -> Iterator[Step]:
        """Yield one Step per tick until seed reaches target (or a cap trips).

        `params` carries this run's knob settings. It is an argument rather than
        constructor state because the caches above are shared infrastructure that
        outlives any single request, while settings vary *per request* — two browser
        tabs searching with different K must not see each other's values. Defaulting
        to None (meaning "use config's defaults") keeps every existing call site and
        test working unchanged.

        Abstract and inert on purpose — the body declares nothing runs. Note it is
        NOT written as a generator (no `yield` here): a `yield` would turn this into a
        real empty generator, muddying "the base executes nothing." Subclasses supply
        the actual generator.
        """
        ...
