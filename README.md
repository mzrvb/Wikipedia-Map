# wikimap

A locally hosted web app over the **real Wikipedia link graph** — actual article-to-article
hyperlinks, not generated or proposed associations. Two modes:

- **Explore** — seed a page and grow the graph outward. A sandbox for watching how
  expansion settings reshape the result.
- **Connect** — a Wikipedia speedrun from page A to page B, either solved by a pathfinding
  algorithm or played by hand, with chess.com-style per-move grading.

Both modes build the graph live on screen as the search runs.

## Status

**Working MVP with live settings and four algorithms — Connect is feature-complete.** Run a search
in the browser, watch the graph build live with the camera auto-fitting to it, switch between
greedy / A* / bidirectional BFS / default (bidirectional beam search), tune the search knobs, and
reshape the rendering (node size — flat, or by score/depth — forces, colour-by) from a settings
panel. A Connect/Explore toggle sits in the header — Explore is disabled until that mode is
actually built. Click any node (mid-run or after) to open a panel with its real Wikipedia summary
and a link to the article. FROM/TO fields autocomplete against real Wikipedia titles as you type.
The run log shows per-step and total-run timing (`[+123ms · 4.56s total]`), measured in the
browser. 122 fast tests green, `ruff check` clean.

Settings come in two kinds, and the split is deliberate:

| | Owned by | Changes | Stored in |
| --- | --- | --- | --- |
| **Search** — top-K, max depth, weight W, hop scale | `config.py` | what the algorithm does | server; sent as query params |
| **Display / Forces** — node size, arrows, physics, colour-by | the browser | how the graph is drawn | `localStorage` |

`max_nodes` is a search knob too, but as of 2026-07-30 it's read by `bfs` alone — greedy/astar/
default are already bounded by `top-K` per tick, so a separate node cap never did real work for
them (see `HISTORY.md`).

A physics slider can never reach the algorithm, so it never goes near `config.py`. The rule:
*changes the search → `config.py`; changes the picture → frontend.*

| Step | What | State |
| --- | --- | --- |
| 1 | Data layer — `wiki/client.py` (ns0 filtering, UA, retry) + two-layer disk-backed cache | done |
| 2 | Embeddings — `embed.py`: cosine similarity, lazy-loaded model, cached by title | done |
| 3 | Graph model + contracts — `graph/contracts.py` (`Step`, `Grade`, …), `graph/model.py` | done |
| 4 | First Connect algorithm — `algorithms/base.py` ABC + `connect/greedy.py` | done |
| 5 | FastAPI + SSE server streaming Steps to a vis-network frontend | done |
| 6 | Per-run params — knobs travel as `run()` arguments, wired to UI controls | done |
| 7a | `connect/astar.py` — weighted A* on the semantic heuristic | done |
| 7b | `connect/bfs.py` — bidirectional, uncapped, ground truth for the other two | done |
| 7c | `connect/default.py` — bidirectional beam search, the app's default | done |
| 8 | Explore mode — `explore/bfs.py`, `explore/beam.py` | next |

Sample run — `Cat → Astronomy`, the same pair under both algorithms:

```
greedy (4 hops), similarity climbing each move:
  'Cat' -> 'Science (journal)'              (score 0.460)
  'Science (journal)' -> 'Spiral nebulae'   (score 0.542)
  'Spiral nebulae' -> 'Galactic astronomy'  (score 0.794)
  'Galactic astronomy' -> 'Astronomy'       (score 1.000)

A* (3 hops), ordering by f = g + W·h:
  expand 'Cat'               (g=0, h=3.20, f=3.20)
  expand 'Science (journal)' (g=1, h=2.16, f=3.16)
  ...
  reached 'Astronomy' in 3 hops: Cat -> Age of Discovery -> Astronomer -> Astronomy
```

A* usually finds shorter routes but expands more pages. Note it is **not guaranteed** to find the
shortest one — the cosine heuristic can overestimate, and a 2-hop route (`Cat → Night vision →
Astronomy`) exists that the default settings miss. Lowering the weight `W` searches more widely and
costs more expansions; `W = 0` orders purely by hops and `W` very large reproduces greedy.

First run for a given page is slow (~80s here) — it fetches every link and embeds each one. The
two-layer cache makes the same run near-instant afterwards (<0.01s). `default.py` cuts cold-run
cost two ways: frontier fetches within a ply run concurrently (a thread pool, not sequential
requests), and a ply's cache-miss titles are embedded in one batched `model.encode(list)` call
instead of one call per title. Neither changes search behavior — same ranking, same output.

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
| `GET /api/connect?…&algorithm=greedy\|astar\|bfs\|default` | Which Connect algorithm to run (default `default`) |
| `GET /api/connect?…&top_k=&max_depth=&max_nodes=&heuristic_weight=&hop_scale=` | Per-run knobs. All optional; out-of-range values give a 422 |
| `GET /api/config` | The knobs *and their bounds*, read-only (contract 1: the frontend never hardcodes them) |
| `GET /api/page?title=` | One page's real Wikipedia summary + URL, fetched on demand when a node is clicked |
| `GET /api/suggest?q=` | Real Wikipedia title suggestions for the FROM/TO autocomplete dropdowns |

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
