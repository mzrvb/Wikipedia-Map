# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read [`HISTORY.md`](HISTORY.md) before starting work.** This file says what the rules
*are*; `HISTORY.md` says *why* they are that way, which decisions were reversed, and which
values are placeholders. It also carries the open questions that STATUS only summarizes.
Update it alongside this file — see [Working practice](#working-practice).

## STATUS

**Roadmap step 1 (data layer) — not started. No implementation code exists yet.**

The package layout is settled: `src/wikimap/`, matching brief §5. The superseded
`src/conceptmap/` skeleton has been deleted. `pyproject.toml`, `.gitignore`, `.env.example`,
and `README.md` are in place; the venv has not been created and nothing is installed.

Every module under `src/wikimap/` is a placeholder holding only a docstring that states
that file's responsibility. Step 1 fills in `wiki/client.py` and `wiki/cache.py` first.

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

**Log significant changes in [`HISTORY.md`](HISTORY.md).** Add an entry when you complete a roadmap step,
make or reverse an architectural decision, introduce a placeholder or known-wrong value, or
do something a future session would otherwise misread. Record the *reasoning*, not just the
change — `git log` already covers what changed. Skip routine edits. Newest entry at the top,
under a date heading. Update the STATUS section above in the same pass.
