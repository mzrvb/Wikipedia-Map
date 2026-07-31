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

**`connect/astar.py` reopening fix — done (2026-07-29).** The 2-hop-route-existed gap above
traced to a concrete bug, not just "heuristic is inadmissible, oh well": the old code closed a
page permanently the first time it was popped, which is only sound when a heuristic is
*consistent* — cosine has no such guarantee. A page could get closed via a route that merely
*looked* cheap, and a genuinely cheaper route discovered afterwards was silently thrown away
forever (`if link in expanded: continue`, unconditionally). Fixed by reopening: a strictly
cheaper rediscovery now calls `expanded.discard(link)` to un-close it, so the better cost — and
everything reachable through it — gets reprocessed. Bounded and cheap: costs only ever move down
and are small integers (≤ `max_depth`), so a page can reopen only a handful of times, and
`get_links` on an already-seen title is a cache hit, not a new fetch. This does NOT make A*
provably optimal — the run still stops at the *first* pop of the target, and nothing rules out
an even cheaper route still sitting undiscovered deeper in the frontier; proving that needs an
admissible heuristic or exhaustive search, which is `bfs.py`'s job. What it fixes is the
specific, provable failure mode: every path A* reports is now built from the best per-page cost
the search ever found, not whichever arrived first. Repro'd with a worked fake-graph test
(`test_a_cheaper_route_to_an_already_expanded_node_still_wins`) before the fix, confirmed fixed
after. 106 fast tests green (was 104, +2), `ruff check` clean, no existing assertion changed.

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

**Review pass on `bfs.py` — done (2026-07-29).** A stale test docstring
(`test_backward_search_finds_a_meeting_forward_alone_would_take_longer_to_reach`) described its own
outcome using the frontier-*size* rule that HISTORY documents as the second live-caught bug, not
the depth-*level* rule that actually shipped — fixed to describe reality. Separately, `max_depth`
was applying independently to each of `bfs`'s two frontiers with no comment on the consequence:
greedy/A* treat it as one walk's cap (max path length); `bfs` treats it as each side's cap (max
path length `2 * max_depth`). **Decided, not changed:** keep it per-side — halving it would make
`bfs` unable to certify depths greedy/A* are allowed to search to, breaking its job as their
ground-truth checker. Now stated explicitly in the module docstring instead of left implicit. No
code behavior changed, no existing assertion changed.

**Frontend — auto-fit camera + disabled Connect/Explore toggle (2026-07-29).** `scheduleFit()`
in `app.js` calls vis-network's `network.fit()` so the camera keeps the whole graph in view as it
grows live — debounced via `requestAnimationFrame`, gated behind a new `#d-autoFit` checkbox
(Display panel, default on, same escape-hatch pattern as `Physics`). ⚠️ **Fixed same day:** firing
`scheduleFit()` only from `applyStep()` (once per Step) wasn't enough — forceAtlas2 physics keeps
expanding the layout for a while *after* a Step lands, and Steps are seconds apart on a cold run,
so the view drifted stale between arrivals. Fixed with a `setInterval(scheduleFit, 400)` running
for the life of a live run instead of a single per-Step call — see HISTORY for the full trace
(also fixed a silently-ignored `easing` → `easingFunction` typo in the same pass). Separately, a
Connect/Explore segmented control now sits centered in the header (new 3-column grid in
`style.css`). **Explore ships disabled** — its algorithm files are still one-line docstring
placeholders and there is no server route for it, and "finish Connect before starting Explore" is
a locked 2026-07-26 decision, so the toggle would otherwise imply a mode that silently does
nothing. Confirmed the disabled-toggle interpretation with the user rather than guessing before
building. Frontend-only, no contract/server changes. 106 tests green.

**Frontend — node size can be driven by score/depth, not just one flat slider (2026-07-29).**
First item off the UI-refactor backlog (Six Degrees of Wikipedia / Connected Papers / Obsidian
references — see HISTORY). A new `#d-sizeBy` select (`uniform`/`score`/`depth`, default `uniform`)
mirrors the existing `colorBy` split: `sizeFor(node)` in `app.js` scales the `#d-nodeSize` base
value per node using the same `score`/`depth` fields `Node` already carries for colouring — no
`config.py` or contract change, frontend-only. Default reproduces old behavior exactly. 104 tests
still green (no Python touched). **Not yet manually verified in a browser** — no
`claude-in-chrome` tooling this session; owed same as the node-click panel before it.

**`connect/default.py` REDESIGNED (2026-07-30) — turn-based priority queue replaced by a
ply-synchronized bidirectional beam search.** The original version (built earlier the same day,
described below for the record) alternated forward/backward expansion by comparing each side's
current best `f = g + W*h`. Live-tested against a real search ("israel" -> "john f kennedy"), it
starved backward completely — zero backward expansions, ever — because backward's frontier value
is set once and never updates until it's picked, so a forward side that keeps finding decent
candidates can win that comparison indefinitely. `bfs.py` had already fought this exact bug class
twice (see its own HISTORY entries) and landed on "the only safe comparison is depth LEVEL
itself." The fix here is stronger: remove the comparison entirely. Every tick now expands BOTH
sides' ENTIRE current frontier at once (fetch, score, keep each side's own top-K) — `bfs.py`'s
ply-synchronized shape, with decision C's top-K cap layered back on. There is no "whose turn"
question left to get wrong. Pruning stays per-side, not pooled — forward ranks against the target,
backward against the seed, two different anchors, and pooling would let one side's neighbourhood
crowd out the other's slots, relocating the same starvation into the prune step instead of
removing it. Reopening (astar.py's fix, inherited by the original default.py) is gone, and that's
a simplification, not a lost feature: depth only ever increases by one, together, on both sides,
so first discovery is already the best depth this design's pruning can produce. `heuristic_weight`/
`hop_scale` are no longer read — see module docstring. Still NOT provably optimal (cosine is a
guess on both sides, `bfs.py` remains the only ground truth). 114 fast tests green (11 in
`test_default.py`, including a direct regression test proving backward now expands every tick
regardless of how much better forward's candidates look), `ruff check` clean. Full reasoning in
HISTORY.

**Design decision retained from the original version:** candidate ranking stays anchored to the
fixed `seed`/`target` ("front-to-end"), not the opposing search's current frontier node
("front-to-front") — naive front-to-front is known-unreliable (one opposing node is a poor proxy
for the real meeting point). This choice predates and is unrelated to the turn-selection bug above.

**Seed/target autocomplete — done (2026-07-30).** `#seed`/`#target` now show a
scrollable dropdown of real Wikipedia titles as the user types, backed by a new
`GET /api/suggest?q=` (`server/app.py`) and `WikiClient.search_titles` (`wiki/client.py`
— a direct `list=prefixsearch` call, same reasoning as `get_backlinks`: the
`wikipedia-api` library has no search support). New `config.SUGGEST_LIMIT`, plain
constant like `BACKLINK_LIMIT`, not a `RunParams`/`/api/config` knob since it never
reaches an algorithm. Frontend: `.input-wrap` + `<ul class="suggestions">`, debounced,
`textContent`-only rendering, mousedown-not-click selection (blur fires first and
would swallow a click). This was the item flagged in HISTORY on 2026-07-29 and
reaffirmed after this same day's title-reliability research — it directly sidesteps
that research's typo/disambiguation failure modes by only letting the user pick an
already-real title. Verified live in Chrome against real Wikipedia end-to-end. 8 new
tests, 122 green, `ruff check` clean. Full reasoning in HISTORY.

**`max_nodes` removed from greedy/astar/default — done (2026-07-30).** Live testing
(TV/movie titles as seeds, abstract concepts as targets) surfaced that `Friends ->
Loneliness` on `bfs` blew past `max_nodes=500` to 898 nodes on the seed's own fan-out
alone (bfs has no top-K cap, unlike the other three) — and, investigating, that
`max_nodes` was never doing real work for `greedy`/`astar`/`default` in the first
place: each already caps a node's fan-out to `TOP_K=20`, so `MAX_DEPTH * TOP_K` (≤240)
already bounds them below the 500 default. Removed the `max_nodes` read from those
three; `bfs.py` keeps it, since it's the one algorithm that actually needs the
backstop. `config.py`'s `MAX_NODES` knob and `/api/config` are unchanged (bfs still
uses both) — comments updated to say bfs-only. Frontend dims "max nodes" for every
algorithm except bfs now (same pattern as weight W/hop scale dimming for greedy/bfs).
Does not fix the `Friends`/`bfs` case itself — that's still capped, by design; see
HISTORY. Five node-cap tests removed (behavior they tested no longer exists by
design). 114 tests green, `ruff check` clean.

**`default.py` per-tick cost cut: concurrent fetch + batched embedding — done (2026-07-30).**
Two separate costs, two separate fixes. **Fetch:** the ply loop's sequential
`for parent in frontier: get_links(parent)` became a `ThreadPoolExecutor` submitting every
frontier node's fetch at once — safe without locking since forward/backward parents are always
disjoint mid-run (a shared title would already have ended the run as a same-tick meeting), and
effective because a thread blocked on socket I/O releases the GIL. Doesn't reduce fetch count
(decision C still requires seeing every candidate to rank it) — cuts wall-clock wait only.
**Embedding:** new `Embedder.embed_batch(titles)` / `EmbeddingCache.similarity_many(titles,
anchor)` send a whole ply's cache-miss titles through one `model.encode(list)` call instead of
one per title — closing a TODO left open since the original MVP note. `default.py`'s ply loop
is the only caller so far; greedy/astar still embed one-at-a-time. Neither change touches
ranking, pruning, or termination. 122 tests green, `ruff check` clean. Full reasoning in
HISTORY.

**Frontend — per-step and total-run timing benchmarks — done (2026-07-30).** Every Step's log
line now shows `[+123ms · 4.56s total] <note>`; run termination (done / Stop / dropped
connection) logs the total. Measured entirely client-side off SSE arrival timestamps
(`performance.now()`, monotonic) — deliberately not a server or `Step`-contract field, since
"how long did this tick take to reach the screen" is a rendering question, same family as node
size/colour that contract 2 already keeps off algorithms. Replay shows the run's REAL recorded
timings (`recordedTimings`, parallel to the existing `recorded` Step array), not numbers off
replay's own fixed 600ms animation clock. Frontend-only, no Python touched, 122 tests
unaffected. Full reasoning in HISTORY.

**Live-tested speed/efficiency across all four algorithms on hard pairs — done (2026-07-30).**
No code changed, observational only. Headline result on a genuinely hard cross-domain pair
(`LaMelo Ball → Spanish Revolution`): `greedy` failed (wrong-page dead end at `max_depth`),
`astar` never finished (7+ min, trapped in a "Spanish [sports league]" plateau — a distinct
failure mode from greedy's drift), `default` solved it in 3.37s via bidirectional search
structurally avoiding that plateau, `bfs` hit the node cap from a *one-hop neighbor*'s fan-out
(`2017 NBA draft`, 624 new nodes) rather than the seed — sharper than the earlier `Friends`
finding, since it shows any mid-search node can be a hub, not just the endpoints. Also a third
independent sighting of a disambiguation page counted as a real hop. Full writeup, numbers, and
what these findings prioritize in HISTORY.

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
