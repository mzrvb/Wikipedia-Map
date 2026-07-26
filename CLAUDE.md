# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read [`HISTORY.md`](HISTORY.md) before starting work.** This file says what the rules
*are*; `HISTORY.md` says *why* they are that way, which decisions were reversed, and which
values are placeholders. It also carries the open questions that STATUS only summarizes.
Update it alongside this file — see [Working practice](#working-practice).

## STATUS

**Roadmap step 1 (data layer) — done.** `wiki/client.py` (ns0 filtering, UA, retry) and
`wiki/cache.py` (memory → disk two-layer cache) are implemented and tested — 7 tests green,
`ruff check` clean. Venv exists at `.venv`, deps installed.

**Roadmap step 2 (embeddings + scoring) — done.** `embed.py` implements `cosine_similarity`,
`Embedder` (sole importer of sentence_transformers, lazy model load), and `EmbeddingCache`
(memory → disk → compute, keyed by title, same shape as `wiki/cache.py`). Model name lives in
`config.EMBEDDING_MODEL`. 14 fast tests green + 1 `slow`-marked real-model proof (related pages
score higher than unrelated); `ruff check` clean. `numpy` added as an explicit dep.

**Roadmap step 3 (graph model + contracts) — done.** The contracts (contracts 2 and 3) live in
`graph/contracts.py`, split out from `graph/model.py` because they're consumed all over the
codebase while the wrapper is just one consumer: `Grade` (str-Enum, six values), `Node`/`Edge`,
`Step`, and `MoveEvaluation` (`from_` trailing-underscore since `from` is a keyword). `graph/model.py`
holds `WikiGraph`, a thin `networkx.DiGraph` wrapper (directed — links are one-way) whose only mutator
is `apply(step)`. 21 fast tests green (7 new in `test_graph.py`), `ruff check` clean. No new deps —
`networkx>=3.3` was already declared.

**Roadmap step 4 (first algorithm emitting Steps) — done.** `config.py` gained the algorithm knobs
(`TOP_K=20` locked, `MAX_DEPTH`/`MAX_NODES` placeholders). `algorithms/base.py` holds the
`ConnectAlgorithm` ABC (Option A: caches injected in `__init__`, `run(seed, target) -> Iterator[Step]`).
`algorithms/connect/greedy.py` implements `GreedyConnect` — greedy best-first, scoring links by cosine
similarity to the target (decision C), capped to TOP_K, with a genuine `visited` check (the predecessor's
dead loop guard, not ported). 30 fast tests green (9 new in `test_greedy.py`), `ruff check` clean. No new deps.

**Roadmap step 6 (per-run params) — done.** `config.RunParams` is a frozen dataclass whose defaults
come from the module constants and whose `__post_init__` clamps every field to its `*_BOUNDS` — that
clamp is what enforces decision C's K≤20 ceiling against *any* caller, not just HTTP ones.
`ConnectAlgorithm.run` and `GreedyConnect.run` take `params: RunParams | None = None` (built inside
the function, never as a default argument value); `greedy.py` no longer reads `config` at all.
`/api/connect` accepts `top_k`/`max_depth`/`max_nodes` as optional query params validated by
`Query(ge=…, le=…)` against the same bounds, and `/api/config` publishes those bounds so the
frontend's number inputs — which ship disabled and value-less — are filled entirely from the server.
59 fast tests green (15 new), `ruff check` clean. Live-proven: `top_k` 20/5/2 yields exactly
[1,20,20,20,20] / [1,5,…] / [1,2,…] nodes per tick, `max_depth=2` trips the cap, `top_k=21` → 422.

**Roadmap step 5 (the server: FastAPI + SSE) — done. MVP is working end-to-end.** `server/app.py`
holds the app: `GET /api/connect?seed=&target=` streams `GreedyConnect.run(...)` as SSE (one `step`
frame per tick, plus `status`/`error`/`done`), `GET /api/config` exposes the knobs read-only, and
`StaticFiles(html=True)` is mounted last at `/` so API routes match first and the frontend shares
one origin (no CORS). The caches are built **once and lazily** via `@lru_cache(maxsize=1)` on
`_algorithm()` — lazily so importing the module needs neither `USER_AGENT` nor the model, which is
what keeps the tests fast. `_stream` is a **sync** generator on purpose: the fetch layer is
synchronous, so Starlette runs it in a threadpool instead of blocking the event loop. Frontend is
`static/{index.html,app.js,style.css}` — vanilla JS, vis-network via CDN script tag, no build step.
38 fast tests green (8 new in `test_server.py`), `ruff check` clean. No new deps.

Proven live, not just unit-tested: `Cat → Astronomy` solved in 4 hops
(`Science (journal)` → `Spiral nebulae` → `Galactic astronomy`), score climbing 0.460 → 1.000, 81
nodes / 80 edges, top-K holding at exactly 20 per tick. Frames arrive **incrementally** (a cold
`Banana → Quantum mechanics` run delivered at +0.00/+5.71/+6.27/+10.17s), which is the live-drawing
guarantee. Cold run ~80s, warm re-run <0.01s — the two-layer cache doing its job.

**Roadmap replanned 2026-07-26 — finish Connect before starting Explore.** The brief puts the
Explore settings UI at step 6 and the rest of Connect at step 7; that order is reversed. Connect is
the only mode that exists, so completing it yields one coherent mode instead of two half-modes, and
each new Connect algorithm proves the shared pieces before Explore inherits them. Next, in order:

1. ~~**Per-run params.**~~ **Done 2026-07-26.** `RunParams` (frozen dataclass in `config.py`,
   defaults from the constants, clamped to bounds in `__post_init__`) is passed as
   `run(seed, target, params=None)` — *not* constructor state, so the `@lru_cache` singleton and its
   warm caches survive and concurrent runs can't stomp each other. Bounds are published via
   `/api/config` and the frontend's controls are built from them. `TOP_K = 20` is a **ceiling, not a
   fixed value** (`TOP_K_BOUNDS`); decision C locks the mechanism and the maximum.
2. **`connect/astar.py`**, then **`connect/bfs.py`** (in that order — see HISTORY for why BFS is
   neither cheap nor the ground-truth baseline the brief implies). A* must rescale cosine into hop
   units before adding it to `g` (`h = LAMBDA * (1 - cos)`, `f = g + W * h`) or it silently
   degenerates into BFS. BFS must be **bidirectional** and must not be cosine-capped.
   `LinkCache.get_backlinks` (done, 2026-07-26) is the data layer it needs.
3. **Explore** (`explore/bfs.py`, `explore/beam.py`) only once Connect is complete.

**Every step must be non-destructive:** existing tests stay green without being edited, new
parameters arrive with defaults, `/api/config` only gains fields, existing URLs keep working.
(Held so far. Backlinks: +6 tests, none edited. Params: +15 tests, no assertion changed — only two
test *doubles* gained `params=None` to match the new `run` signature. 59 fast tests green.)

**No shared base above Connect and Explore yet.** A parent `Algorithm` class holding `__init__` and
an anchor-parameterised ranking helper was proposed and deliberately deferred until Connect is
entirely done — generalising from one mode is a guess. `ConnectAlgorithm` stays the only base.

Every other module under `src/wikimap/` beyond `wiki/`, `embed.py`, `graph/`, `algorithms/`, and
`server/` remains a placeholder holding only a docstring that states that file's responsibility
(astar/bfs/explore not yet built).

The authoritative plan remains `~/Downloads/wikimap_brief.md`.

Update this section after each roadmap step.

## What this is

A locally hosted web app over the **real Wikipedia link graph** (actual article-to-article
hyperlinks — not generated or proposed associations). Two modes:

- **Explore** — seed a page, grow the graph outward; a sandbox for watching how expansion
  algorithm settings reshape the result.
- **Connect** — Wikipedia speedrun from page A to page B, either solved by a pathfinding
  algorithm or played by the user, with chess.com-style per-move grading.

Both modes build the graph **live** on screen as the search runs.

## Locked decisions

Do not silently revisit these. They define the architecture.

- **Stack + transport (A):** Python FastAPI + uvicorn backend, static vanilla-JS frontend,
  vis-network for the graph, **SSE** (server → browser) for streaming incremental updates.
  No build step, no frontend framework. WebSockets only if User mode proves to need
  low-latency round-trips — it probably doesn't.
- **Move scoring (B):** **semantic heuristic.** "Distance to target" is estimated as cosine
  similarity between the current page's embedding and the target's. True BFS distance on
  live Wikipedia is infeasible (branching factor ~300). Keep grading behind the `feedback.py`
  interface so real BFS distance can be layered in later without touching the UI.
- **Branching bound (C):** **top-K cap by cosine similarity, K = 20.** Uncapped expansion
  hits ~27M nodes by depth 3. Fetch all links, embed each, keep the top 20 — but the anchor
  differs by mode:
  - **Connect:** rank by similarity **to the target** (this is the A*/greedy heuristic).
  - **Explore:** rank by similarity **to the seed** (keeps the sphere coherent, prevents drift).

## The three contracts

Load-bearing. Do not collapse them.

1. **`config.py` owns every knob.** Depth, node caps, branch caps, beam width, heuristic
   weights — all defined in one place, as data. Modes and algorithms read from it and never
   hardcode. Explore's entire purpose is watching these change the graph.
2. **Algorithms emit `Step`s; they never draw.** An algorithm yields a stream of `Step`s
   ("these nodes/edges were added this tick, here's a note"). The server streams them; the
   frontend applies them to vis-network. An algorithm must not know that the renderer or the
   transport exists. This is what makes live graph building work and lets new algorithms drop
   in without UI changes.
3. **`feedback.py` is the only grader.** Every move (AI or human) produces a
   `MoveEvaluation`: `{ from, to, grade, delta, note }` where grade ∈ {Brilliant, Best, Good,
   Inaccuracy, Mistake, Blunder} and delta is the change in estimated distance-to-target.
   Nothing else assigns grades. The UI only renders them.

## Wikipedia data layer rules

All MediaWiki access goes through `wiki/client.py`. Nothing else in the codebase talks to
Wikipedia directly.

- **Namespace 0 only — filter with `.ns == 0`, never a colon-in-title check.**
  ```python
  links = [title for title, p in page.links.items() if p.ns == 0]
  ```
  `page.links` returns `{title: WikipediaPage}` with `.ns` already populated, so this costs no
  extra API call. The old repo filtered with `if ':' not in title`, which drops `Category:` and
  `Template:` (good) but *also* drops real articles like "Aliens: The Ride" — and for a
  speedrun a dropped article can be the optimal path. That is a correctness bug, not a style
  preference.
- **Descriptive User-Agent from `.env`**, formatted `appname/version (contact)`. Wikimedia
  throttles or blocks generic agents at volume.
- **Retry with a small delay** on fetch failure.
- **Backlinks bypass `wikipedia-api` — deliberately.** `WikiClient.get_backlinks` issues the
  MediaWiki `list=backlinks` query directly via `requests`, because the library's `page.backlinks`
  paginates to exhaustion (no cap — "Cat" is six figures of results) and drops `blnamespace=0` on
  continuation requests. Ours is capped at `config.BACKLINK_LIMIT` and re-sends the namespace filter
  on every page. `WikiClient` is still the only class that talks to Wikipedia; that rule is intact.
  Known accepted bias: the API returns backlinks in page-id order, so a capped fetch is an arbitrary
  sample, not the most relevant one.
- **Two-layer cache (`wiki/cache.py`), checked in order:** in-memory dict → disk
  (`data/*.json` or sqlite) → network. On a network fetch, write to **both** layers. Must be
  disk-backed, not memory-only, or every launch re-crawls from cold. No TTL for now; the
  staleness tradeoff is known and accepted.
- Embeddings get the same two-layer caching, keyed by page title — embedding ~300 links per
  node is the main cost, so pay it once per page.
- The fetch layer stays synchronous (`wikipedia-api`) until caching proves insufficient. Async
  `httpx` against the raw MediaWiki API is the documented upgrade path, not the starting point.

## Prior art

`../Wikipedia Speedrun/` is the predecessor CLI. Its fetching approach is proven — port it,
with the two fixes it lacked (`.ns == 0` filtering, and caching, which did not exist at all).
Its `beam_search.py` / `greedy_search.py` are the basis for Connect's `greedy` and `astar`.

That repo's `CLAUDE.md` documents its known bugs — read it before porting so you don't carry
them over. Notably: the venv there is broken (deps live in system Python), `util` is an
overloaded name, and greedy's loop guard is dead code.

## Commands

Nothing is runnable yet. Once `pyproject.toml` exists (roadmap step 1):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

System Python is 3.13; the project targets >=3.11.

**Unlike the predecessor repo, this project runs inside its venv.** Install every dependency
there — including `sentence-transformers` and `torch`. Do not repeat the split-install that
left the old repo unable to run under its own venv.

```powershell
pytest                          # full suite
pytest tests/test_feedback.py   # one file
pytest -k "ns0"                 # one test by name
ruff check .                    # lint
```

Once the server lands (step 5) — serves API and static frontend together on localhost:

```powershell
uvicorn wikimap.server.app:app --reload
```

`.env` must define `USER_AGENT`; it is gitignored.

## Collaboration mode: teaching, not just delivering

This is an explorative learning project. The user is a student using it to get hands-on
with Claude Code workflows/tooling, technical Python, mapping/display libraries (vis-network,
embeddings/cosine similarity, FastAPI/SSE), and project architecture. Act as a **senior
developer teaching them**, not a contractor executing tickets. This changes the response
format, not the engineering standards above — code quality, the locked decisions, and the
contracts still hold exactly as written.

- **Explain the why alongside the what.** When a design choice is made (a data structure, a
  library call, a pattern), say why this one and not an obvious alternative — tie it back to
  the locked decisions/contracts above when relevant.
- **Narrate tradeoffs when they exist**, briefly — don't hide judgment calls behind silently
  chosen code.
- **Flag the concepts worth knowing**, not everything — new syntax, a library idiom, an
  algorithmic idea — a line or two, not a lecture. Skip explaining things already covered
  earlier in the project.
- **Still work in roadmap-step-sized chunks** (see Working practice below) — teaching happens
  at that cadence, not paragraph-by-paragraph before any code exists.
- Default to walking through code after writing it rather than before, unless the user asks
  to design something together first.

### Explaining a complex concept: ascending levels

When a concept needs more than a line or two — a language feature, a pattern, an algorithmic
idea — **teach it in ascending levels of complexity, and label them.** This format was arrived
at after several failed attempts at explaining ABCs (2026-07-25) and is the one that worked.

- **Level 1 is one sentence, in plain English, with no jargon.** The single most useful true
  thing about the concept. For ABCs that was: *"it means you can't make one of these."* Not a
  definition — the *point*.
- **Level 2 is why you'd ever want that**, usually via an everyday analogy ("you don't own *a
  vehicle*, you own a car or a bike"). Motivation before mechanism, always.
- **Level 3 is the practical rule** — what it does for you in this codebase, still mostly
  jargon-free.
- **Levels 4+ add precision**: exact semantics, then implementation/internals last.
- **Say explicitly where they can stop.** Name which level is enough to read and write the
  project's code, and mark the rest as optional. This is what keeps depth from reading as
  "you must absorb all of this."

Anti-patterns, learned the hard way in that same session:

- **Don't start at the mechanism.** Metaclasses, `__isabstractmethod__`, and CPython source
  were correct and useless — they answered "how is it implemented" before "what is it for."
- **Follow-up questions pull depth; that is not a request to stay there.** Answering a
  narrow "how does X work internally" is fine, but re-anchor to the simple version afterward
  rather than continuing to descend.
- **When the user says they're lost, drop all jargon and restart from Level 1.** Do not
  rephrase the previous explanation — go simpler than feels necessary and rebuild.
- Ground each level in the project's own code (`ConnectAlgorithm`, `GreedyConnect`) rather
  than in invented `Foo`/`Bar` examples, and prefer *running* a small demo and showing the
  real output over asserting what Python would do.

Once a concept lands, write it into `LEARN.md` **in the level structure that taught it** —
the layering is the part worth re-reading, not just the conclusion.

## Working practice

Build one roadmap step at a time (brief §6). Each step is a working, testable checkpoint:
get it green, run the tests, review `git diff`, commit, then move on. Do not one-shot ahead.
State the plan and the files you'll touch before writing code.

**No zero-byte files.** Every file carries content from the moment it is created — a
placeholder module gets a docstring naming its responsibility and the constraints the
eventual implementation must honor; html/js/css get a comment header doing the same.
An empty file cannot tell you whether it is unwritten or belongs to a dead design, which
is exactly what made the superseded `conceptmap` skeleton expensive to resolve. Check with
`find src tests -type f -empty` — it should return nothing.

**Keep the docs current as you go — unprompted, in the same turn as the work.** Documentation
updates are part of the task, never a follow-up offer. Do not ask "want me to add this to
LEARN.md?" — just add it and report it in one line at the end of the response. The user should
never have to prompt for a doc update; being asked to is a defect (flagged 2026-07-25, after two
such offers in one session).

Which file absorbs what:

| File | Update when | Watch for |
| --- | --- | --- |
| `LEARN.md` | a concept clicks, or a misconception gets corrected — mid-conversation, not at step boundaries | Move items between "Struggling"/"Refining"/"Understood" as understanding shifts; record the *correction*, not just the clean fact |
| `README.md` | a roadmap step completes, or setup/layout changes | **Rots silently** — nothing else points a reader here. It was four steps stale when caught on 2026-07-25. Check it at every step boundary |
| `HISTORY.md` | decisions, reversals, step completions, placeholders — see below | Record *why*; `git log` covers *what* |
| `CLAUDE.md` STATUS | every roadmap step | Keep in sync with README's status table — two places, same facts |

If a doc makes a claim you can't verify (e.g. "see HISTORY for why"), either verify it or say the
rationale was never recorded. Do not paper over a gap with a pointer to nothing.

**Log significant changes in [`HISTORY.md`](HISTORY.md).** Add an entry when you complete a roadmap step,
make or reverse an architectural decision, introduce a placeholder or known-wrong value, or
do something a future session would otherwise misread. Record the *reasoning*, not just the
change — `git log` already covers what changed. Skip routine edits. Newest entry at the top,
under a date heading. Update the STATUS section above in the same pass.
