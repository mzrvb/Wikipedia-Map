# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read [`HISTORY.md`](HISTORY.md) before starting work.** This file says what the rules
*are*; `HISTORY.md` says *why* they are that way, which decisions were reversed, and which
values are placeholders. It also carries the open questions that STATUS only summarizes.
Update it alongside this file — see [Working practice](#working-practice).

## STATUS

**Connect human-play UI built — new standalone page, backend session (2026-08-07).** The
backend groundwork (`GET /api/article`, `POST /api/evaluate_run`, `feedback.py`) finally has a
consumer: `static/play.{html,js,css}`, a SEPARATE page from the AI-solver graph view, reachable
at `/play.html`. Human speedruns page A → B by clicking real article links (live links
highlighted, dead ones greyed via the server's `wm-link`/`wm-disabled` annotation); the finished
run is graded move-by-move with chess-style badges through `/api/evaluate_run` (contract 3). Built
standalone, not into `app.js`, both because it's a genuinely different interaction (article reader
vs vis-network canvas — no shared JS by design) and because `app.js`/`index.html` were dirty from a
parallel frontend session. **Not yet linked from the header toggle** — that's the integration point
once the frontend session lands; reach it directly at `/play.html` for now. No Python touched, no
contract change, served by the existing StaticFiles mount. Verified live: `/play.html` 200,
`/api/article?title=Cat` returned 1755 `wm-link`/1543 `wm-disabled`/0 scripts, a real
`Cat→Felidae→Astronomy` POST graded Inaccuracy + Brilliant with the exact shape the recap renders.
`node --check` clean. DOM interactions (delegated clicks, screen toggles) proven by reading only —
no browser-automation tool this session. Full writeup in HISTORY.

**Run-log redesign in progress — spec locked, nothing built (2026-08-06).** The twin-rail
"Interchange" log below is scheduled to be replaced by a transit-map style: thick green
(seed/forward) and purple (target/backward) rounded-pill rails, white circular stops per
**depth** (user-facing word — "round" stays internal), curving into a shared gold U-turn loop
at the destination row. Each stop's subline: `[x seconds, +k links, x+ total seconds]`. Header
gains an empty progress-bar slot next to SEED/TARGET, green filling left-to-right, purple
right-to-left. **Open:** which of a round's ≤20 candidates becomes the one station name shown
(no tiebreak rule yet) — resolve before building, see HISTORY, this is the same
single-path-vs-beam misreading the 2026-08-02 rework below already fixed once. A candlestick
chart was also mocked up (scratch, discarded) and is parked in favor of this direction. Do not
start implementing until the station-naming rule is settled.

**Auto-fit graph hidden behind the settings panel — fixed; redundant log "round N:" tag removed
(2026-08-05).** Live-driven via a scratch Playwright/Chromium venv (no `claude-in-chrome`-style
tool available this session) against the real running dev server, through several short Connect
runs. Found a genuine bug, not a guess: `network.fit()` frames the graph against the FULL `#graph`
canvas rect, but `#panel`/`#node-panel` are floating siblings that visually cover part of that same
canvas — measured live via `canvasToDOM()` against `getBoundingClientRect()`, a normal 1-hop
`Dog -> Cat` run already had 2/40 nodes rendered directly under the settings panel, 7/81 on
`Cat -> Astronomy`. Fixed with a new `fitGraph()` (`app.js`) that fits the graph into the safe
rectangle (canvas minus whatever panels are currently open) instead of the full canvas —
re-measured at 0/40, 0/81, and 0/81 with both panels open at once. Separately, the twin-rail log's
round rows said `round N:` in both the fwd and bwd column of the same row — redundant, since one
row can only be one round; removed from both columns, and the now-unused `roundNumber` counter
deleted rather than left dead. Frontend-only, no contract/server change. 109 fast tests green
(nothing Python touched), `node --check` clean. Full before/after numbers in HISTORY.

**`feedback.py` implemented: rank-based move grading (contract 3) — docs backfilled (2026-08-02).**
Landed by a parallel backend session (commit `9eb769f`) with no doc update in that commit —
recorded here after the fact. `feedback.py` was a docstring-only placeholder until now;
`evaluate_move()` grades a move by where its destination **ranks**, by similarity to the target,
among every real (ns0) link the page it was played from actually offered — not an absolute cosine
threshold, and not restricted to top-K (a human player can click any link on the page). Reaching
the target directly is unconditionally `Brilliant`. The five grade-boundary percentiles are an
explicit placeholder (same status as `config.MAX_DEPTH`) — do not retune without real playtesting
data. Backend-only: nothing in the server or frontend calls this yet, since Connect's human-play
mode doesn't exist. 6 new tests, 109 fast tests green overall, `ruff check` clean. Full reasoning
in HISTORY.

**Twin-rail log overlap fixed, found-banner added, autocomplete race fixed — done (2026-08-02).**
First real browser check of the twin-rail log (previous entries relied on `node --check` + curl
only): a scratch Playwright/Chromium venv driving the live dev server found the origin/destination/
exhausted rows' dot and bridge rendering on top of the caption text, not above it. Root cause: those
rows' `.col` elements have empty per-column labels (real text lives in a separate `.shared-label`
row below) and an absolutely-positioned dot, so neither contributes intrinsic height — the "dots"
grid row collapsed to 0px and coincided with the caption row. Fixed with `min-height: 28px` on
`#log .row .col` (a no-op on round rows, whose real label text already exceeds it) plus matching
`padding-left: 22px` on `.shared-label`/`.meta`. Also added `#found-banner` — a floating amber pill,
sibling of `#graph`/`#panel`/`#node-panel`, showing the terminal Step's own `note` verbatim
(no second hand-rolled phrasing to drift from the log) when `step.path` lands; dismissible, cleared
by `resetLog()`. While screenshotting, found and fixed a genuine unrelated race in
`setupAutocomplete()` (2026-07-30): a suggestion-fetch response landing after the input already
blurred could reopen the dropdown over the graph/banner, since the stale-query guard never checked
whether the input was still focused — fixed with an added `document.activeElement !== input` check.
All three frontend-only, verified live against the running server (screenshots + bounding-box
reads), not just statically. Full root-cause writeup in HISTORY.

**Center force: full re-measurement pass, range widened again with real margins (2026-08-02).**
The lock-to-default fix worked but only allowed loosening, never tightening — user asked for the
range to be re-derived properly: measure real scaling in Chromium, iterate candidate configs,
pick min/max/default from the data. Swept `centralGravity` 0.30/0.35/0.40/0.45 on two graph
instances; 0.30-0.40 settled clean every trial, 0.45 flaked once — confirming the real instability
boundary sits between 0.40 and 0.45. Shipped `data-log-max=0.35` (a full margin below the flaky
value, not 0.40 itself, since 0.40 was already the number that failed to satisfy the user last
round). Re-verified end to end against the real file: a flat ~15-20% radius drop per slider step
across the whole range, zero dead zones. Default raw recalculated to the same semantic
`centralGravity≈0.0099`. **Also caught and corrected its own false alarm in the same pass**: a
top-edge trial flaked once at a 2.5s settle window, looking identical to real instability — a
12-second re-check showed it was an ordinary damped settle (full decay to zero, just slower),
categorically different from the confirmed real cg≈0.5 oscillation (which never decayed even at
9 seconds). Full binary-search and false-alarm data in HISTORY.

**Center force: slider max hard-capped to the shipped default — ends the loop (2026-08-02).**
Fourth report the same day; the user asked directly for the slider's top end to just BE the
default, so there's no ceiling number left to get wrong. `data-log-max` is now `0.01`, the exact
default `centralGravity`, not a value chosen to sit safely above it — confirmed live (raw=100 →
`0.01` exactly, raw=0 → `0.005`, unchanged floor). The slider can now only loosen the layout from
default; the unstable zone found in the previous entry (`>=0.456`) is structurally unreachable,
not just measured-safe. Full reasoning in HISTORY.

**Center force "insanely sensitive" complaint — real cause was solver instability, not the
curve (2026-08-02).** Third report about this same control the same day. Rather than re-running
the same radius/percentage measurements (already clean twice), a Chromium probe sampled
`network.getPositions()` repeatedly to check whether the layout was actually settling, not just
what it looked like once it stopped. Found the forceAtlas2Based solver genuinely never converges
once `centralGravity` nears the old ceiling of 0.5 — a live binary search on the 81-node
`Cat -> Astronomy` graph found `<=0.436` always settles to 0px/frame movement, `0.456-0.5` is
flaky-to-reliably unstable, and the old ceiling itself showed 6-17px of non-decaying per-frame
drift even after 6+ seconds — a genuine physics limit-cycle, not a rendering issue, and not
something any slider-curve remap could fix. Fixed by lowering `data-log-max` 0.5 → 0.4
(`index.html`), re-verified stable across the whole new range and three repeated trials at the
new top edge; default raw recalculated 15 → 16 to keep the same semantic default
(`centralGravity≈0.01`). Raising solver `damping` or lowering `repel` back down were considered
and deliberately not done — untested live, and shipping an unverified physics tweak here would
repeat the exact mistake this entry documents. Full binary-search numbers in HISTORY.

**Center force's log-scale fix corrected — labels-vanish regression fixed (2026-08-02).** User
reported it was "still fucked" after the earlier fix; a first Chromium re-measurement (radius,
drift, per-step %) came back clean, so screenshots were taken instead of just numbers, which
found the actual bug: at the loose end of the new log-scale range, auto-fit zooms out far enough
to cross the separate Text-fade-threshold cutoff, and every node label vanishes. The failure mode
predates today (linear `centralGravity=0` always did this) but the old slider buried it 2% from
one edge; the log-scale remap gave it roughly a third of the slider's length, easy to hit by
accident. Fixed by raising `data-log-min` 0.002 → 0.005 (`index.html`) — chosen so the loosest
setting still keeps the reference 81-node graph's auto-fit scale above the 0.4 label-fade default,
confirmed by both instrumented reading and screenshot at every step of a full re-sweep. Default
raw slider position recalculated to still resolve to the original `centralGravity≈0.01`. Full
narrative, including why the first verification pass missed it, in HISTORY.

**Run log reworked into a twin-rail "Interchange" diagram — done (2026-08-02).** The log's
2026-07-31 single-rail transit-map styling read as one sequential journey, which stopped
matching reality once questioned against `default.py`'s actual shape: it's a BIDIRECTIONAL
beam search, expanding the forward frontier (seed) and backward frontier (target)
simultaneously every round, in the same `Step`, never one side at a time. Four directions were
mocked up (Round Ledger / Twin Lines / Closing Gap / Radar) and presented to the user, who
picked **Twin Lines / Interchange**: two parallel rails side by side — a blue Line from the
seed, an orange Line from the target (same hexes `sideColor()` already used) — one row per
round, since the two sides are always exactly lockstep (`forward_survivors`/`backward_survivors`
are always emitted together, every round, by construction — no cross-list sync needed). The two
rails merge at an amber diamond "interchange" row when `step.path` is set (destination), or cap
off with hollow rings and no bridge on exhaustion (the absent bridge is what reads as "never
met"). `app.js` gained `roundCounts()` (counts a round's `step.nodes` by depth sign rather than
regexing the note — same reasoning `stepKind()` already used for checking `step.path` over
string-sniffing), `resetLog()`/`appendRow()`/`logStep()`, and a small `railStarted`/`railEnded`
state machine (a trailing "done" status row legitimately arrives after the terminal row, so CSS
`:last-child` alone can't know where a rail should stop). `log()`'s signature and all six
non-Step call sites (SSE status/error/done, `stop()`, `source.onerror`, replay's completion
message) are unchanged; replay needs no separate handling since it drives the same `applyStep()`
→ `logStep()` path on a timer. `index.html` untouched — the log is still built entirely in JS.
Frontend-only, no contract/server change; `node --check` clean. **Not yet manually verified in a
browser this session** (no browser automation tool available) — static files confirmed serving
correctly (200s) off the already-running dev server, but a real click-through is still owed,
same caveat as several earlier frontend passes.

**Center force log-scale, auto-fit staleness fixed, Arrows toggle removed, endpoint sizing fixed
— done (2026-08-02).** Four fixes in one Chromium-driven pass, continuing the same session's
Forces-slider measurement work below. (1) Center force ("centralGravity") was linear over an
exponential physics response — measured 68% of the layout's total range-of-motion compressed into
the slider's first 2% of travel. Now a generic `data-log`/`-min`/`-max` attribute (any range input
can opt in, not just this one) remaps the raw 0-100 slider through `logValue()`/`rawFromLog()` in
`app.js`; re-measured afterward at a consistent ~17-24% change per step across the whole range.
(2) Auto-fit view genuinely was stale, confirmed live: `scheduleFit()` was only ever called during
an in-flight SSE run, so a Forces slider changed after a run finished (or re-checking the Auto-fit
checkbox itself) moved the layout with nothing left to refit the camera —
`network.getScale()` provably never moved. Fixed with `settleFit()`, a short-lived re-fit interval
(300ms, extends itself for 1.5s of quiet) that `applyDisplay()` now triggers on every display
change. (3) "Arrows" toggle removed — links are inherently directional, so it was a control for
turning off something always needed; arrows are now hardcoded on in both the network constructor
and `applyDisplay()`. (4) Size-by confusion traced to endpoints (seed/target) being run through
the same score/depth scaling curve as every other node, which could shrink them (backwards from
"this is an endpoint") depending on how hard the search was — fixed by giving endpoints the same
kind of fixed-regardless-of-mode treatment colour already gets. A second, real but NOT code-fixed
cause — `Node.score` means similarity-to-target on the forward frontier and similarity-to-seed on
the backward one — got a `title` tooltip instead, since it's intentional per-side ranking, not a
bug. All four frontend-only, no contract/server change. Full methodology and numbers in HISTORY.

**Forces sliders measured live and re-tuned — done (2026-08-02).** User reported the Display
panel's Forces sliders "feel weird" when tweaked; no live-browser tooling was available this
session, so installed Playwright + headless Chromium into a scratch venv (not the project's own)
and drove the actual running server through real Connect runs at three graph sizes, sweeping
repel/springLength combinations and reading `network.getPositions()` for spread/overlap/drift.
Findings: node-circle overlap was never the problem (0 at every setting tested — low settings
instead crowd *labels* into an unreadable blob); **springLength above ~200 stops the layout from
settling** once a graph reaches a realistic size (~80 nodes) — confirmed both by a persistent
20-35px/sec drift reading and a screenshot of the layout visibly flying apart instead of
organizing; repel had no observed downside even at 150 (better label spacing, same stability).
`index.html` changed: repel default 45 → 70, springLength slider max capped 400 → 180.
`centralGravity`/`springConstant` untouched (not swept, no measurement to justify changing them).
Frontend-only, no contract/server change. Full methodology, numbers, and a flagged secondary bug
(auto-fit doesn't re-run on a post-run slider change) in HISTORY.

**`default.py` perf review — done (2026-08-02).** Three optimizations, no behavior change:
`EmbeddingCache.similarity_many` no longer double-embeds a title that appears more than once in
one batch (a hub page linked from several frontier parents in the same tick), `default.py`'s
`ThreadPoolExecutor` is now created once for the whole run instead of once per tick, and
`_rank_and_cap` uses `heapq.nlargest` instead of a full sort. 77 fast tests green (was 76, +1),
`ruff check` clean, no existing assertion changed. Full reasoning in HISTORY.

**Frontend polish pass 2026-07-31 — winning path highlighted, five colour-by modes, a
transit-map run log, light theme, and a reworded run form.** Five separate, mostly
frontend-only changes made in one session, landing on top of the `default.py`-only state
below:

- **`Step` gained an optional `path` field** (`graph/contracts.py`) — the only Python-side
  change in this pass, and a real contract-2 addition, not a frontend trick: `path: list[str]
  | None = None`, populated only on the terminal success `Step` in `default.py` (both the
  `seed == target` case and the normal meeting-in-the-middle case), using the same `path`
  list already built for the human-readable note. `None` everywhere else, including
  exhaustion — never `[]`. The frontend's `highlightPath()` (`app.js`) uses it to amber-border
  every node on the winning route and thicken/recolour its edges, without regexing the
  prose note. 76 tests still green (two existing tests gained a `.path == [...]` assertion;
  no new test functions, no existing assertion removed).
- **Five `colour by` modes, not two.** `score`/`depth` already existed; added `band`
  (score bucketed into 4 fixed colours instead of a gradient — trades precision for
  scannability), `side` (flat blue/orange by sign of `depth` — answers "which of
  `default.py`'s two frontiers found this," which depth's per-hop gradient blurs), and
  `recency` (colour by which tick a node was FIRST discovered in, tracked client-side via a
  `tickCounter`/`maxTick` pair reset per run/replay — distinct from depth, since on a wide
  round tick order and hop count can diverge). A separate **"Dim off-path" checkbox**
  (independent of colour-by) mutes every node/edge not on the winning route to 15% opacity
  once one exists, keyed off the same `onPath` DataSet flag `highlightPath()` sets — re-applied
  from `applyDisplay()` too, so toggling it after a run finishes still works. All frontend-only,
  no `config.py`/contract/server change.
- **The run log is now styled as a transit-map line, not a scrolling text dump.** Each
  entry is a "stop" — a dot connected to the next by a rail (`.entry::after` in `style.css`,
  pure CSS, no SVG) — with dot shape/colour keyed to what kind of stop it is: green terminus
  for the start, amber glowing terminus for the destination (checked via the new `step.path`
  field, not string-matching the note), a two-tone blue/orange dot for an ordinary round
  (matching `side` colour-by's palette — a round always advances both directions at once, so
  the dot always shows both), and hollow rings for status chatter / "no route found." Log
  order flipped from newest-on-top (`prepend`) to chronological (`append` + auto-scroll-to-
  bottom), since a route metaphor only reads correctly top-to-bottom in travel order.
- **"ply" removed from everything user-visible.** Renamed to "round" in the `Step` note
  `default.py` emits (`"round {depth}: …"`) and in the matching CSS class / JS classifier —
  a direct, informed user correction: the word (and, worse, an initial chess-ply analogy while
  explaining it) implied the two search directions take turns, which is backwards — a round is
  both frontiers advancing in the exact same tick, simultaneously, no ordering between them.
  `default.py`'s own module docstring and code comments still say "ply" deliberately — that's
  the historically accurate term inherited from `bfs.py`'s design lineage, a different audience
  (a future reader of the algorithm's reasoning) than the running app's user-facing text.
- **Light theme is now the default.** Every colour lives in `style.css`'s `:root` CSS
  variables (`--bg`/--panel`/`--line`/`--text`/`--muted`/`--accent`), flipped from a dark to a
  light palette in one edit — plus two hardcoded canvas colours in `app.js` that CSS can't
  reach (vis-network draws to `<canvas>`): node label text and the default edge line colour.
- **Run form reworded**: separate "From"/"To" labelled fields replaced with one flowing
  `Connect ____ and ____` phrase (`.connect-phrase` in `index.html`/`style.css`). Each input
  lost its own `<label>` wrapper, so each carries an `aria-label` (`"From page"`/`"To page"`)
  instead, to keep an accessible name.

Manual verification note: none of the above was click-tested in a live browser by the agent
that built it this session (no `claude-in-chrome` tooling) — `node --check`, the fast suite,
and `ruff check` all passed, but visual confirmation is owed, same caveat as the node-click
panel and per-node sizing before it.

**`greedy.py`/`astar.py` stripped 2026-07-31 — `default.py` is now the ONLY Connect
algorithm.** A direct, informed user call made while comparing wikimap against
[jwngr/sdow](https://github.com/jwngr/sdow) (which precomputes the whole link graph offline and
answers with plain BFS — a different, easier problem than wikimap's live crawl). Repeated live
testing (see the 2026-07-30 `LaMelo Ball → Spanish Revolution` entry in HISTORY) showed `greedy`
dead-ending, `astar` plateauing for 7+ minutes, and `default` solving the same pair in 3.37s —
maintaining three algorithms was mostly maintaining two failure demonstrations. `ALGORITHMS` in
`algorithms/connect/__init__.py` is now `{"default": DefaultConnect}`; the registry/lookup shape
was deliberately kept (not collapsed to a bare call) so a genuinely new algorithm could still drop
in later. `config.py` lost `MAX_NODES`, `HEURISTIC_WEIGHT`, `HEURISTIC_HOP_SCALE` and their bounds
(all astar-only since `bfs.py`'s removal the same day); `RunParams` lost the matching fields.
`/api/connect` lost `algorithm=`/`max_nodes=`/`heuristic_weight=`/`hop_scale=`; `/api/config`
stopped publishing the algorithm registry and those knobs' bounds. Frontend lost the Algorithm
picker and the three now-dead Search-panel rows, plus the per-algorithm dimming logic that used
to grey them out. 76 fast tests green, `ruff check` clean. Full reasoning and the exact
before/after in HISTORY.

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
admissible heuristic or exhaustive search, which was `bfs.py`'s job until it was removed
2026-07-31 (see HISTORY) — nothing in this codebase does that check anymore. What it fixes is the
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
2. ~~**`connect/astar.py`**~~ **Done 2026-07-26.** ~~**`connect/bfs.py`**~~ **Done 2026-07-28,
   REMOVED 2026-07-31** — see HISTORY for why BFS was neither cheap nor, in the end, worth keeping
   as the ground-truth baseline the brief implies it should be, and for the ply-synchronization bug
   it took two attempts to get right before it was cut.
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

**`connect/bfs.py` — built 2026-07-28, REMOVED 2026-07-31.** Was bidirectional, uncapped BFS — the
ground-truth check on greedy/A*'s shortest-path claims (never computed an embedding; forward nodes
carried `+hops-from-seed`, backward `-hops-from-target`). Its build took two attempts to get the
direction-selection rule right (comparing depth LEVEL, not queue length or frontier size — both
tried and proven wrong live), and later got a `max_nodes` overshoot fix and a docstring-accuracy
review pass. Removed as a direct, informed user call — too slow to be worth the ground-truth
guarantee it provided, after being shown that capping it into a beam search would just duplicate
`default.py`. **The full build/bug/removal narrative, including the direction-selection saga and
what removing it costs the codebase, lives in HISTORY — read it before adding anything back in
this shape.**

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
guess on both sides; `bfs.py` was the only ground truth for this, until it was removed 2026-07-31 —
see HISTORY — leaving no algorithm in this codebase that can currently make that check). 114 fast
tests green (11 in
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

**Superseded 2026-07-31, in two steps (see HISTORY for both):** `astar.py` turned out to have the
same unbounded-fan-out problem `bfs` had, for a different structural reason (its `while frontier`
loop has no ply structure limiting distinct-node pops), so `max_nodes` was reinstated for `astar`
alone. Then `bfs.py` itself was removed entirely (too slow to be worth the ground-truth guarantee
it provided). `max_nodes` is now astar-only.

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

**Frontend — Enter/Run autocorrects seed/target to a real title — done (2026-07-31).**
`app.js`'s `submit` handler now resolves both fields through `/api/suggest` (`resolveTitle()`,
reusing the same endpoint autocomplete's dropdown already calls) before a run starts, falling
back to the typed text if the search returns nothing. Fixes a real correctness gap: the
algorithms compare `seed`/`target` to Wikipedia link titles with exact string equality, so a
hand-typed `astronomy` never matched `Astronomy` even after walking through that exact page —
autocomplete only helped if the user clicked a suggestion, not on Enter/Run. Fixed frontend-side
(reusing `/api/suggest`) rather than loosening the comparison inside `greedy.py`/`default.py`,
to avoid a second fix duplicated across two algorithm modules. Frontend-only, no Python touched,
122 tests unaffected. Full reasoning in HISTORY.

**Frontend — per-step and total-run timing benchmarks — done (2026-07-30).** Every Step's log
line now shows `[+123ms · 4.56s total] <note>`; run termination (done / Stop / dropped
connection) logs the total. Measured entirely client-side off SSE arrival timestamps
(`performance.now()`, monotonic) — deliberately not a server or `Step`-contract field, since
"how long did this tick take to reach the screen" is a rendering question, same family as node
size/colour that contract 2 already keeps off algorithms. Replay shows the run's REAL recorded
timings (`recordedTimings`, parallel to the existing `recorded` Step array), not numbers off
replay's own fixed 600ms animation clock. Frontend-only, no Python touched, 122 tests
unaffected. Full reasoning in HISTORY.

**Review pass — `embed.py` cache-anchor gap fixed, `greedy.py` seed==target silence fixed
(2026-07-31).** Two findings from a backend review. **1.** `EmbeddingCache.DEFAULT_DATA_DIR` was
still `Path("data/embeddings")` — a bare relative path, resolving against whatever directory the
process happened to be launched from. `wiki/cache.py`'s `LinkCache` got the equivalent fix in the
2026-07-27 review pass (`Path(__file__).resolve().parents[3]`); this sibling cache never did,
because every `test_embed.py` test already passed `data_dir=tmp_path` explicitly, the same blind
spot that let the original bug ship. Fixed the same way (`parents[2]`, one level shallower since
`embed.py` sits directly in `wikimap/` rather than a subpackage), with a new regression test that
computes the expected path independently rather than importing `embed`'s own constant, so it
can't pass by sharing a bug with the code it's checking. **2.** `GreedyConnect.run` had no
seed==target special case — `astar`/`default`/`bfs` all emit an explicit "reached in 0 hops" note
for it, greedy just returned after the generic start Step with nothing announcing success. Fixed
to match its siblings; the one existing test asserting the old silent behavior was updated (not
new — this is an intentional behavior change, not a regression). Also flagged, not yet fixed: the
2026-07-30 `max_nodes` removal (below) reasoned `MAX_DEPTH * TOP_K` bounds `astar`'s worst case
the same way it bounds `greedy`/`default` — true for those two (one path; one pooled top-K per
ply) but not for `astar`, whose `while frontier:` loop can expand every distinct node discovered
below `max_depth`, not one per level. This likely explains the astar 7+-minute plateau recorded
below rather than being a separate phenomenon; the capping fix proposed here was implemented the
same day (`max_nodes` reinstated for `astar` — see config.py and astar.py, and the entry below).
123 tests green (was 122, +1), `ruff check` clean.

**`connect/bfs.py` removed — done (2026-07-31).** Deleted along with its test file and registry
entry; `greedy`/`astar`/`default` are the three remaining Connect algorithms. A direct, informed
user call, made after being shown that (a) converting `bfs.py` into a beam search for speed would
remove the codebase's only ground-truth shortest-path checker, and (b) the result would almost
exactly duplicate `default.py`, which already is a bidirectional beam search. `max_nodes` (the
other thing `bfs.py` owned) survives, now `astar`-only. Every doc/comment across the codebase that
named `bfs.py` as live code was swept in the same pass. Full reasoning, including what this costs
the codebase (no algorithm can currently verify another's shortest-path claim), in HISTORY.

**Live-tested speed/efficiency across all four algorithms on hard pairs — done (2026-07-30,
before `bfs` was removed).** No code changed, observational only. Headline result on a genuinely
hard cross-domain pair
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
