# HISTORY

Running log of significant changes and the reasoning behind them.

**What belongs here:** decisions and their rationale, architecture changes, reversals,
roadmap step completions, anything a future session would misread the repo without.
**What does not:** routine edits, typo fixes, anything `git log` already tells you.
This file explains *why*; git explains *what*. Newest entries at the top.

---

## 2026-07-20

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
