# HISTORY

Running log of significant changes and the reasoning behind them.

**What belongs here:** decisions and their rationale, architecture changes, reversals,
roadmap step completions, anything a future session would misread the repo without.
**What does not:** routine edits, typo fixes, anything `git log` already tells you.
This file explains *why*; git explains *what*. Newest entries at the top.

---

## 2026-07-25

### Roadmap step 5 (server + SSE + live frontend) complete — MVP works end-to-end

`server/app.py` filled, `static/{index.html,app.js,style.css}` filled, `tests/test_server.py` new
(8 tests). 38 fast green, ruff clean, no empty files. Decisions worth keeping:

- **`_stream` is a sync generator, not `async def`.** The fetch layer is deliberately synchronous
  (CLAUDE.md), so an async route would block the event loop on every Wikipedia call. Handing
  Starlette a *sync* iterator makes it iterate in a threadpool instead — correct for blocking work
  and free at MVP scale. Revisit only if the async httpx upgrade path is ever taken.
- **Caches built once and lazily** — `@lru_cache(maxsize=1)` on a no-arg `_algorithm()`, imports
  inside the function. Once because a shared `LinkCache` across requests is the entire point of
  having a cache; lazily because eager construction would demand `USER_AGENT` and load an ~80MB
  model merely to import the module, which would have made the test suite slow and fragile.
  `_algorithm()` is annotated as the ABC, not `GreedyConnect` — swapping in A* is a one-line change.
- **Errors must be reported in-band.** Once streaming starts the status line is already sent, so a
  mid-run exception cannot become a 500. `_stream` catches, logs the traceback server-side, and
  emits an `error` event; `test_connect_reports_algorithm_failure_in_band` pins this. Without it a
  crashed run is indistinguishable from a hang.
- **`StaticFiles` mounted last, at `/`.** Mount order is match order, so `/api/*` wins and
  everything else falls through to a file. Same origin for API and frontend means no CORS config.
- **vis-network via CDN `<script>`.** The locked stack says no build step; a script tag is how you
  get a library without one. Needs internet on first load, which costs nothing extra given the app
  already requires it for Wikipedia.
- **Frontend writes titles with `textContent`, never `innerHTML`.** Page titles are third-party
  strings landing in the DOM. vis-network labels are canvas-drawn and safe by construction, so the
  run-log panel is the only place raw titles meet the DOM — and it uses `textContent`.

**Verified live, not just unit-tested** (the distinction that matters — fakes prove wiring, not
that it works): `Cat → Astronomy` in 4 hops via `Science (journal)` → `Spiral nebulae` →
`Galactic astronomy`, score 0.460 → 0.542 → 0.794 → 1.000, 81 nodes / 80 edges, top-K exactly 20
per tick. Incremental delivery confirmed on a cold `Banana → Quantum mechanics` run (frames at
+0.00 / +5.71 / +6.27 / +10.17s) — a warm run finishes too fast to demonstrate streaming at all,
which is itself worth remembering when testing this later. Cold ~80s, warm <0.01s.

**Known rough edges, deliberately not fixed tonight** (MVP first):
- Embedding is one title at a time — ~300 sequential `encode()` calls per hop dominate the cold
  runtime. Batching via `model.encode(list)` is the obvious win and belongs in `embed.py`.
- Greedy's score can *drop* between hops (Banana run went 0.307 → 0.287). Correct behaviour, not a
  bug: greedy picks the best of the *current* page's neighbours, which may be worse than where it
  already stands. This is exactly the regret that step 8's grading will quantify.
- No stop-the-run-server-side: the browser's Stop button closes the EventSource, but the generator
  keeps running to completion. Harmless at these depths; fix when Explore makes runs longer.

### CLAUDE.md gains a teaching-format rule: explain complex concepts in ascending levels

No code changed. Session was spent re-teaching ABCs (the concept `LEARN.md` had flagged as
still-shaky after step 4). The first three attempts failed in an instructive way, so the
format that finally worked is now a rule in CLAUDE.md's collaboration section rather than a
one-off.

**What failed:** each attempt was *correct* and got less useful — job-description analogy, then
`@abstractmethod`-vs-`ABC` precision, then `Lib/abc.py` source and `ABCMeta.__new__`. The user's
own follow-up questions ("is `__isabstractmethod__` part of the library?", "how does ABC scan?")
pulled the depth, which is the trap: answering them faithfully kept descending into implementation
before the *purpose* had landed. Their words: "explain as SIMPLY as possible and build up."

**What worked:** labelled Levels 1–5. L1 = one jargon-free sentence stating the *point* ("it means
you can't make one of these"), L2 = motivation via everyday analogy ("you don't own *a vehicle*"),
L3 = the practical rule, L4+ = precision then internals, plus an explicit "you can stop at Level 3;
the rest is trivia." Naming a stopping point is what stopped depth from reading as obligation.

Generalized into CLAUDE.md → "Explaining a complex concept: ascending levels", with the
anti-patterns (don't open with mechanism; a follow-up question pulling depth is not licence to
stay there; restart at L1 — don't rephrase — when the user says they're lost) and a preference
for running small demos and showing real output over asserting what Python would do.

`LEARN.md` restructured to match: the scattered ABC entries (one under "Struggling with", one
under "Refining" with two follow-ups) are consolidated into a single "Understood" entry written
*in the level structure that taught it* — the layering, not just the conclusion, is the reusable
part. Corrections captured that the old entries had wrong or missing: the instantiation blocker is
`@abstractmethod` and not `ABC` itself; it blocks *existence*, not arguments; and "abstract" means
unfinished, not inaccessible (orthogonal to the underscore convention). A later correction in the
same session added Level 4b: the user had the inheritance direction backwards (called
`GreedyConnect` the *parent*) — whatever sits in the parentheses is the parent, and inheritance
flows downhill, which is what makes the inherited `__init__` possible.

### Docs-update rule: keep them current unprompted, never offer

Separate complaint from the same session, and a process defect rather than a teaching one. Twice
I *offered* to update `LEARN.md` ("say the word and I'll add it") instead of just doing it, forcing
the user to prompt for each update — the exact overhead the running-log practice exists to remove.
Now a rule in Working practice, with a table of which file absorbs what.

Two things it caught immediately: **`README.md` was four roadmap steps stale** (still claiming step 1
hadn't started and the tree was all placeholders), because nothing in the working practice pointed at
it after a step — it now has a status table and an explicit check at every step boundary. And the
rule against unverifiable pointers came from writing "see HISTORY.md for why" about the step-4
ordering deviation, then finding no such entry.

**Open — step 4 ordering deviation, rationale never recorded.** Brief §6 step 4 is headless *Explore*
(`explore/bfs.py`); what was built is Connect's greedy. Defensible (greedy exercises the same top-K
cap and gives a concrete target to search toward, and steps 5+ are unaffected), but the actual
reasoning is lost. Noted in README as a known gap rather than back-filled with a guess.

## 2026-07-23

### Roadmap step 4 (first algorithm: greedy Connect) complete

Built per the plan below. `config.py` (+3 knobs), `algorithms/base.py` (ABC filled),
`algorithms/connect/greedy.py` (filled), `tests/test_greedy.py` (new, 9 tests). 30 fast green,
ruff clean, no empty files. Notes worth keeping:

- **Two "failures" on first run were both wrong test assertions, not code bugs** — a useful
  reminder that a red test can mean the test mismodels correct behaviour. (1) A Step's `edges` are
  score-ordered, so `edges[-1]` is the *worst* candidate, not the one greedy moved to — the committed
  move is recorded in the note (`'B' -> 'D'`), so arrival is asserted there. (2) The dead-end Step
  deliberately still emits the current page's fan-out, so that page *is* the source of a final tick —
  `_move_sources` correctly includes it. Both fixed by correcting the expectation.
- **The dead-end path is a real branch, not just the cap.** Greedy stops for three distinct reasons:
  reached target (loop condition), hit MAX_DEPTH/MAX_NODES (cap note), or every top-K candidate already
  visited (dead-end note). The last is exactly the case the visited check exists to survive — without
  it greedy would ping-pong forever because a page's nearest neighbour is often the page just left.
- **Seed is emitted as its own first Step** (before the loop) so it's born with real attrs; letting the
  first tick's edges create it would leave a blank node (edges auto-create missing endpoints — see LEARN).
- **`base.py` type-imports the caches under `TYPE_CHECKING`** so importing an algorithm doesn't drag in
  wikipediaapi (via LinkCache/WikiClient) or trigger a model load. The ABC only stores what it's handed.

Everything below in this entry is the pre-build plan, kept for the record.

### Step 4 (first algorithm) — design agreed, NOT yet built (paused mid-planning)

Planning conversation only; no code written. Resume here next session. The plan:

**Files to touch:**
- `config.py` — add the knobs greedy reads (currently only holds `EMBEDDING_MODEL`):
  `TOP_K = 20` (decision C branching cap), `MAX_DEPTH` (hop limit), `MAX_NODES` (hard ceiling so
  a bad run can't crawl forever). Values TBD — placeholders when written.
- `algorithms/base.py` — the ABC `ConnectAlgorithm(ABC)`: `__init__(link_cache, embed_cache)`
  stores the caches; `@abstractmethod def run(self, seed, target) -> Iterator[Step]` declares the
  shape with an empty body. Declares only; executes nothing.
- `algorithms/connect/greedy.py` — `GreedyConnect(ConnectAlgorithm)` implementing `run`.

**Greedy loop (best-first on the semantic heuristic):** from `current = seed`, until
`current == target` or MAX_DEPTH/MAX_NODES trips: (1) `link_cache.get_links(current)`;
(2) score each link by `embed_cache.similarity(link, target)` — anchor is the **TARGET** per
decision C (Explore will anchor to seed instead); (3) keep TOP_K by score; (4) filter out a
real `visited` set; (5) pick the single best unvisited link; (6) `yield Step(nodes=[the K
candidates], edges=[current->each], note=...)`; (7) mark visited, move `current`.

**Two things explicitly NOT ported from `../Wikipedia Speedrun/greedy_search.py`:** its loop
guard was dead code — we write a genuine `visited` check (greedy loops without it because the
highest-similarity neighbor is often the page just left). This is the one bug we refuse to carry.

**API shape — Option A, CONFIRMED.** Caches injected in `__init__`, job passed per call as
`run(seed, target)`. The deciding reason is *not* the ABC tie-breaker first written here — it's
that A is the **same dependency-injection shape the codebase already uses twice**: `LinkCache(client)`
and `EmbeddingCache(embedder)` both take their dependency at construction and their job per call.
A makes `ConnectAlgorithm` the third instance of that pattern. The ABC argument is real but
secondary: we want a shared `run` contract across sibling algorithms (greedy/astar/bfs), and A is
the form that makes the ABC pull its weight where B (a free `run(seed, target, link_cache, embed_cache)`
function) would leave it decorative. Lifetime split is the substance: caches are long-lived and
shared (constructor); seed/target are ephemeral, one pair per run (call). `base.py`'s abstract `run`
body stays inert (`...`, never `yield`) so "declares nothing runs" holds; annotate with
`collections.abc.Iterator`, not the deprecated `typing.Iterator` (we target 3.11+).

**Verify:** `tests/test_greedy.py` with FAKE caches (canned links + scores, no network, no model)
— asserts it reaches target on a toy graph, never revisits, respects TOP_K/MAX_DEPTH, yields
well-formed Steps. Then `ruff check`, review `git diff`, commit. Same cadence as steps 1-3.

### Open: user-facing tuning (physics + algorithm knobs) deferred until after MVP

Decision by the user: do not build any user-editable settings UI until a full working MVP
exists. Noted so it isn't picked up early. Two *distinct* kinds of knob, not to be blurred:

- **Algorithm / expansion knobs** (depth, node caps, K=20, heuristic weights) — live in
  `config.py` (contract 1) and change *which nodes/edges exist* (the structure Python emits).
  Exposing these is Explore mode's whole purpose, so they're the likely first to become
  user-editable.
- **Physics knobs** (spring length, repulsion, gravity, settle speed) — pure vis-network
  render config; change *how the same structure is posed on screen*, not what's in the graph.
  Cheap to expose (vis-network surfaces them) but cosmetic — polish, not core.

Keep the two separate in any future settings UI: algorithm knobs = "different graph", physics
knobs = "same graph, restyled". Merging them into one undifferentiated panel would obscure the
data-vs-rendering line, which is exactly what a tool meant to teach expansion-algorithm
behavior must keep visible. Revisit once the MVP is running (step 5+ frontend).

**User's intended shape for the algorithm-knob UI (2026-07-23):** a *pre-run* settings panel —
before starting any mode (Explore / Connect-human / Connect-AI) the user edits depth, node caps,
K, heuristic weights within ranges we define, then runs. Deliberately simpler than *live* tuning
(no mid-search re-render). Two consequences worth recording now, though the UI is post-MVP:

- **`config.py` owns both the default values AND their bounds.** The value (`K = 20`) is the knob;
  the range (`K ∈ [1, 50]`, int) is metadata the frontend needs to render a valid slider and reject
  bad input. Both live in config (contract 1) so nothing is hardcoded in the frontend either. **For
  step 4 we write config as plain constants only** (values, no bounds yet) — decided with the user;
  bounds are added when the panel is built, not before.
- **Global-vs-per-run — the real trap.** Step 4 has greedy read `config.TOP_K` as a module global,
  which is fine for a hardcoded value and fine while there's no server. But once a *user* sets K per
  run, a mutated global is shared state: two concurrent runs (e.g. two browser tabs) would stomp each
  other's settings — a genuine concurrency bug on a request-handling server, not a style nit. The
  fix, when the panel lands, is a per-run `Params`/`Settings` object built from the request and passed
  *into* `run(seed, target, params)`, superseding direct `config.*` reads. Not built now; recorded so
  the "read config directly" step-4 choice isn't mistaken later for a decision that per-run params
  were rejected. They weren't — they're just deferred with the UI.

### Roadmap step 3 (graph model + contracts) complete

`graph/contracts.py` (new) + `graph/model.py` (filled) + `tests/test_graph.py` (filled). 7 new
tests, 21 fast green, ruff clean. No new deps.

- **Contracts split into their own file, deviating from STATUS's prediction.** STATUS said `Step`
  and `MoveEvaluation` would go *in* `model.py`. Put them in `graph/contracts.py` instead: the
  contracts are consumed everywhere (algorithms emit `Step`, feedback emits `MoveEvaluation`, the
  server serializes both, the frontend renders them), while the networkx wrapper is only *one*
  consumer. Contracts import nothing from the project — they sit at the bottom of the dependency
  stack and point at nobody, so nothing can create an import cycle through them.
- **`Grade` is a `str`-Enum** so a member *is* its word (`Grade.BEST == "Best"`) and serializes to
  JSON/SSE with zero conversion. Enum (not free strings) closes the set — a typo'd grade can't exist.
  No thresholds live here; which grade a move earns stays behind contract 3 (feedback.py), per the
  2026-07-23 scoring-model entry below.
- **`MoveEvaluation.from_` carries a trailing underscore** because `from` is a Python keyword and
  can't be a field name (PEP 8 convention). Maps back to a plain `"from"` key at serialization.
- **`WikiGraph` wraps a `DiGraph`, not a `Graph`** — Wikipedia links are one-way, so edges are
  directed and `neighbors()` returns successors (out-links) only. Same single-front-door rationale
  as `WikiClient`/`Embedder`: one class owns the nx translation so the backend stays swappable.
- Node identity is the page title string (matches the cache key in `wiki/` and `embed.py`), not a
  wrapper object — one identity for a page everywhere.

### Feedback scoring model worked out ahead of step 8 (no code yet)

Conceptual session — no implementation shipped. Clarified how `feedback.py` (decision B,
contract 3) will turn cosine similarity into chess-style grades, so step 8 doesn't re-derive it:

- **One axis.** `eval(page) = cosine_similarity(embed(page), embed(target))`. A move's
  `delta = eval(to) - eval(from)`; grading compares your delta to the best neighbor's:
  `regret = best_delta - your_delta`.
- **Five grades are regret bands.** Best/Good/Inaccuracy/Mistake/Blunder are one memoryless
  computation bucketed by thresholds — no move history, no second metric.
- **Brilliant is the deliberate special case.** Requires regret ≈ 0 AND a *second* axis test
  (`cosine_similarity(link, from_page)` low = "looked unrelated but paid off"). Do NOT force all
  six grades through one formula; Brilliant's surprise predicate lives as branching inside
  `feedback.py`, which is exactly what contract 3 (feedback is the only grader) is protecting —
  the mess stays in one module, downstream only sees the `Grade` enum.
- **Reuse, not recompute.** Computing `best_delta` needs every neighbor's eval, which the
  top-K cap (decision C) already embeds; embeddings are title-cached (step 2), so the grader
  pays nothing extra. Threshold values for the bands are still TBD — placeholders when written.

No files changed except LEARN.md and this entry. Step 3 (`graph/model.py`) remains next; its
`Grade`/`MoveEvaluation` dataclasses are the contract surface this scoring logic will fill later.

---

## 2026-07-21

### Roadmap step 2 (embeddings + scoring) complete

`embed.py` implemented per brief §6 step 2. Three pieces, deliberately mirroring the `wiki/`
layering so the pattern stays consistent across the codebase:

- `cosine_similarity(a, b)` — a module-level function, not a method: pure math, no state.
  Guards `denom == 0` so a zero vector returns 0.0 instead of a NaN/divide-by-zero.
- `Embedder` — the ONLY importer of `sentence_transformers`, same single-front-door rule as
  `WikiClient` for `wikipediaapi`. Model loads lazily on first `embed()` (import lives inside
  `_get_model`), so merely importing `embed.py` never triggers the ~80MB download. This is
  also what lets the fast tests run with a fake embedder that never loads a model.
- `EmbeddingCache` — same memory → disk → compute chain as `LinkCache`, keyed by title.
  "Compute" (the model forward pass) is the expensive step the network call was in `LinkCache`.
  One wrinkle vs LinkCache: numpy arrays aren't JSON-serializable, so disk writes go through
  `.tolist()` and reads rebuild with `np.array(...)`.

Decisions made in this step:
- **Model = `sentence-transformers/all-MiniLM-L6-v2`**, stored in `config.EMBEDDING_MODEL`
  (contract 1 — a knob, not hardcoded in embed.py). Chosen as the standard small/fast default
  (~80MB, 384-dim). Swappable later without touching embed.py.
- **numpy added as an explicit dependency** (not pandas). Cosine similarity is array math, and
  the future top-K cap (decision C) wants batched vectorized ranking — numpy's job. Pandas
  would be the wrong abstraction (labeled tabular data, not homogeneous float blocks).
- **`slow` pytest marker + `addopts = "-m 'not slow'"`**: the real-model test (brief's "related
  scores higher than unrelated" proof) is deselected by default so `pytest` stays ~1s. Run it
  with `pytest -m slow`. Both were run and pass: 14 fast + 1 slow.

Next: step 3, `graph/model.py` — networkx wrapper + `Step`/`MoveEvaluation` (contracts 2, 3).

---

## 2026-07-21

### Roadmap step 1 (data layer) complete

`wiki/client.py` and `wiki/cache.py` implemented per brief §6 step 1 and committed in
`a03ce47`. Both fixes from the old repo landed: `p.ns == 0` filtering (no colon check) and
a real disk-backed cache (JSON file per title under `data/links/`), checked memory → disk →
network in that order, writing back to both layers on a network fetch.

`tests/test_wiki_client.py` proves all four things brief §6 step 1 asked for: ns0-only
filtering, UA passed to `wikipediaapi.Wikipedia`, retry-then-give-up on failure, and the
cache surviving a fresh instance (simulating a restart) via the disk layer alone. 7 tests
green, `ruff check` clean, no empty files.

Also added `LEARN.md` — separate from this file. `HISTORY.md` tracks *project* reasoning;
`LEARN.md` tracks concepts the human building this is still internalizing (classes as
toolboxes not top-down scripts, `self` binding, the wrapper-layering pattern here). Keep
them distinct — don't let personal learning notes bleed into project rationale or vice versa.

Next: step 2, `embed.py` — page-title embeddings + cosine similarity, same two-layer cache
shape as `wiki/cache.py`.

---

## 2026-07-20

### Skeleton reconciled: `conceptmap` deleted, `wikimap` scaffolded

Resolves the "skeleton does not match the brief" item below. `src/conceptmap/` and its
`tests/test_graph.py` are gone; `src/wikimap/` now matches brief §5 exactly.

The two layouts were not reconcilable by renaming — the old skeleton encoded a design the
brief replaced. `propose.py` assumed *proposed* concept associations where the brief wants
*real* hyperlinks, and `viz/render.py` + `template.html` assumed server-side HTML rendering
where the brief wants a FastAPI app serving static files that consume an SSE Step stream.
Its flat `algorithms/{bfs_threshold,greedy_beam}.py` also has no place to express the
explore-vs-connect split, which is load-bearing: the two modes anchor their top-K ranking
to different things (seed vs. target, decision C). All 14 files were 0 bytes, so nothing
was lost.

**Placeholders, not empty files.** Each scaffolded module holds a docstring naming its
responsibility and the constraint it must honor. This is deliberate — the previous skeleton
was 13 zero-byte files, and a zero-byte file cannot tell you whether it is unwritten or
belongs to a dead design. That ambiguity is what cost this session an investigation.

Two open readings of the brief, resolved by judgement and worth revisiting if they bite:

- **`embed.py` placement.** Brief §5's tree omits it entirely, but roadmap step 2 says to
  build it. Placed at `src/wikimap/embed.py`, a sibling of `feedback.py`, since both are
  shared services consumed by both modes. The tree looks like the incomplete artifact here.
- **sync vs. async fetching.** §5's stack line says "httpx (async Wikipedia calls)", but
  §2's rules and the `pyproject.toml` it supplies both say synchronous `wikipedia-api`,
  with httpx commented out as the upgrade path. Went with sync — two sources against one,
  and CLAUDE.md already documented it that way. The §5 prose is stale, not a live decision.

`pyproject.toml` is transcribed verbatim from the brief. `.gitignore` ignores `data/`
(regenerable cache, and it will get large), `.env`, and `.claude/settings.local.json`.

Note: HISTORY previously said root `algorithms.py` was "staged for deletion" — it was
actually already removed in `780a93e`. Corrected here rather than in place.

### Statusline moved from global to project scope

`.claude/statusline.ps1` and `.claude/settings.json` added. The statusline shows
model, git branch with a `●` when the tree is dirty, context %, 5-hour rate limit %,
and session cost in CAD.

Originally written to the user-level `~/.claude/statusline.ps1`, which changed the
statusline for *every* project on the machine. Reverted that file to its original
contents and reimplemented as project-scoped config, since project settings override
user settings for `statusLine`.

Notes carried forward:
- `$USD_TO_CAD = 1.37` is a **placeholder**. Claude Code only reports
  `cost.total_cost_usd`; no live rate is fetched, deliberately — the statusline runs
  after every assistant message and a network call there would add latency and a
  failure mode for two decimal places.
- Glyphs are written as `[char]0x2502` / `0x25CF` rather than literal characters.
  PowerShell 5.1 reads `.ps1` as ANSI without a UTF-8 BOM, so literals risk mangling.
- The path in `settings.json` is absolute and machine-specific. It uses forward
  slashes because Windows routes statusline commands through Git Bash when installed,
  which silently strips unquoted backslashes. If this repo ever gains a collaborator,
  move it to the gitignored `.claude/settings.local.json`.

### CLAUDE.md written from the project brief

Created from `~/Downloads/wikimap_brief.md` per its §7. Captures the three shared
contracts (config owns knobs, algorithms emit Steps, feedback is the only grader),
the Wikipedia data-layer rules, both locked decisions, and STATUS.

Deliberately inverts one rule from the predecessor repo: **this project runs inside
its venv.** `../Wikipedia Speedrun/` has a broken split install (`sentence-transformers`
and `torch` in system Python, only two deps in the venv), so its CLAUDE.md instructs
*not* to activate the venv. That failure should not be reproduced here.

### Open: skeleton does not match the brief

**Resolved same day — see "Skeleton reconciled" above.** Left in place as the record of
why the question came up.

Commit `0cfaa8a` scaffolded `src/conceptmap/` — `propose.py`, `viz/`,
`bfs_threshold.py`, `greedy_beam.py` — a superseded design based on *proposed*
concept associations. The brief specifies `src/wikimap/` over *real* Wikipedia
hyperlinks, with `wiki/`, `graph/`, `algorithms/{explore,connect}/`, `feedback.py`,
and `server/`.

All 14 skeleton files are 0 bytes, so nothing is lost by replacing them. Unresolved
pending a decision; `algorithms.py` at the repo root fits neither layout and is
currently staged for deletion. Settle the package name (`wikimap`) before step 1
writes imports against it.

## 2026-07-19

### Repo initialized

`0715154` empty `algorithms.py`. `0cfaa8a` the conceptmap skeleton above.
No implementation code yet — roadmap step 1 (data layer) not started.
