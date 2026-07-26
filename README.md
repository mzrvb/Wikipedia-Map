# wikimap

A locally hosted web app over the **real Wikipedia link graph** — actual article-to-article
hyperlinks, not generated or proposed associations. Two modes:

- **Explore** — seed a page and grow the graph outward. A sandbox for watching how
  expansion settings reshape the result.
- **Connect** — a Wikipedia speedrun from page A to page B, either solved by a pathfinding
  algorithm or played by hand, with chess.com-style per-move grading.

Both modes build the graph live on screen as the search runs.

## Status

Roadmap steps 1–4 done; **step 5 (server + live graph) is next.** 30 fast tests green,
`ruff check` clean.

| Step | What | State |
| --- | --- | --- |
| 1 | Data layer — `wiki/client.py` (ns0 filtering, UA, retry) + two-layer disk-backed cache | done |
| 2 | Embeddings — `embed.py`: cosine similarity, lazy-loaded model, cached by title | done |
| 3 | Graph model + contracts — `graph/contracts.py` (`Step`, `Grade`, …), `graph/model.py` | done |
| 4 | First Connect algorithm — `algorithms/base.py` ABC + `connect/greedy.py` | done |
| 5 | FastAPI + SSE server streaming Steps to a vis-network frontend | next |

Everything under `src/wikimap/` beyond `wiki/`, `embed.py`, `graph/`, and `algorithms/` is still
a placeholder — a module docstring stating that file's responsibility, no implementation.

Note a deviation from the brief's ordering: brief §6 step 4 is headless *Explore*
(`explore/bfs.py`); what was actually built is Connect's greedy. Steps 5+ are unaffected — the
server work is the same either way — but the rationale was never recorded.

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

Once the server lands (roadmap step 5), it serves the API and the frontend together:

```powershell
uvicorn wikimap.server.app:app --reload
```

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
