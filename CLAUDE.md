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

**Graph display settings — done.** ⚠️ `#panel` must stay a **sibling** of `#graph` (both inside
`#canvas`), never a child: vis-network's `Canvas._create()` deletes every child of the container it
is given, which wiped the panel and — via a `null.addEventListener` throw — silently disabled the Run
button too. Pinned by `test_settings_panel_is_not_inside_the_graph_container`.
A floating panel over the canvas with three sections: Search
(server-owned, from `/api/config`), Display, and Forces (both browser-owned, persisted in
`localStorage`). Display controls are read generically — every one carries `data-display` and an id of
`d-<key>`, so adding a control means adding HTML and nothing else. Nodes carry `score`/`depth` as
DataSet fields so "colour by" can recolour without re-searching, and Replay re-applies the recorded
Step stream on a timer. The only server-side addition was the structural regression test above.

**`connect/astar.py` — done.** Weighted A*: `f = g + W * h` with `h = hop_scale * (1 - cosine)`, a
`heapq` frontier, and `came_from` path reconstruction. The rescale is load-bearing — `g` counts hops,
so raw cosine added to it can never outweigh one hop and A* would silently degrade to BFS. `W` spans
the spectrum (0 = breadth-first ordering, large = greedy), live-confirmed. A registry in
`algorithms/connect/__init__.py` holds `{greedy, astar}`; `/api/connect?algorithm=` selects, and
`_caches()` is split from `_algorithm()` so both algorithms share one warm cache. `ruff check` clean. **Live: A* solved `Cat → Astronomy` in 3 hops where greedy took 4** —
but it is NOT optimal (a 2-hop route existed; cosine `h` is inadmissible). See HISTORY; do not let a
future docstring claim the textbook guarantee.

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
2. ~~**`connect/astar.py`**~~ **Done 2026-07-26.** ~~**`connect/bfs.py`**~~ **Done 2026-07-28** —
   see HISTORY for why BFS is neither cheap nor the ground-truth baseline the brief implies, and for
   the ply-synchronization bug it took two attempts to get right.
3. **Explore** (`explore/bfs.py`, `explore/beam.py`) only once Connect is complete.

**Where a knob lives — `config.py` vs the frontend.** Contract 1 covers *search* knobs: anything that
changes what the algorithm does. **Display knobs (node size, arrows, physics forces, colours) live in
the frontend and `localStorage`, never in `config.py` or `/api/config`** — they cannot reach the
algorithm, and serving them would give the backend an opinion about drawing, which is contract 2
violated in reverse. Rule: *changes the SEARCH → `config.py`; changes the PICTURE → frontend.*

**Every step must be non-destructive:** existing tests stay green without being edited, new
parameters arrive with defaults, `/api/config` only gains fields, existing URLs keep working.
(Held so far. Backlinks: +6 tests, none edited. Params: +15 tests, two test *doubles* gained
`params=None`. A*: +18 tests, two doubles gained `lambda *_:`. 2026-07-27 review pass: +2 tests,
none edited — raising `TOP_K_BOUNDS`' floor cost nothing because every bounds assertion reads
`config.TOP_K_BOUNDS[0]` rather than the literal. No assertion has ever changed. 80 fast tests green.)

**Review pass 2026-07-27 — seven fixes, one deferred.** Stale `config.py` comments corrected;
`TOP_K_BOUNDS` floor 0 → 1 (K=0 dead-ends every run, and the bounds are served to the browser);
cache dirs anchored to the project root instead of the cwd; `WikiClient`'s broad `except` now logs
before swallowing; `max_nodes` counts **distinct** pages rather than re-counting repeat sightings
(greedy gained a `seen` set kept separate from `visited` — *path* vs *drawing*; A* uses
`len(cost_from_seed)`, which already held the truth); frontend `replayBtn` no longer stubbed with
`|| {}`. ⚠️ **Deferred by the user until deployment: `LinkCache._lookup`'s write is not atomic** — a
crash mid-write leaves truncated JSON that permanently breaks that title on every later run. Fix is
`.tmp` + `Path.replace`. See HISTORY. Do not fix early; do not lose track of it.

**Node-click detail panel — done (2026-07-28).** Clicking any node in the graph, mid-run or
after, opens a third panel (`#node-panel`, a sibling of `#graph`/`#panel` inside `#canvas` —
same nesting rule as the settings panel) showing title, score, depth, the page's real Wikipedia
summary, and a link to the article. Backend: `WikiClient.get_summary(title)` reads `.summary`
and `.fullurl` off the *same* `wikipediaapi` page object `get_links` already fetches (one page,
two API calls — `extracts` then `info` — not four), and a new `GET /api/page?title=` returns it
as plain JSON (a query param, not `/api/page/{title}`, because titles like "AC/DC" contain `/`,
which a path segment can't carry safely — same reasoning `seed`/`target` already use). Fetched
on demand only when a node is clicked, never during the run — the `Node`/`Step` contracts stay
title+score+depth only, on purpose; page detail doesn't belong on every tick. `_wiki_client()` is
a second lazy `@lru_cache(maxsize=1)` singleton, deliberately separate from `_caches()`'s
`LinkCache`-owned one, to avoid coupling this route to another class's private state. Frontend
wires a single `network.on("click", ...)` handler (not `selectNode`) so one listener covers both
"open on node" and "close on background click." 90 fast tests green (was 80), `ruff check` clean,
no existing assertion changed. Manual click-through in a real browser was **not** performed by the
agent that built this (a background session with no browser attached) — the backend was verified
directly (`curl /api/page?title=Cat`, and a 404 case), but visually confirming the panel opens is
still owed before calling this fully proven end-to-end.

**`connect/bfs.py` — done (2026-07-28).** Bidirectional, uncapped BFS — the ground-truth check on
greedy/A*'s shortest-path claims. Registered in `ALGORITHMS`, so it appears in the frontend's
algorithm picker automatically (no frontend changes needed at all). Never computes an embedding
(`Node.score` is always `None`); forward nodes carry `+hops-from-seed`, backward nodes carry
`-hops-from-target` so "colour by depth" visually separates the two searches meeting in the middle.

⚠️ **Took two attempts to get the direction-selection rule right — read this before touching the
turn logic.** Bidirectional BFS is only a ground truth if it processes nodes in true non-decreasing
depth order across BOTH sides combined; get that wrong and it can report a longer route than a
heuristic search already found, which defeats the entire point of building it. Attempt 1 compared
raw queue *length* after partial draining — wrong, let one side's queue race ahead in depth while
the other's shallower frontier waited. Attempt 2 compared full-frontier *size* between plies — still
wrong, a side with a small frontier (e.g. a thin one-link-per-page chain) can keep "winning" that
comparison and race ahead in depth indefinitely. **The only safe comparison is depth LEVEL itself**
— expand whichever side's current frontier sits at the lower depth number, full ply at a time. Both
bugs were caught by the same live test (`Mitsubishi → Kanye West`): attempt 1 returned 4 hops when
A* had already proven 3 exist; the depth-level fix returned 3, matching. Neither bug was caught by
the unit tests, because the fakes used small graphs where the bug either didn't trigger or produced
an answer that was merely *not the specific node* a test asserted on (fixed to assert path/hop-count
only, not which node the searches met at, since that's a genuine implementation detail).

102 fast tests green (was 90, +12), `ruff check` clean, no existing assertion changed.

**`bfs.py` `max_nodes` overshoot fix — done (2026-07-29).** The cap was only checked once per
whole ply (a ply has no size limit of its own, unlike greedy/astar's `top_k`-bounded ticks) — a
repro fanning out 10×10 asked for `max_nodes=20`, got 111. Fixed by checking after every node's own
fan-out instead, plus an early `break` once the two searches meet (stop wasting fetches on the rest
of that ply — nothing later in it can be shorter). See HISTORY for why pruning `bfs`'s branching to
fix this was considered and rejected (it would cost `bfs` the "ground truth" guarantee it exists
for), and for the two real, not-yet-built levers that don't have that problem (concurrent fetch
within a ply; batching, rejected for now since it can't help the backlinks half at all). 104 fast
tests green (was 102, +2), `ruff check` clean, no existing assertion changed.

**No shared base above Connect and Explore yet.** A parent `Algorithm` class holding `__init__` and
an anchor-parameterised ranking helper was proposed and deliberately deferred until Connect is
entirely done — generalising from one mode is a guess. `ConnectAlgorithm` stays the only base.

Every other module under `src/wikimap/` beyond `wiki/`, `embed.py`, `graph/`, `algorithms/`, and
`server/` remains a placeholder holding only a docstring that states that file's responsibility
(explore not yet built).

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
