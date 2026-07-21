# HISTORY

Running log of significant changes and the reasoning behind them.

**What belongs here:** decisions and their rationale, architecture changes, reversals,
roadmap step completions, anything a future session would misread the repo without.
**What does not:** routine edits, typo fixes, anything `git log` already tells you.
This file explains *why*; git explains *what*. Newest entries at the top.

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
