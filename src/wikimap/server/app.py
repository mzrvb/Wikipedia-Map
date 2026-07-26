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
from dataclasses import asdict #
from functools import lru_cache # higher order functions
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from wikimap import config
from wikimap.algorithms.base import ConnectAlgorithm
from wikimap.algorithms.connect.greedy import GreedyConnect
from wikimap.config import RunParams

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="wikimap")


@lru_cache(maxsize=1)
def _algorithm() -> ConnectAlgorithm:
    """Build the one shared GreedyConnect, with its two long-lived caches.

    `lru_cache(maxsize=1)` on a no-argument function is the compact idiom for
    "compute once, reuse forever" — the same memoisation trick as
    `Embedder._get_model`, just spelled with a decorator instead of an `if is None`.
    The imports sit inside the function for the same reason the model load does:
    nothing heavy should happen merely because someone imported this module.

    Annotated as the ABC, not GreedyConnect: everything below only relies on `run`,
    which is exactly what the base class guarantees. Swapping in AStarConnect later
    changes this one line and nothing else.
    """
    from wikimap.embed import Embedder, EmbeddingCache
    from wikimap.wiki.cache import LinkCache
    from wikimap.wiki.client import WikiClient

    return GreedyConnect(LinkCache(WikiClient()), EmbeddingCache(Embedder()))


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame.

    The wire format is plain text and dead simple: a `event:` line naming the type, a
    `data:` line holding the payload, then a BLANK line that terminates the frame.
    That trailing "\\n\\n" is the whole protocol — omit it and the browser waits
    forever for a message it already has.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n" # blank link at the end marks msg completion for delivery


def _stream(seed: str, target: str, params: RunParams) -> Iterator[str]: # draws the actual frames of the generator
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
    yield _sse("status", {"message": f"Searching {seed} → {target}…"})
    try:
        algo = _algorithm()
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
        "embedding_model": config.EMBEDDING_MODEL,
        # Bounds so the frontend can build controls without hardcoding ranges —
        # contract 1 applies to the *limits* as much as to the values.
        "bounds": {
            "top_k": list(config.TOP_K_BOUNDS),
            "max_depth": list(config.MAX_DEPTH_BOUNDS),
            "max_nodes": list(config.MAX_NODES_BOUNDS),
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
    params = RunParams(top_k=top_k, max_depth=max_depth, max_nodes=max_nodes)
    return StreamingResponse(
        _stream(seed, target, params),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells any reverse proxy not to buffer the response. Without it a proxy
            # may hold frames back until the stream closes, silently killing the
            # live-drawing effect that this whole endpoint exists for.
            "X-Accel-Buffering": "no",
        },
    )


# Mounted LAST and at "/" so it acts as the fallback: the /api routes above are
# matched first, and anything else falls through to a file. html=True serves
# index.html for "/" — that's what lets the API and the frontend share one origin
# (no CORS setup needed) on a single uvicorn process.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
