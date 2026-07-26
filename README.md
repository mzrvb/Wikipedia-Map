# wikimap

A locally hosted web app over the **real Wikipedia link graph** — actual article-to-article
hyperlinks, not generated or proposed associations. Two modes:

- **Explore** — seed a page and grow the graph outward. A sandbox for watching how
  expansion settings reshape the result.
- **Connect** — a Wikipedia speedrun from page A to page B, either solved by a pathfinding
  algorithm or played by hand, with chess.com-style per-move grading.

Both modes build the graph live on screen as the search runs.

## Status

**Working MVP with live settings.** Roadmap steps 1–6 done — run a Connect search in the browser,
watch the graph build live, and change the search knobs between runs. 59 fast tests green,
`ruff check` clean.

| Step | What | State |
| --- | --- | --- |
| 1 | Data layer — `wiki/client.py` (ns0 filtering, UA, retry) + two-layer disk-backed cache | done |
| 2 | Embeddings — `embed.py`: cosine similarity, lazy-loaded model, cached by title | done |
| 3 | Graph model + contracts — `graph/contracts.py` (`Step`, `Grade`, …), `graph/model.py` | done |
| 4 | First Connect algorithm — `algorithms/base.py` ABC + `connect/greedy.py` | done |
| 5 | FastAPI + SSE server streaming Steps to a vis-network frontend | done |
| 6 | Per-run params — knobs travel as `run()` arguments, wired to UI controls | done |
| 7 | Rest of Connect — `connect/astar.py`, then bidirectional `connect/bfs.py` | next |
| 8 | Explore mode — `explore/bfs.py`, `explore/beam.py` | after Connect |

Sample run — `Cat → Astronomy`, solved in 4 hops with the similarity score climbing each move:

```
start: 'Cat' (target 'Astronomy')
'Cat' -> 'Science (journal)'        (score 0.460)
'Science (journal)' -> 'Spiral nebulae'      (score 0.542)
'Spiral nebulae' -> 'Galactic astronomy'     (score 0.794)
'Galactic astronomy' -> 'Astronomy'          (score 1.000)
```

First run for a given page is slow (~80s here) — it fetches every link and embeds each one. The
two-layer cache makes the same run near-instant afterwards (<0.01s).

Everything under `src/wikimap/` beyond `wiki/`, `embed.py`, `graph/`, and `algorithms/` is still
a placeholder — a module docstring stating that file's responsibility, no implementation.

Two deviations from the brief's ordering, both deliberate:

- Brief §6 step 4 is headless *Explore* (`explore/bfs.py`); what was actually built is Connect's
  greedy. Steps 5+ are unaffected — the server work is the same either way — but the rationale
  was never recorded.
- The brief puts the Explore settings UI at step 6 and the rest of Connect at step 7. **Reversed
  on 2026-07-26:** Connect is finished first so one mode is coherent and shippable, and so the
  pieces Explore will share are proven by several Connect algorithms before being generalised.
  See `HISTORY.md`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env    # then fill in USER_AGENT
```

Python 3.11+. Every dependency — including `sentence-transformers` and `torch` — installs
into the venv.

## Running

```powershell
pytest                  # tests
ruff check .            # lint
```

The server serves the API and the frontend together — open <http://127.0.0.1:8000>, enter two page
titles, press Run:

```powershell
uvicorn wikimap.server.app:app --reload
```

| Endpoint | What |
| --- | --- |
| `GET /` | The frontend (form, graph canvas, run log) |
| `GET /api/connect?seed=&target=` | SSE stream — one `step` event per algorithm tick |
| `GET /api/connect?…&top_k=&max_depth=&max_nodes=` | Same, with per-run knobs. All optional; out-of-range values give a 422 |
| `GET /api/config` | The knobs *and their bounds*, read-only (contract 1: the frontend never hardcodes them) |

Settings are per request, not global state — two browser tabs can run different `top_k` values
without interfering. `top_k` is capped at 20 (locked decision C: uncapped expansion reaches ~27M
nodes by depth 3).

## Layout

| Path | What lives there |
| --- | --- |
| `src/wikimap/config.py` | Every tunable knob, in one place |
| `src/wikimap/wiki/` | The only code that talks to MediaWiki (`client.py`, `cache.py`) |
| `src/wikimap/graph/` | networkx model + the `Step` and `MoveEvaluation` contracts |
| `src/wikimap/algorithms/` | `explore/` and `connect/` search implementations |
| `src/wikimap/embed.py` | Title embeddings + cosine similarity, cached |
| `src/wikimap/feedback.py` | Move grading — the only grader |
| `src/wikimap/server/` | FastAPI app, SSE stream, static frontend |

See `CLAUDE.md` for the architecture rules and `HISTORY.md` for why they are what they are.
