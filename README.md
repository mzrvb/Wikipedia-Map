# wikimap

A locally hosted web app over the **real Wikipedia link graph** — actual article-to-article
hyperlinks, not generated or proposed associations. Two modes:

- **Explore** — seed a page and grow the graph outward. A sandbox for watching how
  expansion settings reshape the result.
- **Connect** — a Wikipedia speedrun from page A to page B, either solved by a pathfinding
  algorithm or played by hand, with chess.com-style per-move grading.

Both modes build the graph live on screen as the search runs.

## Status

Scaffolded; roadmap step 1 (the data layer) not started. The tree under `src/wikimap/` is
placeholders — module docstrings stating each file's responsibility, no implementation yet.

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
