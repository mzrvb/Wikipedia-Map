"""FastAPI app: routes, the SSE stream, and static file serving.

Consumes the Step stream from algorithms and forwards it to the browser. Holds no
search logic of its own — contract 2 in its final form: the algorithm yields Steps
knowing nothing about HTTP, this module turns each one into an SSE frame, and the
frontend turns each frame into nodes on a canvas. Three layers, one direction.

Two shape decisions worth knowing:

- **The caches are built once, lazily, in `_algorithm()`.** Once because they're the
  whole point (a shared LinkCache across requests is what stops a re-crawl); lazily
  because importing this module must stay cheap — building them eagerly at import
  would demand USER_AGENT and load an ~80MB model just to run the tests.
- **`_stream` is a plain sync generator, not `async def`.** The fetch layer is
  deliberately synchronous (see CLAUDE.md), so an `async` route would block the whole
  event loop on every Wikipedia call. Handing Starlette a *sync* iterator makes it run
  the iteration in a threadpool instead, which is correct for blocking work and costs
  us nothing at MVP scale.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from wikimap import config
from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.algorithms.connect import ALGORITHMS, DEFAULT_ALGORITHM
from wikimap.config import RunParams

if TYPE_CHECKING:
    # Type-only, same reasoning as algorithms/base.py: _wiki_client() imports
    # WikiClient at call time so importing this module never drags in wikipediaapi.
    from wikimap.wiki.client import WikiClient

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="wikimap")


@lru_cache(maxsize=1)
def _caches():
    """The two long-lived caches, built once and lazily.

    Once because sharing them is the entire point — a fresh LinkCache per request
    would mean re-crawling Wikipedia every time. Lazily (imports inside the function)
    because importing this module must stay cheap: eager construction would demand
    USER_AGENT and load an ~80MB model just to run the tests.

    Split out from `_algorithm` so that every algorithm shares ONE set of caches. If
    the caches were built inside `_algorithm`, switching greedy -> astar would hand
    the new algorithm a cold cache.
    """
    from wikimap.embed import Embedder, EmbeddingCache
    from wikimap.wiki.cache import LinkCache
    from wikimap.wiki.client import WikiClient

    return LinkCache(WikiClient()), EmbeddingCache(Embedder())


@lru_cache(maxsize=1)
def _wiki_client() -> WikiClient:
    """The one WikiClient the page-detail endpoint needs, built lazily.

    Deliberately separate from `_caches()`: that function's LinkCache holds a
    WikiClient for the SEARCH path as a private implementation detail, and reaching
    into it would couple this unrelated endpoint to another class's internals to
    save nothing — WikiClient itself does no caching (LinkCache is the cache), so a
    second instance costs nothing beyond re-reading USER_AGENT. Page detail is a
    rare, user-triggered lookup, not something worth wiring through the disk cache.
    """
    from wikimap.wiki.client import WikiClient

    return WikiClient()


@lru_cache(maxsize=None)
def _algorithm(name: str = DEFAULT_ALGORITHM) -> ConnectAlgorithm:
    """Build (once per name) the shared algorithm instance for `name`.

    `lru_cache` keyed by the name: one GreedyConnect, one AStarConnect, each reused
    across requests. Unbounded maxsize is safe because the key space is the fixed
    ALGORITHMS registry, not user input — the route validates the name before it
    reaches here.

    Annotated as the ABC, not a concrete class: everything below relies only on
    `run`, which is exactly what the base class guarantees. That is what lets a new
    algorithm drop into the registry without the server learning anything about it.
    """
    link_cache, embed_cache = _caches()
    return ALGORITHMS[name](link_cache, embed_cache)


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame.

    The wire format is plain text and dead simple: a `event:` line naming the type, a
    `data:` line holding the payload, then a BLANK line that terminates the frame.
    That trailing "\\n\\n" is the whole protocol — omit it and the browser waits
    forever for a message it already has.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream(
    seed: str,
    target: str,
    params: RunParams,
    algorithm: str = DEFAULT_ALGORITHM,
) -> Iterator[str]:
    """Turn the algorithm's Step stream into SSE frames, one per tick.

    This is the generator chain that makes live drawing work: `run()` yields a Step,
    this yields a frame, Starlette writes it to the socket, the browser paints it —
    and only then does the search resume for the next tick. Nothing is buffered into
    a list at any layer, which is exactly why the graph grows on screen instead of
    appearing all at once at the end.

    `params` is threaded straight through to `run()` rather than stashed anywhere.
    This function is called once per request, so the settings live in this generator's
    own frame — two concurrent runs cannot see each other's.
    """
    yield _sse("status", {"message": f"Searching {seed} → {target} ({algorithm})…"})
    try:
        algo = _algorithm(algorithm)
        for step in algo.run(seed, target, params):
            # asdict() walks the frozen dataclass (and its nested Node/Edge lists)
            # into plain dicts — json.dumps can't serialize a dataclass directly.
            yield _sse("step", asdict(step))
    except Exception as exc:  # noqa: BLE001 - the stream must report, never 500 silently
        # Once streaming has begun the status code is already sent, so an exception
        # can't become an HTTP error — the only way to tell the user is in-band.
        logger.exception("connect run failed: seed=%r target=%r", seed, target)
        yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})
    yield _sse("done", {})


@app.get("/api/config")
def read_config() -> dict:
    """The knobs, read-only. Contract 1 says config owns them; the frontend displays
    them rather than keeping its own copy that could drift out of sync.
    """
    return {
        "top_k": config.TOP_K,
        "max_depth": config.MAX_DEPTH,
        "max_nodes": config.MAX_NODES,
        "heuristic_weight": config.HEURISTIC_WEIGHT,
        "hop_scale": config.HEURISTIC_HOP_SCALE,
        "embedding_model": config.EMBEDDING_MODEL,
        # The registry, so the frontend's algorithm picker is built from what the
        # server actually offers rather than a hardcoded list that could drift.
        "algorithms": sorted(ALGORITHMS),
        "default_algorithm": DEFAULT_ALGORITHM,
        # Bounds so the frontend can build controls without hardcoding ranges —
        # contract 1 applies to the *limits* as much as to the values.
        "bounds": {
            "top_k": list(config.TOP_K_BOUNDS),
            "max_depth": list(config.MAX_DEPTH_BOUNDS),
            "max_nodes": list(config.MAX_NODES_BOUNDS),
            "heuristic_weight": list(config.HEURISTIC_WEIGHT_BOUNDS),
            "hop_scale": list(config.HEURISTIC_HOP_SCALE_BOUNDS),
        },
    }


@app.get("/api/connect")
def connect(
    seed: str = Query(min_length=1, max_length=200),
    target: str = Query(min_length=1, max_length=200),
    top_k: int = Query(
        config.TOP_K, ge=config.TOP_K_BOUNDS[0], le=config.TOP_K_BOUNDS[1]
    ),
    max_depth: int = Query(
        config.MAX_DEPTH, ge=config.MAX_DEPTH_BOUNDS[0], le=config.MAX_DEPTH_BOUNDS[1]
    ),
    max_nodes: int = Query(
        config.MAX_NODES, ge=config.MAX_NODES_BOUNDS[0], le=config.MAX_NODES_BOUNDS[1]
    ),
    heuristic_weight: float = Query(
        config.HEURISTIC_WEIGHT,
        ge=config.HEURISTIC_WEIGHT_BOUNDS[0],
        le=config.HEURISTIC_WEIGHT_BOUNDS[1],
    ),
    hop_scale: float = Query(
        config.HEURISTIC_HOP_SCALE,
        ge=config.HEURISTIC_HOP_SCALE_BOUNDS[0],
        le=config.HEURISTIC_HOP_SCALE_BOUNDS[1],
    ),
    # Literal-style validation via the registry: an unknown name is a 422 here rather
    # than a KeyError deep inside _algorithm.
    algorithm: str = Query(DEFAULT_ALGORITHM, pattern=f"^({'|'.join(sorted(ALGORITHMS))})$"),
) -> StreamingResponse:
    """Stream a Connect run as Server-Sent Events.

    SSE not WebSockets, per the locked stack decision: this is one-way (server pushes
    Steps, browser never replies mid-run), and SSE is plain HTTP with auto-reconnect
    built into the browser. WebSockets would buy bidirectionality we don't need yet.

    The knobs are optional query params defaulting to config's values, so the original
    `?seed=&target=` URL still works. Range checking is FastAPI's job via `ge`/`le` —
    out-of-range values get a 422 here, at the edge, so the algorithm never has to
    know that user input exists. The bounds themselves come from config, not literals.
    """
    params = RunParams( # defined parameters
        top_k=top_k,
        max_depth=max_depth,
        max_nodes=max_nodes,
        heuristic_weight=heuristic_weight,
        hop_scale=hop_scale,
    )
    return StreamingResponse(
        _stream(seed, target, params, algorithm),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells any reverse proxy not to buffer the response. Without it a proxy
            # may hold frames back until the stream closes, silently killing the
            # live-drawing effect that this whole endpoint exists for.
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/page")
def page_detail(title: str = Query(min_length=1, max_length=200)) -> dict:
    """One page's real Wikipedia summary + URL, fetched on demand when a node in the
    graph is clicked. Plain JSON, not SSE — a single synchronous lookup, not a stream.

    A query param, not a `/api/page/{title}` path param: Wikipedia titles can contain
    "/" (e.g. "AC/DC"), which a path segment can't carry safely. `seed`/`target` on
    `/api/connect` already dodge this exact problem the same way.
    """
    result = _wiki_client().get_summary(title)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"message": f"No Wikipedia summary found for {title!r}"},
        )
    return {"title": title, "summary": result["summary"], "url": result["url"]}


# Mounted LAST and at "/" so it acts as the fallback: the /api routes above are
# matched first, and anything else falls through to a file. html=True serves
# index.html for "/" — that's what lets the API and the frontend share one origin
# (no CORS setup needed) on a single uvicorn process.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
