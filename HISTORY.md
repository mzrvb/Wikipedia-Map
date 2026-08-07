# HISTORY

Running log of significant changes and the reasoning behind them.

**What belongs here:** decisions and their rationale, architecture changes, reversals,
roadmap step completions, anything a future session would misread the repo without.
**What does not:** routine edits, typo fixes, anything `git log` already tells you.
This file explains *why*; git explains *what*. Newest entries at the top.

---

## 2026-08-07 — Connect human-play UI built (new standalone page, backend session)

The backend already had everything human-play needs — `GET /api/article` (real Wikipedia HTML
with every link pre-marked `wm-link`/`wm-disabled`, from `wiki/article.py`), `POST
/api/evaluate_run` (batch grading through `feedback.py`, contract 3), plus `/api/suggest` and
`/api/page`. Nothing on the frontend consumed any of it. This session built that consumer.

**Built as a SEPARATE page — `static/play.{html,js,css}` — not bolted into `index.html`/`app.js`.**
Two reasons, one architectural and one practical:
- *Architectural:* the AI-solver view is a force-directed vis-network canvas watching an algorithm
  search; human-play is an article reader where the human IS the search. They share the backend and
  the header look and nothing else, so sharing a 1100-line `app.js` built entirely around
  vis-network would be forcing two unrelated interactions into one file. They ship no JS in common
  by design (the autocomplete is deliberately re-implemented compactly in `play.js` rather than
  extracted — same hard-won lessons baked in: debounce, stale-response `seq` guard,
  `document.activeElement` focus guard, mousedown-not-click).
- *Practical:* `app.js`/`index.html`/`CLAUDE.md`/`HISTORY.md` were dirty from a parallel frontend
  session this same day. A separate page kept this work off their files entirely (only these two
  shared docs are touched, by prepend).

**The game loop (`play.js`):** three screens (start → play → recap) toggled by `showScreen`. Start
resolves both fields to a real title via `/api/suggest` before beginning (the exact fix `app.js`
made 2026-07-31 — the grader compares titles with `==`, so `astronomy` must become `Astronomy`);
`seed == target` is handled as a trivial 0-move win. `navigate(title, {record})` is the core: it
records a `{from, to}` move (except for the opening seed landing), pushes the breadcrumb, checks
`title === target` BEFORE fetching (no point rendering the target just to cover it with the recap),
then `innerHTML`s the annotated article. One delegated click listener on `#article` handles every
`a.wm-link` (delegation, not per-link, because the innerHTML is rebuilt each navigation);
`wm-disabled`/other `<a>` clicks are swallowed so a stray `href="#"` can't jump the page. On finish
(reached or gave up) it POSTs the whole move list to `/api/evaluate_run` and renders one badge per
move, coloured by grade.

**`innerHTML` is used deliberately and safely** for the article body: the server already stripped
`<script>`/`<style>` and re-escaped all text in `wiki/article.py`, and that HTML is *designed* to be
spliced into the DOM (the whole `wm-link`/`data-title` scheme only works if it is). Page titles
everywhere else (breadcrumb, autocomplete, recap) use `textContent` — untrusted Wikipedia text.

**No backend change, no contract change, no Python touched.** The page is served by the existing
`StaticFiles(html=True)` mount, reachable at `/play.html`. It is NOT yet linked from `index.html`'s
header toggle — that's the integration point once the frontend session's `app.js` work lands, and
was left undone rather than edit into the middle of their uncommitted changes.

**Verified live against the running dev server**, not just static-checked: `/play.html` serves 200;
`/api/article?title=Cat` returned 758 KB with 1755 `wm-link` / 1543 `wm-disabled` annotations and 0
`<script>` tags, sample `<a href="#" class="wm-link" data-title="Felidae">` matching exactly what
`play.js` delegates on; a real two-move POST to `/api/evaluate_run` (`Cat→Felidae→Astronomy`, target
Astronomy) graded `Felidae` **Inaccuracy** (ranked 561/1181, delta −0.058) and `Astronomy`
**Brilliant** (reached, delta +0.857), response shape matching `renderEvaluations` exactly.
`node --check` clean, no empty files. Not yet click-tested in a real browser (no browser-automation
tool this session) — the DOM interactions (delegated clicks, screen toggles) are the one part
proven only by reading, same caveat as several earlier frontend passes.

## 2026-08-06 — Run-log redesign: transit-map direction chosen, spec locked, nothing built yet

Design-only session, no code changed. Two directions were explored to replace the twin-rail
"Interchange" log: a dual candlestick chart (scratch mockup, throwaway HTML in a temp
scratchpad — not in the repo, not linked from anywhere, treat it as gone) and a transit-map
style with circular "station" stops, which the user is prototyping directly in Canva and has
now locked several decisions on. **The candlestick direction is parked, not chosen.**

**Locked so far, from a live Canva reference (`Screenshot 2026-08-06 025524.png`, user's
machine, not in the repo):** two thick vertical rounded-pill rails (green = seed/forward,
purple = target/backward, both a genuine palette departure from the current blue/orange),
white-fill/black-stroke circular stops, one stop per depth per side. The two rails curve into
a shared gold U-turn loop at the terminal (destination) row instead of the current diamond +
bridge. User-facing label is **"Depth N", not "round N"** (same integer either way — this only
changes display text). Each stop's subline format is now
**`[x seconds, +k links, x+ total seconds]`** — `+k links` is what keeps a single-title-per-depth
station from implying the search only ever considered one page; the actual frontier is up to
top-K (20) candidates per side per round, not one. Header also gains a compressed second copy of
the same convergence metaphor: an empty box next to SEED/TARGET, meant to hold a plain
progress bar, green filling from the left, purple from the right.

**Open, not yet answered:** which of a round's up to 20 candidates becomes "the" station name —
presumably highest score that round, but no tiebreak rule exists yet for near-ties. This is a
data/ranking decision, not a styling one, and matters more than it looks: labeling one page per
round risks re-implying a single evolving path per side, which is the exact misreading the
2026-08-02 twin-rail rework (below) was built to correct for the AI's real bidirectional-beam
behavior. Worth resolving before implementation, not after.

**Feasibility read, not yet built:** the rail/stop mechanics are believed to be a re-skin of the
existing `.rails`/`.rails-cap` row-stacking technique (`style.css`) that already makes the
current log grow live as rows append — thicker/colored bars and white dots instead of thin grey
lines and colored dots, no new growth mechanism needed. The gold U-turn only ever appears once,
on the terminal row, at a fixed known gap between the two rail x-positions (same reasoning
`--dot-x`/`--col-gap` already rely on) — so it's judged to be a single fixed-size SVG/CSS asset
swapped in at the end, not a per-round computed curve. Unverified — no prototype built against
this reasoning yet.

---

## 2026-08-05 — Auto-fit graph hidden behind the settings panel — fixed; redundant "round N:" log tag removed

User-requested pass: drive several short live Connect runs in a real browser and fix whatever
"doesn't fit," plus drop the repeated `round N:` prefix from the twin-rail log. No
`claude-in-chrome`-style tool available, so a scratch Playwright/Chromium venv (discarded after)
drove the real dev server, same as every earlier frontend pass here.

**Auto-fit bug, confirmed live:** `network.fit()` frames the graph against the FULL `#graph`
canvas rect, but `#panel`/`#node-panel` are floating siblings covering part of that same canvas
(siblings, not children — see index.html). `fit()` has no way to know they're there. Measured by
converting `getPositions()` to screen space via `canvasToDOM()` against `getBoundingClientRect()`:
a 1-hop `Dog -> Cat` run had 2/40 nodes under the settings panel; `Cat -> Astronomy` (81 nodes) had
7 — a normal short run, not an edge case.

Fixed with a new `fitGraph()` (`app.js`): computes the graph's bounding box, builds a "safe"
rectangle (canvas minus whichever panel is open), and calls `network.moveTo()` to center/scale
into that instead of the full canvas — falls back to the full canvas if both panels open would
leave under 100px safe width. Re-measured: 0/40, 0/81, and 0/81 with both panels open at once.
Frontend-only; `moveTo()` drives the same view `fit()` would have, so nothing downstream breaks.

**Round-tag redundancy:** each round row showed `round N: X fwd` / `round N: X bwd` — the same
number said twice on one row. Removed the prefix from both columns (`logStep()`), leaving `X fwd`
/ `X bwd` — row position already conveys the round, same as origin/destination/exhausted rows.
Deleted the now-unused `roundNumber` counter rather than leave it dead.

`ruff check`/`node --check` clean, 109 fast tests green (frontend-only).

---

## 2026-08-02 — `feedback.py` implemented: rank-based move grading (contract 3) — docs backfilled

Landed by a parallel backend session as commit `9eb769f` with no HISTORY/CLAUDE/README update in
the same commit — recorded here after the fact so the doc trail doesn't have a silent gap where a
real contract went from placeholder to implemented.

`feedback.py` was a docstring-only placeholder until now; `evaluate_move()` is the first real
implementation of contract 3 (`feedback.py` is the only grader). Grading is **rank-based, not an
absolute cosine-similarity threshold**: a move is graded by where its destination ranks, by
similarity to the target, among every real (ns0) link the page it was played from actually
offered — not restricted to the algorithm's top-K, since a human player can click any link on the
page, not just the ones an algorithm would have kept. This matters because the same raw cosine
score means something different on different pages: 0.3 similarity can be the best (or only)
option on a weak page and a lazy pick on a strong one, so an absolute threshold would grade the
same number two different ways depending on context, which a rank comparison can't be fooled by.
Reaching the target directly is graded `Brilliant` unconditionally, bypassing the rank comparison
entirely — there's nothing to rank a "found it" move against.

The five grade boundaries (`Best`/`Good`/`Inaccuracy`/`Mistake`/`Blunder`, split by percentile
rank among a page's available links) are an explicit **placeholder**, flagged in the module
docstring with the same status as `config.py`'s `MAX_DEPTH`: reasonable-looking guesses, not yet
tuned against real human play. Do not adjust the percentile cutoffs without live playtesting data
to justify a specific change — same rule this project already applies to `MAX_DEPTH`.

This is backend-only groundwork for Connect's human-play mode, which does not exist yet — nothing
in the server or frontend calls `evaluate_move()` today. `link_cache`/`embed_cache` are injected
the same way every algorithm already receives them (Option A), so grading a move costs no new
fetch when the page was just rendered for a player to click through. 6 new tests in
`tests/test_feedback.py` (direct-hit Brilliant, top/bottom/middle rank, and that grading responds
to a page's own link set rather than a fixed score cutoff); 109 fast tests green overall as of
this backfill, `ruff check` clean.

## 2026-08-02 — Twin-rail log overlap fixed, a found-banner added, and an autocomplete race fixed alongside it

The twin-rail "Interchange" log rework (previous entry below) had never been checked in a real
browser — every prior pass here verified with `node --check` and a curl 200 only. This pass
installed Playwright + headless Chromium into a scratch venv (same approach as the Forces-slider
measurement session) and actually drove the running dev server through a real `Cat -> Astronomy`
Connect run, screenshotting `#log` and reading real `getBoundingClientRect()` numbers instead of
guessing from the CSS. That surfaced a real bug the static checks couldn't have caught: on the
origin/destination/exhausted rows, the dot's text ("st**a**rt: 'Cat'...") was rendering with its
first few characters hidden UNDER the dot itself, and the bridge line cut across the middle of the
wrapped text.

**Root cause.** Those three row kinds are a two-row CSS Grid: a "dots" row (`.col.fwd`/`.col.bwd`)
above a "caption" row (`.shared-label`, `grid-column: 1 / -1`). But `.col`'s only child content for
these three kinds is an empty-string `.label` (the real text lives in `.shared-label` below, not in
the column itself), and `.dot` is `position: absolute` — so neither contributes any intrinsic
height to `.col`. With both grid items in row 1 reporting 0 height, that row's track collapsed to
0px, and row 2 (`.shared-label`) started at the exact same y-coordinate as row 1. The dot's
`top: 7px` (and the bridge's `top: 13px`), both offsets computed on the assumption of a real
dots-row height, ended up landing 7-13px into what was visually the caption's own text instead.
Round rows never showed this because their `.label` always holds real text ("round 1: 20 fwd"),
which gives `.col` genuine height — the bug only affects rows with an empty per-column label and a
separate full-width caption.

**Fix**, confirmed via a second bounding-box read after the change (9px/6px clear gap between the
dot and the caption's first line, vs. touching/overlapping before): `#log .row .col` gained
`min-height: 28px` — enough to clear the tallest marker (destination's rotated diamond, whose
rotated bounding box is ~19.8px, centered on the same `top: 7px` origin as the round dots) with a
few px of margin either side. Round rows are unaffected: their real label text already exceeds
28px of line height, so the min-height is a no-op there. Also gave `.shared-label` and `.meta`
matching `padding-left: 22px` (previously 0) so their text starts flush under the round rows'
labels above/below them instead of at the row's bare left edge — a secondary misalignment, not an
overlap, caught in the same visual pass.

**Found banner added**, the second half of what was asked for this pass ("make the UI more
presentable once a connection is found"). A floating pill (`#found-banner` in `index.html`, a
sibling of `#graph`/`#panel`/`#node-panel` — same nesting rule as those, for the same reason:
vis-network's `Canvas._create()` wipes any child it's handed). Centered top (`left: 50%`,
`transform: translateX(-50%)`), clear of `#node-panel` (left:12) and `#panel` (right:12) at the
same `top: 12px`. Deliberately reuses `step.path`'s own terminal `Step.note` verbatim as its text
(`showFoundBanner(step.note)` in `applyStep()`, right next to the existing `highlightPath(step.path)`
call) rather than composing a second "reached X in N hops" phrasing — this is a display-only
convenience, not a new source of truth, and a second hand-rolled phrasing could drift from what the
log already says while this one structurally can't. Same amber (`#facc15`) as the log's destination
diamonds and the graph's path highlight (`PATH_COLOR`), so all three reinforce one "this is the
answer" signal instead of adding a fourth hue. Dismissible (`#found-banner-close`, same `.hint`-style
button pattern as `#node-panel-close`); cleared automatically by `resetLog()` so a fresh run or
replay never shows a stale banner from the previous one.

**A real, unrelated bug found and fixed along the way**, because it was actively undermining the
found-banner's presentability in the same screenshots: `setupAutocomplete()`'s suggestion dropdown
(`app.js`, built 2026-07-30) could reopen itself AFTER the input blurred. The debounced
`fetchSuggestions(query).then(...)` callback only guarded against a STALE query (`input.value.trim()
!== query`) — it never checked whether the input was still focused. Sequence: type → debounce timer
fires → fetch sent → user clicks Run before the response lands → `blur` fires `hide()` → the
in-flight fetch resolves moments later, the query text is still unchanged (so the stale guard passes),
and `renderSuggestions()` reopens the list regardless — a dropdown that outlives the run and sits on
top of the graph and the new banner. This is a genuine race, not a headless-browser-only artifact:
it reproduces any time a response arrives after the user has already moved on, which typing-then-
clicking-Run does routinely. Fixed with a second guard, `if (document.activeElement !== input) return;`,
alongside the existing stale-query check. Re-verified live: a full run + screenshot after the fix
shows no leftover dropdown.

All three fixes are frontend-only (`app.js`, `style.css`, `index.html`), no contract/server/Python
change. Not yet re-run through the fast test suite (frontend-only, nothing there to break), but this
pass — unlike every prior frontend-only pass this project — is the first one actually confirmed
against a live, rendered page rather than static syntax checks alone.

---

## 2026-08-02 — Center force: full re-measurement pass, range widened again with actual margins

The lock-to-default fix worked but was a stopgap, not a design — it removed the ability to
tighten the layout at all. User asked for the range to be re-derived properly this time: measure
the real scaling in Chromium, iterate several candidate configs, and pick min/max/default from
that data instead of patching one variable per complaint cycle.

**Method.** Swept `centralGravity` 0.30/0.35/0.40/0.45 against two graph instances (a fresh
`Cat -> Astronomy` run and a second re-run of the same pair forced through a deeper `max_depth`
ceiling via the disabled-but-JS-settable `#max_depth` input — confirmed structurally identical,
81 nodes both times, since `default.py` stops at the real meeting point regardless of the
ceiling, but a genuinely independent re-settle, not a cached repeat), 2 trials each, sampling
`network.getPositions()` every 150ms. Also re-swept label visibility at `centralGravity`
0.003-0.008 on both graphs to confirm the existing 0.005 floor still holds.

**Result:** 0.30/0.35/0.40 settled to 0px/frame on every trial on both graphs; 0.45 flaked once
(3-8px/frame non-decaying drift on 1 of 4 trials) — consistent with the earlier binary search
placing the real instability boundary between 0.40 and 0.45. Chose `data-log-max=0.35`, not 0.40:
0.40 tested clean here too, but it's the exact number that was already shipped when the user
reported this still felt broken last round, so it gets no benefit of the doubt — 0.35 buys a full
extra step of margin below the confirmed-flaky value. `data-log-min` stays `0.005`. Re-verified
against the real file end to end: a 10-unit-step sweep from 0.005 to 0.35 produced a flat
14.9-19.9% radius drop every single step (matching a `radius ~ centralGravity^-0.5` power-law fit
computed from the original 11-point sweep at the old bounds) — no dead zones, no runaway zone.
Default raw recalculated to keep resolving to the same semantic default, `centralGravity≈0.0099`.

**A false alarm caught and corrected in the same pass, worth recording on its own:** a
repeated-trial check at the new top edge flaked once in 4 tries at a 2.5-second settle window —
which looked exactly like the earlier confirmed cg=0.5 instability. Before shipping 0.35 anyway,
re-ran that exact flaky transition 6 times watching a full 12 seconds instead of 2.5: every trial
decayed smoothly and completely to 0px/frame, some just taking ~3.5s instead of ~2.5s — an
ordinary damped settle after a sudden parameter jump (a brief spike over 100px/frame, then a
monotonic decay to exactly zero), not oscillation. That is categorically different from the
confirmed real instability at `centralGravity≈0.5`, which stayed at 2.6-11.9px/frame with no
decay trend even 9 seconds in (re-checked against that original data to make sure this wasn't the
same failure mode wearing a different number). The lesson, for the next time a jitter probe reads
"unsettled": that reading only means something if the observation window is long enough to rule
out a slow-but-ordinary settle — 2-3 seconds was not, for this graph size; 12 seconds reliably is.
Without that recheck, this pass would have shipped a fourth number chosen to dodge a bug that was
never actually there, which is exactly the failure pattern the last three cycles fell into.

## 2026-08-02 — Center force: slider's max hard-capped to the shipped default, ending the loop

Fourth report the same day ("still broken... is there no way to cap the highest center force
slider option to the default center force option?") after curve-shape, floor, and ceiling fixes
all failed to satisfy the complaint. Rather than another measure-and-cap cycle, took the user's
suggestion literally: `data-log-max` on `#d-centralGravity` is now `0.01` — the exact shipped
default `centralGravity` value, not a number chosen to sit safely above it. Confirmed live against
the real file: raw=100 resolves to exactly `0.01`, raw=0 to exactly `0.005` (unchanged floor from
the earlier labels-vanish fix), raw=50 to the geometric midpoint `0.00707`. The slider can now only
ever *loosen* the layout from the default; it is structurally impossible to drag it into the
unstable zone found in the previous entry (`>=0.456`), because that zone is no longer part of the
range at all — this isn't "verified safe," it's "not reachable," a stronger guarantee than
anything the last three passes produced. If a use case ever needs MORE central pull than the
default, that requires deliberately re-opening this range and re-doing the stability sweep from
the previous entry — not guessing a bigger ceiling.

## 2026-08-02 — Center force "insanely sensitive" — real cause was physics instability, not the slider curve

Third report in one day about this same control ("center force slider is still insanely
sensitive"), after the log-scale remap and the label-vanish fix above. Both of those fixes were
real, but neither was the actual complaint — this time the culprit wasn't the slider's math at
all, it was the physics simulation itself.

**Method, to avoid a fourth failed cycle:** rather than re-measuring radius/percentage-per-step
again (already proven clean twice), wrote a Playwright probe that samples `network.getPositions()`
repeatedly (every 150ms, well after the initial settle window) and measures frame-to-frame node
movement — i.e. "has the layout actually stopped moving," not "what does it look like once it
stops." Also simulated a real mouse-down/move/up drag on the slider element itself, not just a
scripted value change, to rule out a test-methodology gap.

**The bug:** the forceAtlas2Based solver genuinely never converges once `centralGravity` gets
close to the old ceiling of 0.5, given this graph's other physics defaults (`repel=70`, raised in
an earlier pass the same day). Binary-searched live on the real 81-node `Cat -> Astronomy` graph:
every value at or below `raw=97` (`centralGravity<=0.436`) reliably settled to 0px/frame movement
across repeated trials; `raw=98-100` (`0.456-0.5`) was flaky-to-reliably unstable, and the old
ceiling itself (`raw=100`, `centralGravity=0.5` exactly) showed 6-17px of persistent per-frame
drift that had not decayed even after 6+ seconds of waiting — a genuine, non-decaying oscillation
(a limit cycle), not a rendering artifact or a slow settle. Dragging anywhere near the top of the
old range put the simulation into a state that visually never stops jittering — which is exactly
what "insanely sensitive" describes, and no amount of re-shaping the raw-to-value curve could have
fixed it, since the bug was in the physics, not the mapping.

**Fix:** lowered `data-log-max` on `#d-centralGravity` from `0.5` to `0.4` (`index.html`) — chosen
with margin below the live-confirmed stable boundary (`<=0.436`), re-verified by sweeping the
entire new 0-100 raw range and re-testing the new top edge (`raw=100` -> `centralGravity=0.4`)
three separate times, all settling to 0px/frame. `data-log-min` (0.005, from the previous fix)
is untouched. Default raw value recalculated `15` -> `16` to keep resolving to the same semantic
default, `centralGravity≈0.01` (now 0.0101, was 0.00998) — confirmed live against the actual
file on page load, not just computed by hand.

**Considered and explicitly NOT done:** raising the solver's `damping` option, or lowering the
`repel` default back down, either of which might also suppress the oscillation. Both were left
alone because a quick live test of a `damping` bump did not clearly help (if anything looked
worse in one trial) and neither was swept properly — shipping an unverified physics tweak here
would repeat exactly the mistake this whole entry is about. Capping the slider's reachable range
below a directly-measured stable boundary is the only change in this pass with live evidence
behind it.

## 2026-08-02 — Center force's log-scale fix had a real regression: labels could vanish entirely

User reported Center force was "still fucked" after the log-scale fix earlier today. First
re-measurement pass (same Chromium/Playwright approach, scratch venv) came back clean —
fine-grained single-unit sweeps, a 3-second hold-and-sample drift check, and a rapid full-range
sweep all showed smooth, monotonic, non-oscillating behavior, no console errors. That result
didn't match the report, which was the signal to look at something other than the numbers already
being tracked (radius/scale/drift) — so screenshots across a slow settle at several raw slider
values were taken and actually looked at, not just measured.

**The bug:** at the loose end of the (new) Center-force range, auto-fit correctly zooms out to
frame the now-larger graph — but zooming out crosses the independent "Text fade threshold"
control's cutoff (default 0.4), and `applyLabelFade()` drops every label's font to 0. Confirmed
by screenshot: `raw=0` and `raw=15` rendered two clean, well-organized node clusters with **zero
text anywhere on screen** — not corrupted, not overlapping, just completely unlabeled. A
graph with no labels is not able to do its one job (show *which* page is which), so however
correct the underlying physics numbers were, this reads as completely broken to a user touching
the slider.

**Why this is a regression from *this same day's* earlier fix, not a pre-existing bug someone
else's slider would have hit:** the failure mode already existed before the log-scale change —
literal `centralGravity=0` always produced this same zoomed-out, label-free state. But the old
*linear* 0-0.5 slider kept its shipped default at `0.01`, only 2% of the way across the range, so
a user had to drag almost the entire way to the far edge to ever reach the broken zone, and the
slider's coarse 0.005 step made landing exactly there unlikely by accident. Putting the same
range on a log scale (to fix the unrelated "too sensitive" complaint) gave the loose end roughly
a third of the slider's total length — turning a corner case nobody would practically hit into
one a user exploring the control lands on almost immediately.

**Fix:** raised `data-log-min` on `#d-centralGravity` from `0.002` to `0.005` (`index.html`) —
chosen so the loosest possible setting keeps the reference 81-node `Cat -> Astronomy` graph's
auto-fit scale at 0.445, just above the shipped 0.4 label-fade default, confirmed both by the
`network.getScale()`/`labelsVisible` reading at every 10-unit step of a full re-sweep (all `true`,
where the previous bounds went `false` below roughly raw=20) and by a screenshot at `raw=0`
showing every label intact. Default position recalculated for the new bounds (`raw=15`, still
resolving to `centralGravity≈0.01`, the original semantic default) and the sensitivity curve
re-checked: still a consistent ~16-21% change per 10-unit step across the *entire* range, if
anything smoother than the first cut. A user who wants a looser view than the new floor allows
still has one lever for it — the separate Text-fade-threshold slider — it just no longer happens
by accident from a control that has nothing to do with text.

Root-cause note for next time this class of bug shows up: the earlier verification pass measured
exactly the things it set out to fix (radius, percentage-per-step, drift) and every one of those
came back correct — the regression was invisible to that instrumentation because it lived in an
interaction with a *different* control (Text-fade-threshold) that nothing was watching. Screenshots
caught it in about two minutes once actually taken; the numeric probes alone, run twice, did not.

## 2026-08-02 — Run log reworked: single transit-map rail → twin-rail "Interchange" diagram

The run log's 2026-07-31 styling (see that entry below) drew the run as ONE rail, stops
appended top-to-bottom in arrival order — a metaphor explicitly requested that session as an
aesthetic upgrade to the old scrolling move-history log, with real transit-system maps as the
stated inspiration. Revisited today because the user, re-examining it, was no longer sure a
single sequential line still represented what the log was showing: `default.py` (the only
Connect algorithm, since 2026-07-31) is a BIDIRECTIONAL beam search — every round expands the
forward frontier (from the seed) AND the backward frontier (from the target) simultaneously, in
the exact same tick, never one side taking a turn. A single rail reads as one journey; the
reality is two frontiers racing toward each other and meeting in the middle. (The same
underlying mismatch was partially caught once before, in the *wording* only — the 2026-07-31
pass renamed "ply" → "round" specifically because "ply" wrongly implied turn-taking, but never
revisited the rail's single-line *shape* once that was fixed.)

Four concrete directions were mocked up (ASCII previews) and put to the user directly rather
than picked unilaterally:

1. **Round Ledger** — smallest change: keep the single rail exactly as-is, just split the
   existing conic-gradient blended dot into two small side-by-side blue/orange dots per row.
2. **Twin Lines / Interchange** — two parallel rails, one per frontier, merging at an
   interchange marker on the meeting round.
3. **Closing Gap** — one rail, but forward stops grow down from the top while backward stops
   grow up from the bottom, so the visible gap shrinks each round. Flagged as the fiddliest to
   build (no natural way to keep both growing ends in view without knowing the final round
   count in advance).
4. **Radar/wavefront** — abandon the transit metaphor entirely for two expanding pulses meeting
   mid-canvas. Flagged as the biggest rewrite.

**Twin Lines / Interchange was chosen.** Implementation leaned on a fact confirmed during
research, not assumed: `forward_survivors`/`backward_survivors` are always computed and
emitted together in one `Step`, every round, by construction (both loops run inside the same
`while` iteration in `default.py` — there is no way for one side to advance without the other
advancing in that same tick). That guarantee is what makes "one row per round, two columns"
free of any cross-list synchronization problem — the two columns are never out of step because
the data never allows them to be.

Design decisions worth recording:
- **Row taxonomy**, all driven by the EXISTING `stepKind()` classifier (zero changes needed
  there): `origin` and `round` are two-column rows with independent per-side markers;
  `destination` (i.e. `step.path` is set — covers both a normal meeting and the `seed==target`
  instant win) is a two-column row with a bold amber bridge connecting both dots; `exhausted`
  is two-column with hollow red rings and **no bridge at all** — the deliberate absence of a
  bridge is what reads as "these two never met," the same logic the old single-rail design used
  for hollow rings meaning "nothing arrived here."
- **Colors**: origin row's two dots keep each column's own forward/backward hue (blue
  `#2563eb`/orange `#ea580c`, same hexes `sideColor()` already uses for "side" colour-by), just
  larger — a column then reads as one consistent color top-to-bottom until it turns amber at
  the finish. (An earlier draft of this design used green/pink for the origin dots, matching
  `applyStep()`'s fixed seed/target ENDPOINT node colors on the graph canvas — a real existing
  convention, but a different one: that convention exists so an endpoint reads as "a fixed point
  of the search" regardless of coloring mode, which isn't the job the origin row's dots are
  doing here. Kept it simple: one hue per column, no new palette entries.)
- **Counting a round's fwd/bwd numbers from `step.nodes` by depth sign, not from the note
  string.** `default.py`'s note already says `"round N: X fwd + Y bwd"`, but the new
  `roundCounts()` counts `node.depth > 0`/`< 0` directly — the same reasoning `stepKind()`
  already uses for checking `step.path` instead of regexing "reached" out of prose meant for
  humans. Verified `step.nodes` for a round Step is exactly `forward_survivors ∪
  backward_survivors`, so the two approaches produce identical numbers; the structured field
  just can't silently drift from the note if the wording ever changes for cosmetic reasons.
- **A small rail state machine** (`railStarted`/`railEnded` module-level flags in `app.js`) was
  needed because CSS `:last-child` — which the old design leaned on entirely — can't be trusted
  once a row legitimately arrives AFTER the terminal (destination/exhausted) row: the trailing
  "done"/"stopped" status caption. Without it, that caption would grow a stray rail tail past
  where the search actually ended.

**What did NOT change**: `stepKind()`, `log()`'s signature and all six of its existing non-Step
call sites (SSE `status`/`error`, `done`, `stop()`, `source.onerror`, replay's `"replay done"`),
`highlightPath()` and all graph-canvas rendering, the `textContent`-only rule for every label,
`index.html` (the log is still built entirely in JS — zero markup changes), and replay's
architecture (it drives the recorded `Step[]` through the same `applyStep()` → `logStep()` path
on a timer, so it inherited the new rendering with no replay-specific code at all).

Frontend-only (`app.js`, `style.css`), no contract/server/Python change of any kind —
`default.py`/`contracts.py` were read-only references. `node --check` passed; static files
confirmed serving (200s) off the already-running dev server. **Not manually click-tested in a
live browser this session** — no browser automation tool was available (this session runs
without `claude-in-chrome`-equivalent tooling), so a real visual confirmation is still owed, the
same caveat several earlier frontend-only passes have carried.

---

## 2026-08-02 — Center force made log-scale, auto-fit staleness fixed, Arrows toggle removed, endpoint sizing fixed

Same live-measurement approach as the repel/springLength pass earlier today (Playwright +
headless Chromium against the real running server, scratch venv, not the project's own), this
time chasing four separate user reports in one session: "Center force still feels too sensitive,"
"I think auto-fit is broken," "remove the Arrows toggle, it's not needed," and "I'm confused by
the Size-by options."

**1. Center force ("centralGravity") switched from a linear to a log-scale slider.**
Swept the old linear 0-0.5 range on the 81-node `Cat -> Astronomy` graph and measured
`network.getPositions()`'s spread at each step: maxRadius fell from 2253 (cg=0) to 718 (cg=0.01)
— a 68% collapse inside the first 2% of the slider's travel — then only from 259 to 102 (60%)
across the remaining 98% (cg=0.08 to 0.5). That's not "sensitive," that's a slider whose entire
usable range lives in its first few pixels while the rest does almost nothing: the underlying
physics response is exponential in centralGravity, and a linear control on top of an exponential
response is guaranteed to feel broken at one end. Fixed generically rather than by name-checking
"centralGravity": any range input marked `data-log` (plus `data-log-min`/`data-log-max`) now has
its raw 0-100 position remapped through `logValue()`/`rawFromLog()` in `app.js` before use, kept
symmetric with `readDisplay()` (raw -> semantic) and `loadDisplay()` (semantic, from
localStorage -> raw, so the handle lands in the right place on reload) — an attribute-driven
escape hatch, matching this panel's existing "add HTML, not JS" pattern for every other control,
rather than a one-off special case. Re-swept afterward: the same 81-node graph now moves by a
consistent ~17-24% per 10-point step across the *entire* slider, confirmed both numerically and
in a screenshot. Bounds (0.002-0.5) preserve every value the old slider could reach; only the
mapping changed.

**2. Auto-fit view was genuinely stale, not just perceived that way.** `scheduleFit()` was only
ever called from `applyStep()` and the live-run's `fitInterval` — both gated on an in-flight SSE
connection. Confirmed live: dragging any Forces slider (or unchecking then re-checking "Auto-fit
view" itself) *after* a run had finished changed the layout dramatically (measured
`network.getPositions()` radius moving from 461 to 762) while `network.getScale()` never moved
at all — the camera was frozen on whatever it last framed. Root cause: nothing outside a live run
ever called `scheduleFit()` again. Fixed with `settleFit()`, a new function alongside
`scheduleFit()` in `app.js`: it runs `scheduleFit()` on a 300ms interval and keeps doing so until
1.5s pass with no further display change (each call restarts the countdown), because a single
immediate fit would just frame the pre-settle positions and go stale again the moment forceAtlas2
kept moving — the same "physics needs a beat" problem the live-run's `fitInterval` already solved
for the SSE case, just needed once more for the post-run case. `applyDisplay()` now calls
`settleFit()` at the end (guarded on `nodes.length`, and `scheduleFit()` itself still no-ops when
the checkbox is off). Re-verified: the same slider-after-done test now shows `network.getScale()`
moving 0.49 -> 0.30, and the checkbox-recheck test shows 0.48 -> 0.31 — both previously frozen.

**3. "Arrows" toggle removed — arrows are always on now.** A direct, informed user call: the
graph is inherently directed (Wikipedia links are one-way, per contract 2's `Edge` shape), so
there was never a real reason to draw it undirected, and the checkbox was a control that did
nothing anyone would actually want to use. Deleted the `#d-arrows` row from `index.html`; `app.js`
now hardcodes `arrows: { to: { enabled: true, scaleFactor: 0.4 } }` in both the network
constructor and `applyDisplay()`'s `setOptions()` call, rather than reading a `display.arrows`
that no longer exists. Confirmed live: no `#d-arrows` element in the DOM, arrows still render, no
console errors.

**4. Size-by confusion had a real, fixable cause: endpoints scaled through the SAME curve as
everyone else.** Investigating turned up two distinct problems, one fixed and one only
documented:
- **Fixed:** `sizeFor(node)` was being applied to the seed/target nodes too, multiplied by their
  flat 1.6x endpoint bump. That's inconsistent with how *colour* already treats endpoints (`isSeed
  ? "#4ade80" : isTarget ? "#f472b6" : nodeColor(...)` — always a fixed colour, never run through
  the picked scheme) and it actively misleads: in "depth" mode the seed is always depth 0 so it
  always renders biggest, but the target's depth is whatever hop count the search happened to
  finish at — shrinking the target on a *harder* search, backwards from what "this is an endpoint"
  should mean. In "similarity" mode both endpoints share one fixed seed<->target baseline score,
  which is often low precisely when a search is the interesting kind, again shrinking the nodes
  that should stand out. Fixed by giving `isSeed`/`isTarget` (and `n.endpoint` in the
  `applyDisplay()` resize pass) a flat `1.6 * display.nodeSize` regardless of `sizeBy`, mirroring
  colour's existing carve-out exactly. Verified live: Cat/Astronomy's `size` field now reads
  identically (19.2) across `uniform`/`score`/`depth` modes, where before "depth" gave the seed
  26.88 against the target's 22.27 for the exact same search.
- **Documented, not changed:** `default.py` ranks forward-frontier candidates by similarity to
  the TARGET but backward-frontier candidates by similarity to the SEED (confirmed reading
  `default.py`'s ply loop — `forward_scores`/`backward_scores` are two separate
  `similarity_many` calls against two different anchors), and both land in the same `Node.score`
  field. That's an intentional, correct design (each side ranks toward its own actual goal,
  matching decision C's "Connect ranks by similarity to the target" rule read per-direction) —
  but it means "similarity" doesn't have one fixed meaning across the whole picture, which is a
  legitimate source of confusion no UI relabeling fully removes. Added a `title` tooltip to both
  the Size-by and Colour-by selects in `index.html` explaining the split and pointing at "side
  (fwd/bwd)" as the mode that disambiguates it, rather than changing the scoring semantics itself.

All four changes are frontend-only (`index.html`/`app.js`), no contract/server/`config.py` change.
`node --check` passes; no Python touched, so the fast suite is unaffected. Screenshots and raw
probe output live only in the job's scratch tmp dir, same as the earlier pass today — not
committed, transcribed here.

## 2026-08-02 — Forces sliders measured live: repel default raised, spring-length range capped

User reported the Forces sliders (Display panel, browser-only per contract 1) "feel weird" when
tweaked. No `claude-in-chrome` tooling was available this session either, so — rather than guess
— installed Playwright + headless Chromium into a scratch venv (`$CLAUDE_JOB_DIR`, not the
project's own `.venv`; this is a throwaway measurement tool, not a project dependency) and drove
the actual running server: three real Connect runs at three graph sizes (42 nodes stopped after
round 1, 81 nodes — the documented `Cat -> Astronomy` full run — and 26 nodes for `LaMelo Ball ->
Spanish Revolution`), sweeping 7 repel/springLength combinations on each via the real slider
elements (`el.value = x; dispatchEvent(new Event('input'))`, the same path a user's drag fires),
reading `network.getPositions()` for spread/overlap and taking two position snapshots ~1s apart to
measure residual drift (a non-zero px/sec reading after ~2.7s means the physics never damped out
— it's still visibly moving, not settled).

**Findings:**
1. **Node-circle overlap was never the binding constraint** — `overlapFrac` was 0 at every
   combination tested, including the tightest (repel=10, springLength=40). What actually breaks
   at low settings is **label** crowding (unmeasured by circle-overlap, confirmed by eye in a
   screenshot: dozens of text labels stacked into an unreadable blob even though the dots
   themselves never touched).
2. **springLength, not repel, is what destabilizes the layout.** Every combo with
   springLength <= 110 settled to near-zero drift regardless of repel (tested up to 150). Every
   combo with springLength >= 250 showed 20-35 px/sec of continuing drift on the 81-node graph
   — i.e. still visibly rearranging itself long after it should have stopped — and a screenshot
   at the extreme (repel=250, springLength=400) showed the two search hubs collapsed near the
   center with most of the other ~78 nodes flung to a sparse, disorganized ring, instead of the
   clean two-star radial pattern the default settings produce.
3. **The same springLength is safe at one graph size and broken at another.** springLength=250
   drifted only ~8 px/sec on the 42-node graph but ~30 px/sec on the 81-node graph from the same
   search pair — more connected/repelling pairs compound the imbalance between the spring pulling
   nodes to a long rest length and centralGravity (fixed at 0.01) pulling them back in. This is
   the concrete version of "feels weird": a slider position that looked fine on a small run can
   silently stop converging once the same search grows past ~80 nodes, which is an ordinary size
   for this app (documented for `Cat -> Astronomy`), not an edge case.
4. **Higher repel had no downside in any test.** repel=150 with the default springLength=110
   visually looked as good as or better than the shipped default (45) — same stable two-star
   layout, slightly better label spacing — at every graph size tried.

**Changes (frontend-only, `index.html`, no contract/server change — display knobs stay
browser-owned):** default repel raised 45 -> 70 (finding 4). springLength's slider max capped
400 -> 180 (findings 2-3 — nothing above ~200 produced a settled layout once the graph reached
a realistic size, so that region of the range was actively harmful, not just an untested extreme).
centralGravity and springConstant were left untouched — neither was swept, so there's no
measurement backing a change to either yet, only to the two knobs users actually reach for when
a graph "feels wrong" (spacing and edge length).

Screenshots and raw metrics live only in the job's scratch tmp dir (not committed — they're
measurement artifacts, not project files); the numbers above are transcribed from that run.
One measurement artifact worth flagging for anyone re-running this: the very first data point
in the `LaMelo Ball -> Spanish Revolution` sweep read `n=2` — a race in the *probe script*
(it matched a leftover `.entry.destination` element from the previous run's log before the new
run's `logEl.replaceChildren()` had fired), not a real single-node graph. Discard a sweep's first
row if it looks anomalously small; every later row in that run was consistent.

**Not done, flagged for later:** auto-fit (`scheduleFit()`) only re-runs when a new `Step` arrives
during a live run, never when a Forces slider is changed after a run has stopped. Confirmed live:
dragging springLength to its old maximum on a stopped, already-fit graph visibly pushed part of
the graph outside the frozen viewport with no way to re-fit except starting a new run or manually
scroll-zooming. Capping springLength's range (above) makes this far less likely to bite, but
doesn't fix the underlying gap — `applyDisplay()` could call `scheduleFit()` too. Left alone this
pass since it's a separate, smaller bug from what was asked, not a blocker for the slider-range
fix.

## 2026-08-02 — `default.py` perf review: three optimizations, no behavior change

A user-requested review of the only remaining Connect algorithm, looking specifically for
optimizations rather than bugs. Three fixes, all verified non-destructive (77 fast tests green,
was 76; `ruff check` clean; no existing assertion changed).

**1. `EmbeddingCache.similarity_many` was embedding duplicate cache-misses twice
(`embed.py`).** Its miss-detection loop checked `title in self._memory` *before* the batch
write happened, so a title appearing more than once in the input list — a never-before-seen hub
page linked from several of `default.py`'s frontier parents in the same tick, which is common on
real Wikipedia — landed in `misses` once per occurrence. `Embedder.embed_batch` (the actual model
forward pass, the expensive step this whole cache exists to minimize) then computed it more than
once, and each duplicate re-wrote the same disk file. Fixed with `dict.fromkeys(titles)` at the
top of the loop — one line, dedups while preserving order, protects every caller not just
`default.py`. New regression test (`test_similarity_many_dedupes_repeated_titles_before_batching`)
extends `test_embed.py`'s `_FakeEmbedder` with an `embed_batch` that call-counts, proving a
triple-repeated title reaches the model exactly once.

**2. `ThreadPoolExecutor` was created and torn down every tick (`default.py`).** The
`with ThreadPoolExecutor(...) as pool:` sat *inside* the `while` loop, so each of up to
`max_depth` (≤12) ticks spun up and joined a fresh batch of OS threads. Neither frontier ever
exceeds `top_k` after the first tick (both start at 1, then `_rank_and_cap` caps them), so a
single pool sized `2 * params.top_k`, created once before the loop and reused every tick, does
identical work with far less thread churn. This meant widening the `with` block to wrap the
entire `while` loop rather than sit inside it — a bigger diff than the other two fixes, but a
pure reindent; no logic moved.

**3. `_rank_and_cap` full-sorted when it only needed the top K (`default.py`).**
`sorted(...)[:k]` is O(n log n) over every deduped candidate — a ply's candidate count can run
into the low thousands (top_k frontier nodes × ~hundreds of links each) while k is capped at 20
(`TOP_K_BOUNDS`). Swapped for `heapq.nlargest(k, ..., key=...)`, which the stdlib docs describe
as equivalent to `sorted(reverse=True)[:k]` (same tie-breaking), just O(n log k) instead.

**Also, while touching the meeting-detection line already being reindented for fix #2:**
`set(backward_depth)` / `set(forward_depth)` became `backward_depth.keys()` /
`forward_depth.keys()` — dict key-views already support `&` directly, so this was an unnecessary
set allocation every tick. Frontier sizes are small enough (≤240 total) that this one is noise on
its own; only changed because the surrounding lines were already being touched.

Not changed: nothing about ranking, pruning, termination, or the Step contract. This was reviewed
alongside two other sessions running in parallel on frontend work in the same working tree
(`server/static/app.js` showed as modified in `git status` but was never touched by this pass —
left alone and excluded from this commit).

---

## 2026-07-31 — Frontend polish pass: path highlighting, colour-by modes, transit-map log, light theme

Five changes, done in sequence in one session, each requested separately but building on the
last. Recorded together because several of them share reasoning and a later one (the log
redesign) directly reuses a data shape the first one (path highlighting) introduced.

**1. `Step` gained a `path` field, and the graph highlights the winning route.**
`default.py` already computed the full seed → … → target route on success — it was building
the string for the `"reached … via A -> B -> C"` note. That prose was the ONLY place the route
existed; highlighting it in the graph would have meant the frontend regexing a log line
written for humans, which is exactly the kind of fragile coupling contract 2 exists to
prevent (an algorithm's note text is not an API). Fixed at the source instead: `Step` gained
`path: list[str] | None = None` (`graph/contracts.py`), populated on both success paths in
`default.py` (the `seed == target` short-circuit, and the normal meeting-in-the-middle case),
`None` everywhere else including exhaustion. This is additive to contract 2, not a violation
of it — the algorithm still isn't drawing anything, it's exposing data it already had.
`highlightPath()` (`app.js`) amber-borders every node the path names and thickens/recolours
the connecting edges (edge ids are always `${path[i]}->${path[i+1]}`, which holds for both the
forward half and the backward half of a bidirectional route — confirmed by walking through
`_reconstruct`'s edge-direction invariants rather than assumed). An `onPath` flag persists on
each DataSet item so a later display-setting change (`applyDisplay()`'s resize pass) can
re-derive the border instead of silently losing it the next time `nodeColor()` recomputes a
node's fill. 76 tests still green — two existing tests in `test_default.py` gained a
`.path == [...]` assertion; no new test functions needed since the path was already being
computed and exercised.

**2. Five `colour by` modes instead of two, plus a `path` field the code was ALREADY carrying.**
Asked to brainstorm ways to use colour before building anything (kept as a short design
discussion, not implemented until agreed) — landed on five options ranked by cost: side
(cheapest, the sign of `depth` was already there), recency (needs one new client-tracked field,
`tickCounter`/`maxTick`), off-path dimming (a toggle, not a colour scheme), discrete similarity
bands (a bucketing function over the existing score), and semantic clustering (flagged as
the one genuine outlier — needs real embedding vectors shipped past the anchor similarity
score, which is a contract-level change and arguably an Explore-mode question given "finish
Connect before starting Explore," so NOT built). User asked to build all four remaining ones
so they could compare by eye rather than argue over which to pick abstractly — a legitimate
use of "build several options to A/B" that doesn't conflict with "don't add speculative
abstractions," since these are genuinely different, complete features, not variations on a
guess. `recencyColor` reuses `scoreColor`'s exact gradient formula, keyed on tick-fraction
instead of score-fraction, rather than inventing a new colour math for what's structurally
the same idea. "Dim off-path" reads `onPath` (set by `highlightPath()` above) rather than a
second, separately-tracked boolean, so it can't drift out of sync with what's actually
highlighted.

**3. The run log restyled as a transit-map line — and "ply" removed from user-facing text.**
Asked to make the existing scrolling log ("move history") more visually aesthetic, with
transit-system maps as the explicit inspiration. Implemented as pure CSS (a `::after`
pseudo-element per entry draws the rail segment to the NEXT entry — no SVG, no manual
position math, and a new entry automatically grows its own connector the instant an older
entry stops being `:last-child`), with dot shape/colour keyed to a `stepKind(step)`
classifier: green terminus for the run's start, an amber glowing terminus for the destination
(checked via `step.path` from change #1 — the exact payoff of making that data structured
instead of leaving it as prose), a two-tone blue/orange dot for an ordinary tick (reusing
`side` colour-by's palette from change #2), and hollow rings for status chatter and "no route
found." Log order flipped from newest-on-top (`prepend`) to chronological (`append` +
`scrollTop` auto-follow), since a route only reads correctly top-to-bottom in travel order —
a real, deliberate behavior change, not an incidental one.

While explaining what a "ply" was (the word `default.py` and this log used for one tick of
both search directions advancing), a chess/board-game analogy was reached for first. That
was a mistake, called out directly and correctly: chess's "ply" means one PLAYER's move, i.e.
one side goes at a time — precisely the turn-taking model `default.py`'s 2026-07-30 redesign
exists to NOT have (see that entry below: the whole point was removing the "whose turn"
question, because comparing sides to decide who goes next is what made the old design starve
backward). Reaching for that analogy while trying to explain the current design risked
teaching the exact misconception the redesign was fixing. Restarted from Level 1 with no
board-game framing, grounded directly in `default.py`'s loop body (both `ThreadPoolExecutor`
submissions happen in the same block, unordered). Then, on request, renamed "ply" to "round"
everywhere user-visible: the `Step` note text `default.py` emits, the matching CSS class
(`.entry.ply` → `.entry.round`), and the JS classifier's string match. Left "ply" alone in
`default.py`'s own module docstring and internal comments — that prose is explaining the
term's lineage from `bfs.py`'s history for a future code reader, a different audience than
someone watching the app run, and rewriting it would have discarded accurate historical
reasoning to fix a UI word choice.

**4. Light theme.** Every colour in the frontend already lived in `style.css`'s `:root`
custom properties (`--bg`, `--panel`, `--line`, `--text`, `--muted`, `--accent`) from the
original build — flipping the whole UI to light was a single edit to those six values. The
only colours CSS variables couldn't reach were two hardcoded hex strings in `app.js`'s
vis-network constructor options (node label font colour, default edge colour) — vis-network
draws to a `<canvas>`, which is opaque to CSS, so those two got updated by hand to match.

**5. Run form reworded.** Two separately-labelled "From"/"To" fields became one flowing
`Connect ____ and ____` phrase (a `.connect-phrase` flex row in `index.html`). Cost: each
input previously got its accessible name for free by sitting inside its own `<label>`; losing
that wrapper meant adding an explicit `aria-label` to each input instead, so screen readers
still get a name.

Net: 76 fast tests green throughout (unchanged from the pre-session count — this was a
frontend-heavy pass, and the one Python change was additive to an existing contract), `ruff
check` clean, `node --check` clean on every `app.js` edit. None of it was click-verified in a
real browser by the agent that built it (no `claude-in-chrome` tooling this session) — same
open item as the node-click panel and per-node sizing before it.

## 2026-07-31 — `greedy.py`/`astar.py` stripped: `default.py` is now the only Connect algorithm

A direct, informed user call, made in a conversation comparing wikimap against
[jwngr/sdow](https://github.com/jwngr/sdow) (a Six Degrees of Wikipedia tool that precomputes the
entire link graph offline into SQLite and answers with plain BFS over a graph it already fully
has — a fundamentally different, much easier problem than wikimap's live per-request crawl). That
comparison surfaced real frustration with Explore (still unbuilt) and with maintaining three
Connect algorithms whose live-tested results were not actually close: on the hardest cross-domain
pair tested (`LaMelo Ball → Spanish Revolution`, recorded 2026-07-30, below), `greedy` failed
outright (wrong-page dead end at `max_depth`), `astar` never finished (7+ minutes, trapped in a
plateau), and `default` solved it in 3.37s by structurally avoiding both failure modes via
bidirectional search. Keeping three options was not offering a real choice — it was one working
algorithm plus two others that mostly demonstrated their own failure modes, at the cost of every
future fix, every config knob, and every frontend control needing to account for three code paths
instead of one.

**What was removed:** `algorithms/connect/greedy.py`, `algorithms/connect/astar.py`,
`tests/test_greedy.py`, `tests/test_astar.py`. `config.py` lost `MAX_NODES`/`MAX_NODES_BOUNDS`,
`HEURISTIC_WEIGHT`/`HEURISTIC_WEIGHT_BOUNDS`, `HEURISTIC_HOP_SCALE`/`HEURISTIC_HOP_SCALE_BOUNDS` —
all three were astar-only as of the `bfs.py` removal earlier the same day, so nothing reads them
anymore. `RunParams` lost `max_nodes`/`heuristic_weight`/`hop_scale` and their clamps. The server's
`/api/connect` lost the `algorithm=`, `max_nodes=`, `heuristic_weight=`, and `hop_scale=` query
params; `/api/config` stopped publishing `algorithms`/`default_algorithm` and those same knobs'
bounds. The frontend lost the Algorithm `<select>`, the "max nodes"/"weight W"/"hop scale" Search
panel rows, and the `syncAlgorithmUI()` dimming logic that used to grey them out per algorithm —
none of that logic has anything left to dim.

**What was deliberately kept, not simplified further:** `ALGORITHMS` (now `{"default":
DefaultConnect}`) and `_algorithm(name)` in `server/app.py` stay a registry/lookup rather than
being collapsed into a bare `DefaultConnect()` call. `ConnectAlgorithm` (the ABC in
`algorithms/base.py`) stays in place too. Cost is near zero — one dict entry, one indirection —
and it means a genuinely new Connect algorithm (not a resurrection of greedy/astar) can still drop
in later without restructuring the server or the frontend's knob-rendering code.

**What this costs:** the "watch breadth-first vs. greedy vs. balanced A* vs. bidirectional beam
search" comparison — previously the point of the weight-`W` slider (`W=0` behaves breadth-first,
`W` large behaves greedy, astar in between) — is gone; the app now demonstrates one search
strategy, not a spectrum. If a teaching/demo use case for that comparison resurfaces later, it
should come back explicitly as a deliberate "watch this fail" contrast, not as a default the user
has to pick between.

76 fast tests green (was recorded as 122 pre-`bfs.py`-removal, down through both removals the same
day), `ruff check` clean. `TestAlgorithmSelection` in `test_server.py` was replaced by a smaller
`TestAlgorithmRegistry` pinning what's left of the registry shape (one entry, shared caches across
lookups) rather than multi-algorithm selection, since that behavior no longer exists to test.

## 2026-07-31 — `connect/bfs.py` removed: too slow to be worth the ground-truth guarantee

A direct, informed user call ("bfs takes too long, lets operate it as beam search" → after being
shown what that would actually cost → "just delete it lowkey its so fucking slow notw orth"),
made after two explicit warnings about what it gives up. Recorded in detail because it's a real
architectural reversal, not a routine deletion.

**What was asked first, and why it was redirected.** The request was to turn `bfs.py` into a beam
search for speed. Flagged before writing any code: `bfs.py`'s entire reason for existing was being
*uncapped and unranked* — the ground-truth check on whether greedy/A*/default's claimed shortest
paths actually were shortest (a cosine-capped search "can only ever find routes cosine was willing
to consider," per its own docstring). Capping it into a beam search would remove that guarantee
from the whole codebase, with nothing left to replace it. Also surfaced: `default.py` **already
is** a bidirectional beam search — built 2026-07-30 by taking `bfs.py`'s ply-synchronized shape and
adding decision C's top-K cap back on. Reading `default.py` in full confirmed "bfs as beam search"
would land almost line-for-line on what `default.py` already does (same threaded per-ply fetch,
same batched embedding, same three-source meeting detection, same `_reconstruct`). Asked again,
explicitly, whether to still convert `bfs.py` in place given that near-duplication. The answer was
to skip the beam-search conversion entirely and just delete `bfs.py`.

**What actually got removed:** `algorithms/connect/bfs.py` and `tests/test_bfs.py`, plus its entry
in `algorithms/connect/__init__.py`'s `ALGORITHMS` registry (the frontend's algorithm picker is
config-driven, so it drops out of the dropdown automatically — no frontend registry change
needed). Three algorithms remain: greedy, astar, default.

**Consequence, stated plainly because it's easy to lose track of later:** there is currently no
algorithm in this codebase that can verify another one's shortest-path claim. `astar.py` and
`default.py`'s docstrings both still document their own known non-optimality (inadmissible cosine
heuristic, prune-before-explore respectively) — those limitations were always true, but until
today there was a way to check them against ground truth on any given run. There no longer is.
If a future session wants that guarantee back, it needs a new, undirected, unranked search built
from scratch — not a revival of `bfs.py`'s beam-search-shaped middle ground, since that middle
ground is `default.py`.

**Fallout handled in the same pass, not left dangling:** `bfs.py` was one of two readers of
`config.MAX_NODES` (the other, `astar.py`, was reinstated as a reader the very same day in an
unrelated backend-review pass — see the entry below this one). `max_nodes` stays on `RunParams`;
only its ownership comment changed (astar-only now). `BACKLINK_LIMIT` survives untouched — 
`default.py` reads it too for its own backward half. Every docstring/comment across
`algorithms/base.py`, `greedy.py`, `astar.py`, `default.py`, `config.py`, `app.js`, `index.html`,
`README.md`, and the test suite that named `bfs.py` as a live component was swept and corrected in
the same pass (either removed or converted to past tense), rather than left to rot as a dangling
reference to a file that no longer exists. 120 fast tests green (was 123, -3 for `test_bfs.py`'s
removal), `ruff check` clean.

---

## 2026-07-31 — live-tested: `De'Aaron Fox → Dwight Howard` "1 hop" was real, not a bug

Reported as a suspected bug: `default` found `DeAaron Fox -> Dwight Howard` in 1 hop, and the
user couldn't find any such connection reading the actual `De'Aaron Fox` article. Investigated
by pulling the same link list the app's cache actually used (`LinkCache.get_links("DeAaron
Fox")` — 310 real ns0 links, `Dwight Howard` genuinely among them) and then the parsed article
HTML to find *where*: both players' pages transclude the **"Jordan Brand Classic All-American
Game — Boys' MVPs"** navbox at the very bottom of the page (a collapsed year-by-year award list),
and each was that game's MVP in a different year. Real hyperlink, just buried in a navbox rather
than the prose — invisible on a normal read-through of the article, easy to mistake for the
algorithm inventing a connection.

Not a bug, and nothing was changed. Recorded because it's the same failure-shaped-like-a-feature
category as the `TIME`/`Time` magazine finding in the 2026-07-30 hard-pairs entry below: the
"real Wikipedia link graph, not generated associations" locked decision means Connect will
surface *any* true hyperlink, including trivia-navbox links a human skimming the page would never
notice. Worth knowing as a standing category of "correct but unsatisfying" result before
mistaking the next one for a fetch/cache bug.

---

## 2026-07-31 — backend review: `embed.py` cache-anchor gap, `greedy.py` seed==target silence

A full read-through of `wiki/`, `embed.py`, `graph/`, `algorithms/`, and `server/app.py`, prompted
by "review the backend." Two confirmed bugs, fixed; one confirmed risk, documented but not yet
fixed (capping proposals pending a decision).

**1. `EmbeddingCache.DEFAULT_DATA_DIR` was still a bare relative path.** `Path("data/embeddings")`
resolves against the process's current working directory, not the project root — precisely the
bug the 2026-07-27 review pass fixed for `wiki/cache.py`'s `LinkCache` (`Path(__file__).resolve()
.parents[3]`, see that entry above). `embed.py` never got the equivalent fix. Practical
consequence: launch `uvicorn` from any directory but the repo root and the entire embedding cache
(the model-forward-pass cost, which is the whole point of caching it — "embedding ~300 links per
node is the dominant cost, so pay it once per page") goes cold silently, with no error, just a
slow rebuild and a stray `data/embeddings` folder wherever the process was started. It slipped
through the 2026-07-27 pass's own blind spot: "every `test_embed.py` test already passed
`data_dir=tmp_path` explicitly" — true then and still true now, so no test ever exercised the
real default. Fixed the same way as `LinkCache` (`Path(__file__).resolve().parents[2]` — one
level shallower, since `embed.py` lives directly in `wikimap/`, not a subpackage). New regression
test computes the expected path independently from the test file's own location rather than
importing `embed`'s constant, so it can't pass by sharing the bug it's checking for.

**2. `GreedyConnect.run` had no `seed == target` special case.** `astar.py`, `default.py`, and
`bfs.py` all check this up front and emit an explicit `"reached ... in 0 hops"` Step; greedy
fell through to its generic start Step and then simply returned, since `while current != target`
is immediately false. Not a crash, just silence — the frontend gets a start frame and a `done`
frame with nothing in between announcing the run actually succeeded. Fixed to match the other
three. The one existing test that asserted the old silent behavior
(`test_seed_equal_target_yields_only_the_start`) was rewritten, not preserved — this is a
deliberate behavior change closing an inconsistency, not a regression the old test should keep
pinning. Renamed to match astar's test of the same purpose
(`test_seed_equal_to_target_terminates_immediately`).

**3. Flagged, not fixed: `astar.py`'s worst-case bound doesn't hold.** The 2026-07-30 entry below
("`max_nodes` removed from greedy/astar/default") reasoned that `MAX_DEPTH * TOP_K` (≤ 240)
bounds all three algorithms' worst case, since each caps a node's own fan-out to `TOP_K`. That
holds for `greedy` (walks exactly one path, one expansion per depth level) and `default` (pools
and caps to `TOP_K` *per ply, per side*, regardless of how many parent nodes contributed
candidates). It does NOT hold for `astar`: its `while frontier:` loop keeps popping and expanding
every distinct node discovered below `max_depth`, with no ply structure and no total cap — so the
real worst case is closer to `TOP_K` raised to the depth, not multiplied by it. This is the
likely actual explanation for the `astar` 7-plus-minute plateau already recorded below (stuck
exhausting dozens of similarly-scored "Spanish [sports league]" pages on `LaMelo Ball → Spanish
Revolution`) — filed at the time as a distinct "breadth without progress" failure mode, but more
likely fallout from removing astar's only backstop the same day, based on a bound that doesn't
actually apply to it. Two capping approaches were proposed (see the session's conversation, not
reproduced here) — bring back a form of `max_nodes` scoped to `astar` alone, or add an
expansion-count cap distinct from the node-count one `bfs.py` uses — but neither is implemented;
this needs a decision, not just a fix, since either changes what "the search gave up" means to a
user watching it run.

123 fast tests green (was 122, +1: the new `embed.py` cache-anchor regression test).
`ruff check` clean. No existing assertion changed except the one `greedy.py` test whose old
assertion described the exact behavior being intentionally fixed.

---

## 2026-07-31 — Enter/Run now autocorrects seed/target to a real title

Closes a gap a code review surfaced the same day: `greedy.py`/`default.py` compare `seed`/
`target` to real Wikipedia link titles with exact string equality (`current != target`,
`forward_depth[link] = depth`, etc.), but the frontend was sending whatever the user literally
typed. Autocomplete (2026-07-30) already fixes this when a user clicks a suggestion — the click
hands back a real, correctly-cased title — but nothing stopped someone typing `astronomy` and
hitting Enter, walking straight through `Astronomy` without the algorithm ever recognizing it,
and getting a misleading "stopped: hit cap" instead of a clear typo error.

Fixed in `app.js`'s `submit` handler, not in the algorithms: `resolveTitle(query)` calls the
same `/api/suggest` endpoint autocomplete already uses and takes the top hit, falling back to
the original text if the search comes back empty (offline, gibberish query, etc.) so a failed
lookup degrades to today's behavior rather than blanking the field. Both `seed` and `target`
resolve concurrently (`Promise.all`) before the run starts, and the corrected values are written
back into the input boxes so the user can see what's actually running. This covers Enter AND
clicking Run for free — both fire the same `submit` event — so no separate keydown handling was
needed.

Deliberately not fixed by loosening the algorithms' comparison (e.g. case-insensitive or
title-normalizing equality checks in two different search modules): `/api/suggest` already
exists for exactly the job of turning arbitrary user text into a real title, so reusing it here
is one small frontend addition instead of a second, redundant fix duplicated inside `greedy.py`
and `default.py`. The submit handler is now `async` (previously synchronous) to `await` the
resolution before opening the `EventSource`; Run is disabled immediately, before that round
trip, so a second Enter/click during the brief resolve window can't fire a double run. No Python
touched, 122 tests unaffected. Not yet manually verified in a browser — same caveat as the
node-click panel and node-size-by-score work before it.

---

## 2026-07-30 — live-tested algo speed/efficiency across all four algorithms on hard pairs

Requested directly: a head-to-head comparison, using genuinely hard cross-domain pairs rather
than the easy ones tested earlier the same day ("those are easy links... try shit like LaMelo
Ball to the Spanish Revolution"). No code changed — purely observational, using the timing
feature and `/api/suggest` autocomplete both built earlier this same day.

**`The Simpsons → Satire`** was trivial (direct 1-hop link) for all four — but still surfaced a
real number worth keeping: `The Simpsons` has 2098 raw outbound links, wider even than
`Friends`' 896 from the previous session's `bfs` failure. `bfs` only survived here because the
meeting was found inside the very first (uncapped) node's own fan-out, before the node cap ever
got a chance to fire — a coincidence of this specific pair, not evidence the underlying issue is
fixed.

**`Interstellar (film) → Time`** (cold cache) split the algorithms for the first time: `greedy`
found a 2-hop route through `TIME` — Time Magazine's page, not the target concept — because
cosine scored the two titles as effectively identical (1.000). `default` found the semantically
correct `Interstellar (film) → Theory of relativity → Time` in the same 2 hops, because its
backward half started from the real target and never considered the magazine at all. This is the
title-only-embedding weakness `wikimap-connect-reliability-research` (memory) flagged as
recommendation #5, now demonstrated live rather than theorized.

**`LaMelo Ball → Spanish Revolution`** — the real stress test:
- `greedy`: failed, hit `max_depth`, dead-ended at `French Revolution` (0.721 similarity, wrong
  page) after drifting through unrelated LA-local-news pages.
- `astar`: manually stopped after 7+ minutes without finishing. Trapped in a wide plateau of
  dozens of "Spanish [sports league]" pages that all scored similarly on the shared word
  "Spanish," and had to exhaust nearly all of them (by `f`-order) before reaching the genuinely
  close branches (`Spanish monarchy`, `Spanish Civil War`, h≈1.1). A different failure mode from
  greedy's drift — breadth without progress, not a wrong commitment.
- `default`: solved it in 3.37s, 6 hops, via `Spain`/`Spanish Revolution of 1936`. Its
  bidirectional design structurally sidesteps astar's plateau — the backward half doesn't need
  one continuously-low-h path all the way through, only a meeting point, and it found one via a
  completely different neighborhood than forward's.
- `bfs`: hit the node cap at 1031 nodes in 4.43s — not from the seed this time, but from `2017
  NBA draft` (a *one-hop* neighbor) alone contributing 624 new nodes. **Sharper than the earlier
  `Friends` finding**: the hub-fan-out problem isn't only a seed/target property — any node
  discovered mid-search can be a hub. A future title-pattern pre-filter (recommendation #1 in
  the reliability research) needs to apply everywhere `get_links`/`get_backlinks` is called, not
  just at a run's two endpoints.

Also the third independent sighting of a disambiguation page counted as a real hop
(`Spanish Revolution (disambiguation)` in `default`'s path here, after `Power (disambiguation)`
in an earlier session) — enough repeat evidence to treat recommendation #3 (disambiguation
detection via MediaWiki's `pageprops`) as the next highest-value fix from that research, not
just a hypothesis. See memory `wikimap-connect-reliability-research` for the full ranked list
these findings feed into.

---

## 2026-07-30 — frontend: per-step and total-run timing benchmarks

Requested directly: visible timing for each Step and for a whole run, partly to make the perf
work below (concurrent fetch + batched embedding) demonstrable rather than just asserted.
Built entirely in `app.js` — no backend change, no `Step` contract change. Deliberately: "how
long did this tick take to reach the screen" is a rendering-side question, the same family
contract 2 already keeps off algorithms (node size, colour). Measured off SSE arrival
timestamps via `performance.now()` — monotonic and sub-millisecond, unlike `Date.now()`, which
can jump if the system clock adjusts mid-run.

Each Step's log line now reads `[+123ms · 4.56s total] <note>` — delta since the previous
Step, elapsed since the request went out. Run termination (the `done` SSE event, a manual Stop
click, or a dropped connection) logs the run's total. `runStartTime`/`lastStepTime` are
module-level state, cleared inside `stop()` — the one function every termination path already
funnels through — rather than separately at each of the three call sites, so there's a single
place that owns "a run is/isn't currently being timed."

**Replay reuses the real timings, not fabricated ones.** Replay already re-applies the
recorded Step stream on a fixed 600ms animation clock (see the node-detail-panel era's replay
feature). Timing it off THAT clock would show a distorted benchmark — every step reading
~600ms apart regardless of what actually happened. Instead `recordedTimings` is a second array
parallel to the existing `recorded` Step array, capturing each Step's real
`{deltaMs, elapsedMs}` as it arrived live; replay looks those up by index instead of
recomputing off its own clock. Frontend-only, 122 tests unaffected, `ruff check` clean (no
Python touched).

## 2026-07-30 — `default.py` per-tick cost cut: concurrent fetch (threads) + batched embedding

Asked directly, after walking through where each Connect algorithm's time actually goes:
is `default.py`'s per-tick fetch cost worth cutting? Two genuinely separate costs had been
bundled under "fetch cost" and got two separate fixes.

**Fetch (network wait).** `default.py`'s ply loop fetched each frontier node's links/backlinks
one at a time — a plain Python `for` loop, one blocking `LinkCache.get_links`/`get_backlinks`
call after another. For a full ply (up to `top_k=20` nodes per side) that's up to 20 sequential
round trips per side before a single candidate can even be scored. Fixed with a
`ThreadPoolExecutor`: every frontier node's fetch is submitted at once and awaited together.
This does NOT reduce fetch count — decision C still requires seeing every candidate link
before ranking it, so nothing is skipped — it cuts wall-clock wait, because a thread blocked
on socket I/O releases the GIL, so Python threads genuinely overlap while waiting even though
only one can run bytecode at a time. Confirmed safe without locking: forward and backward
frontier parents are always disjoint mid-run (a shared title would already have triggered a
same-tick meeting and ended the run — see the redesign entry below), so no two threads ever
touch the same `LinkCache` entry concurrently. This is the same lever `bfs.py`'s own HISTORY
entry (2026-07-29, node-cap overshoot) already flagged as real-but-unbuilt for its own ply
cost; not yet ported there.

**Embedding (model compute).** This one was a genuinely old TODO — the original MVP note far
below in this file already said "Embedding is one title at a time... Batching via
`model.encode(list)` is the obvious win," and it sat unbuilt the whole time since. New
`Embedder.embed_batch(titles)` wraps `model.encode()` on a list instead of a single string
(the model batches internally — one vectorized forward pass instead of N small ones), and
`EmbeddingCache.similarity_many(titles, anchor)` collects a whole ply's cache-miss titles and
sends them through one `embed_batch` call, falling back to the existing memory/disk layers for
anything already cached. `default.py`'s ply loop is the only caller so far — greedy/astar
still embed one candidate at a time, since neither builds a whole-ply candidate list the way
default.py's ply-synchronized shape does; porting the same batching to them is a smaller,
separate change if it's worth doing later.

Neither fix touches ranking, pruning, or termination — same algorithm, same output, just
faster. 122 tests green (`_FakeEmbedCache` in `test_default.py` gained `similarity_many`, no
existing assertion changed), `ruff check` clean.

## 2026-07-30 — `connect/default.py` redesigned: turn-based heap → ply-synchronized beam search

Live-tested the morning's freshly-shipped `default.py` against a real search, "israel" ->
"john f kennedy," through the browser. The graph showed forward fanning out normally (`israel`,
then `Bill Clinton`) while the target node sat completely disconnected — zero edges, zero backward
expansions in the log, not even an empty one. Traced by hand: both sides' frontiers start with an
identical `f` value on tick 1 (both seeded from the same seed-target similarity), and the
turn-selection rule (`top_f_forward <= top_f_backward`) resolves ties in forward's favor. Backward's
frontier value is set once, at the start, and never recalculated until backward is actually picked
— so if forward keeps discovering candidates that score even moderately well (both "Israel" and
"Bill Clinton" are large, well-connected hub pages), forward can keep winning that comparison
indefinitely. This is the exact bug class `bfs.py`'s own HISTORY entries already fought twice
(comparing raw queue length, then whole-frontier size — both proven wrong live) before landing on
"the only safe comparison is depth LEVEL itself." The old `default.py` compared `f`, which is worse
than either of `bfs.py`'s two already-rejected attempts, since `f` bakes in a heuristic guess and
isn't even monotonic the way queue length or frontier size at least were.

**The user's proposal, and why it's a stronger fix than patching the comparison:** rather than
pick a side each tick, run both from seed and target simultaneously — batch every candidate link
from both sides' current frontier together, score them, and prune to top-K as the search moves
inward. Implemented as a ply-synchronized beam search, directly borrowing `bfs.py`'s "advance one
full wavefront per tick" shape and layering decision C's top-K cosine cap back on top (unlike
`bfs.py`'s deliberately uncapped exception). There is no turn-selection left to get wrong, because
there is no turn — every tick expands both sides' entire current frontier, unconditionally.

Design decisions made while translating "batch and prune" into code, each a real fork with a
reasoned answer:

1. **Pruning is per-side, not pooled.** Forward's candidates are ranked by similarity to the
   target; backward's by similarity to the seed (decision C, unchanged) — two different questions
   on two different anchors, not one shared scale. Pooling into a single top-K cut would let
   whichever side's neighbourhood scores higher *this tick* crowd out the other's slots — the same
   starvation shape, just relocated from turn-selection into the prune step instead of eliminated.
   Verified with a test where forward's candidates score 0.9 and backward's score 0.01: backward
   still keeps its own top-K regardless.
2. **Reopening (`astar.py`'s fix, inherited by the original `default.py`) is gone — and it's a
   genuine simplification, not a lost feature, not a regression.** Reopening existed to handle a
   route that looked cheap enough to close a page early, only for a genuinely cheaper route to
   surface later — a scenario that specifically needed a persistent priority queue where "later"
   could mean "a lower-cost path processed after a higher-cost one already closed that page." Here,
   depth increases by exactly one, together, on both sides, every tick. A link is only ever
   first-seen in the ply where some survivor of the current frontier reaches it, and that ply
   number can only go up — first discovery already IS the best depth this design's pruning can
   produce. Nothing to reopen.
3. **`heuristic_weight` (W) and `hop_scale` are no longer read.** They existed to make
   `f = g + W*h` comparable *across* a frontier holding candidates at different depths — the
   turn-selection heap that no longer exists. Every candidate considered in one tick now shares the
   same depth, so blending in `g` compares a constant against itself; pure similarity ranking is
   already the right order. `astar.py` still needs both; this file doesn't, same as `greedy.py`
   never reading `config` once params landed.
4. **A link discovered by more than one frontier node in the same tick is a new wrinkle** that
   never existed when only one node was expanded per tick. Resolved by keeping each link's
   best-scoring parent edge and discarding the rest — deterministic (first-seen wins on an exact
   tie), tested directly.
5. **Meeting detection now checks three sources, not two:** a side's new find against the other
   side's pre-existing depths (as before), in both directions, PLUS a side's new find against the
   *other side's own new finds from the same tick* — since both sides genuinely move at once now, a
   page independently discovered by both sides in one tick is a real meeting, not something to
   defer a tick to notice.
6. **Termination simplified:** stop at the first ply where any meeting is found (reporting the
   cheapest if more than one turned up), replacing the old `best_total`/keep-hunting-across-many-
   ticks logic that existed specifically to guard against a naive "stop at first contact" bug in a
   one-node-at-a-time model. That guard matters less once a whole ply's candidates are already
   gathered and compared together before any decision is made — the same simplification `bfs.py`
   already makes for the identical reason.

**Collided, briefly, with the other concurrent session.** While this rewrite was in progress, the
other terminal was independently removing `max_nodes` from `greedy.py`/`astar.py` (see the entry
below) — and, discovered mid-edit here, had *also* already applied the same removal to this
brand-new, still-untracked `default.py` and its test file before this session got to it. Both
sessions converged on the identical decision (this design is bounded by `2 * max_depth * top_k`
without a separate cap, same reasoning as the other three algorithms), so nothing broke — 11/11
`test_default.py` tests still green afterward — but it was pure luck, not coordination: two agents
editing the same untracked file with no lock between them could just as easily have silently
overwritten real work with no git history to recover it from. Flagged to the user live; the other
terminal was paused before further work continued here.

Not manually re-verified in a browser against the original "israel" -> "john f kennedy" case this
session (that specific search may still fail regardless — see Bug 2 in the same live-testing pass,
the seed/target strings aren't resolved against real Wikipedia titles before searching, a separate,
already-flagged issue). What IS proven: the structural starvation bug is gone by construction, not
patched — there is no code path left in this file that can pick one side over the other.

104 fast tests before this pass (post max_nodes-removal baseline), 114 after (test_default.py grew
from 13 to 11 net — two max_nodes tests removed matching the codebase-wide decision, plus new tests
for no-starvation, per-side-pruning, and same-tick duplicate/meeting detection), `ruff check` clean.

---

## 2026-07-30 — seed/target autocomplete: `/api/suggest` + a dropdown under FROM/TO

The UI-backlog item flagged back on 2026-07-29 (Six Degrees of Wikipedia's live
autocomplete vs. wikimap's plain-text `#seed`/`#target`, where a typo silently
dead-ends a run) and reaffirmed after today's title-reliability research session —
built now rather than deferred further, since it directly sidesteps two of that
research's failure modes (mistyped/nonexistent titles, landing on a disambiguation
page) by only ever letting the user pick a real, already-resolved title in the
first place.

`WikiClient.search_titles(query, limit=SUGGEST_LIMIT)` (`wiki/client.py`) is a new
third method that bypasses `wikipedia-api`, alongside `get_backlinks` — same
reason: the library has no search support at all. Uses `list=prefixsearch` directly,
`psnamespace=0` server-side (the same ns0 rule as `get_links`/`get_backlinks`), and
`pslimit` server-side rather than slicing a larger result after the fact. New
`config.SUGGEST_LIMIT = 8`, deliberately NOT a `RunParams` field or published via
`/api/config`'s bounds — it never reaches an algorithm, so it isn't a contract-1
search knob, just a plain constant `WikiClient` reads directly (same category as
`BACKLINK_LIMIT`).

`GET /api/suggest?q=` (`server/app.py`) returns a plain JSON list of titles,
sharing `/api/page`'s lazy `_wiki_client()` singleton rather than building its own.

Frontend: `#seed`/`#target` are each wrapped in a `.input-wrap` (new, `position:
relative`, sized to the input alone so the dropdown aligns under it rather than
under the whole label, which also holds the "From"/"To" text) holding a `<ul
class="suggestions">`, scrollable via `max-height` + `overflow-y: auto` — the
"scroll dropdown" the user asked for. `setupAutocomplete()` in `app.js` debounces
input (200ms, 2-char minimum), fetches `/api/suggest`, and renders results with
`textContent` (never `innerHTML` — same rule as `log()`/the node panel: real
Wikipedia titles land in the DOM verbatim). A stale-response guard (compare the
input's current value against the query a given fetch was issued for) mirrors the
node-click panel's `openNodeTitle` pattern, just keyed on query text instead of a
node id. List items use `mousedown` + `preventDefault()` rather than `click`, since
`blur` (which hides the list) fires before `click` and would otherwise swallow the
selection. Escape and blur both close it. No keyboard arrow-navigation — out of
scope for this pass; Enter still submits the form as before, unchanged.

Verified live in Chrome against real Wikipedia: typing "Batm" in FROM surfaced
"Batman", "Batman Begins", etc. in a scrolling list; typing "Quan" in TO surfaced
"Quantum mechanics" among others; picking a suggestion filled the field and closed
the dropdown without triggering a submit; running `Batman -> Quantum mechanics`
afterward worked end-to-end. Zero console errors throughout.

8 new tests (`TestSearchTitles` in `test_wiki_client.py`, mirroring `TestBacklinks`'
mocked-`requests.get` pattern; `TestSuggestEndpoint` in `test_server.py`, extending
the existing `_FakeWikiClient`/`fake_wiki_client` fixture with `search_titles`).
122 tests green (was 114), `ruff check` clean.

---

## 2026-07-30 — `max_nodes` removed from greedy/astar/default; bfs-only now

Prompted by a live-testing session running TV/movie titles as seeds against
abstract-concept targets across all four algorithms. `Friends -> Loneliness` on `bfs`
never got past depth 1: the seed page alone has ~896 outbound links (episode lists,
cast, "in popular culture"), and since `bfs` has no top-K cap by design, that single
node's fan-out blew straight through `max_nodes=500` to 898 nodes before the
between-nodes check ever fired.

Checking whether `max_nodes` was pulling real weight on the other three algorithms
showed it wasn't. `greedy`/`astar`/`default` all cap every node's fan-out to
`TOP_K=20` already (decision C), so their own worst case is already bounded by
`MAX_DEPTH * TOP_K` (≤ 12 × 20 = 240, comfortably under the 500 default) with or
without `max_nodes`. `max_depth` was already doing the limiting; `max_nodes` was dead
weight riding along.

Removed the `params.max_nodes` read (and the now-pointless `seen` bookkeeping that
existed only to feed it) from `greedy.py`, `astar.py`, and `default.py`. `bfs.py` is
untouched — it's the one algorithm with no per-node cap, and the one that actually
needs the backstop. `config.py`'s `MAX_NODES`/`MAX_NODES_BOUNDS`/`RunParams.max_nodes`
all stay (still read by `bfs`, still served via `/api/config`) — comments updated to
say bfs-only instead of universal. Frontend: the "max nodes" control now dims for
every algorithm except `bfs` (new `.nodecap` class, toggled in `syncAlgorithmUI()`),
mirroring how weight W/hop scale already dim for greedy/bfs.

**Does NOT fix the `Friends`/`bfs` case itself** — `bfs` still hits the cap on that
run, by design; this only removes a cap that wasn't protecting anything on the other
three. Separately commissioned a research pass into approaches for TV/movie-title
fan-out and abstract-concept-target runs generally (disambiguation handling, redirect
resolution, filtering low-signal links, etc.) — see its findings when they land, and
whatever gets implemented from them, for the actual fix to that class of run.

Five tests removed (two node-cap tests each from `test_astar.py`/`test_default.py`,
one from `test_greedy.py`) — they tested behavior that's gone by design, not a
regression. 114 tests green, `ruff check` clean.

---

## 2026-07-30 — `connect/default.py`: bidirectional weighted A*, now `DEFAULT_ALGORITHM`

Fourth Connect algorithm, and the first written to be a deliberate combination of the
other three: `astar.py`'s top-K-ranked, weighted `f = g + W*h` search (decision C's
branching cap still applies, unlike `bfs.py`'s uncapped exception), run from both
`seed` and `target` simultaneously like `bfs.py`. Forward ranks candidates by
similarity to the target (exactly `astar.py`'s heuristic); backward ranks by
similarity to the seed, its own natural anchor. Registered in `ALGORITHMS` as
`"default"` and now `DEFAULT_ALGORITHM` — the app's out-of-the-box choice — because
for someone who just wants a good route without picking an algorithm, it's usually
cheaper than one-directional A* (half the effective depth each side has to cover) and
far less visually explosive than `bfs` (top-K keeps every tick bounded, unlike `bfs`'s
uncapped ply). NOT provably optimal, doubly so: everything `astar.py`'s docstring says
about cosine being inadmissible applies on both sides here, and naive bidirectional
search has its own separate correctness trap (stopping at the first meeting found is
not guaranteed cheapest, even for an admissible heuristic — `bfs.py`'s docstring
describes the unweighted version of the same trap). Mitigated the standard way: track
the cheapest meeting found (`best_total`) and keep expanding whichever frontier could
still beat it, stopping only once neither can — a practical improvement, not a proof.
Also carries over, independently per side: `astar.py`'s reopening fix (a strictly
cheaper rediscovery of an already-expanded page un-closes it) and `bfs.py`'s
check-the-node-cap-after-not-before-expansion fix (astar.py's before-expansion
placement is only safe there because its meeting check happens at pop time, fully
resolved before the cap gate; this file's meeting check happens mid-relaxation, so a
before-expansion gate could trip on a later tick and block the very expansion that
would have reported an already-cheaper meeting).

**Design decision, discussed with the user before finishing this file: candidate
ranking stays anchored to the fixed `seed`/`target` ("front-to-end"), not switched to
chasing the opposing search's current frontier node ("front-to-front").** Front-to-front
is the more powerful idea on paper, but naive versions (comparing to a single "current"
node on the other side) are known-unreliable in practice — that one node is a poor
proxy for the actual eventual meeting point, especially early in a run when one side
has barely started, and it costs the same one extra similarity lookup either way, so
there's no efficiency case for it. The mechanism that actually makes the two searches
*meet* was already separate from ranking regardless — the structural check (a page's
cost becoming known on both sides) plus `best_total` pruning — so this decision only
concerns which page a side's own candidates get compared against, not how meetings are
detected.

**Found and fixed before this file was considered done: a broken test, not an
algorithm bug.** `test_backward_search_contributes_a_shorter_meeting` asserted backward
must expand at least one node, using a graph where forward's own links already form a
complete route to the target. Traced by hand: both frontiers start with an identical
f-value on tick 1 (both seeded from the same `seed`-`target` similarity), and the
tie-break rule (`top_f_forward <= top_f_backward`) favors forward on ties — so forward
goes first, completes the route in 2 hops, and the resulting `best_total` beats
backward's still-untouched initial frontier value before backward ever gets a turn.
The reported path was correct; the test's premise (that backward's contribution was
necessary) simply didn't hold for that graph. Fixed by reworking the scenario so
forward's own link graph is a dead end and the route only closes through backward's
independently-discovered backlink.

⚠️ **Noted, not fixed — same pattern as the deferred `LinkCache._lookup` atomic-write
item.** The tie-break rule above deterministically favors forward on exact ties,
including on every run's very first tick (both sides start from the same similarity
value, by construction). This doesn't threaten correctness (`best_total` pruning still
guards against a wrong early stop, proven by `TestDoesNotStopAtTheFirstMeeting`), but
it could starve backward search in symmetric or near-symmetric graphs, undercutting
the "half the effective depth each side has to cover" efficiency case this file's
docstring makes for itself. Not fixed now — flagged so a future session doesn't have
to rediscover it before deciding whether it's worth alternating on ties.

This file had been added to the working tree by a concurrent session without STATUS/
HISTORY entries or a passing test suite; this entry, the STATUS update, and the test
fix close that gap. 119 fast tests green (was 118 with the one failure), `ruff check`
clean, no other assertion changed.

## 2026-07-29 — auto-fit fix: one `fit()` per Step chases a moving target and loses

User-reported live regression right after auto-fit shipped: it "isn't doing shit" during a real
Connect run. Two things were wrong.

**The real bug.** `scheduleFit()` only fired from inside `applyStep()` — once per Step. A Step
marks the instant a node/edge is *added*, but forceAtlas2 physics keeps pushing the whole layout
outward for a while afterward as it settles, and Steps arrive with real network latency between
them (a cold run's Wikipedia fetches are seconds apart — see the roadmap-step-5 entry below).
That gap is plenty of time for physics to drift the graph back out past whatever `scheduleFit()`
last framed, and nothing re-fit the camera again until the *next* Step arrived — by which point
physics had already been quietly overflowing the frame for seconds. One fit-per-arrival chases a
moving target and loses. Fixed with a `setInterval(scheduleFit, 400)` that runs for the lifetime
of a live run (started alongside the `EventSource` in the submit handler, cleared inside `stop()`),
so the camera tracks the settling itself, not just the moment a node lands. `scheduleFit()` was
already cheap to over-call — `fitPending` + `requestAnimationFrame` no-ops it when there's nothing
to do — so polling it costs nothing. A trailing `setTimeout(scheduleFit, 400)` after the `done`
handler's `stop()` catches whatever the layout does in the last fraction of a second once the
interval that was tracking it gets cleared.

**A smaller bug caught alongside it.** `network.fit()`'s animation option is `easingFunction`, not
`easing` — I'd written the latter. vis-network drops unrecognised option keys silently rather than
erroring, so this cost nothing *visible* on its own (the fit still ran, just without the intended
custom easing), but it was still wrong and is fixed now.

Frontend-only, no Python touched, 106 tests still green (this file has no JS test coverage — see
the `sizeFor`/`d-sizeBy` entry below for why). Confirmed via `curl` that the already-running dev
server is serving the fixed `app.js` (static files, read straight off disk — no restart needed).
Still not manually clicked-through in a real browser this session (`claude-in-chrome` extension
declined) — the user is verifying directly in their own browser tab.

---

## 2026-07-29 — `connect/astar.py`: fixed the closed-list bug behind the inadmissible-heuristic gap

The user asked to hold off on Connect's display/UI work and instead make A* find better paths —
specifically the gap STATUS already flagged: A* solved `Cat → Astronomy` in 3 hops when a 2-hop
route existed, blamed generally on cosine similarity being an inadmissible heuristic (it can
overestimate true remaining hops, so nothing textbook guarantees optimality). That framing was
correct but incomplete — tracing the code found a second, *concrete* bug riding on top of the
inadmissibility, and only the second one was fixable without abandoning the semantic heuristic
(decision B locks it; true BFS distance during a live Connect run is infeasible).

**The bug:** textbook A* closes a node the instant it's first popped and never looks at it again —
sound only because a *consistent* heuristic proves the first pop already found that node's
true-cheapest cost. Cosine-to-target has no such property. The old code closed nodes permanently
anyway (`if link in expanded: continue`, unconditional), so a page reachable both via a route that
merely *looks* cheap (low `h`, because it scores well against the target) and, later, via a
genuinely cheaper route in real hops, would get closed on the first (worse) route and then have
the second (better) route's discovery silently thrown away — not "the estimate was imperfect," but
"a strictly better answer was found and discarded by a stale invariant." Traced by hand with a
worked example: `Fast1`/`Fast2` score 0.95 (tiny `h`, so A* dives down them fast) reach `X` at depth
3 and close it; only afterwards does unappealing-looking `Slow` (score 0.3) get expanded and reach
`X` at depth 1 — a strictly shorter route through the same node, discarded by the old code.

**The fix:** reopening. A strictly cheaper rediscovery of an already-closed node now calls
`expanded.discard(link)` to un-close it, so it gets popped and re-expanded from the better cost —
and so does everything reachable through it. This is the standard fix for A* over a heuristic
that isn't provably consistent; it is bounded (costs only ever move down, in small integer hop
counts capped by `max_depth`, so a page reopens at most a handful of times) and cheap (`get_links`
on an already-seen title hits the in-memory cache layer, not the network).

**What this does NOT fix, on purpose:** the run still stops at the *first* pop of the target
itself. Reopening guarantees every *intermediate* page's recorded cost is the best the search has
found so far, but proving the target's first-pop cost is the true minimum — rather than merely the
best found before stopping — needs an admissible heuristic (a real lower bound) or exhaustive
search. That's exactly `bfs.py`'s job (the bidirectional ground-truth checker), not this file's;
duplicating it here would mean rebuilding `bfs.py` inside `astar.py`. The "NOT OPTIMAL" framing in
the module docstring stays — it's still true — but now says precisely which gap remains closed
(per-page cost propagation) and which stays open (target-stopping isn't proven minimal).

Proven with a hand-traced fake-graph repro before touching the code, then encoded as
`test_a_cheaper_route_to_an_already_expanded_node_still_wins` (asserts the 3-hop route is now
found instead of the old 4-hop one) and
`test_reopened_node_is_expanded_again_from_its_cheaper_cost` (asserts the reopened node is
genuinely reprocessed — appears in the expansion order twice — not just relabelled). 106 fast
tests green (104 + these 2), `ruff check` clean, no existing assertion touched or changed.

## 2026-07-29 — frontend: auto-fit camera + a disabled Connect/Explore toggle in the header

Two small, independent frontend changes, requested together but unrelated in code.

**Auto-fit.** The graph grows live during a run and the camera never moved to keep up — the
user had to scroll-zoom out by hand every few nodes. Added `scheduleFit()` in `app.js`, called
from the end of `applyStep()` whenever a Step actually added a node or edge (note-only Steps like
"reached target" skip it — nothing new to fit to). It calls `network.fit({ animation: {...} })`,
vis-network's built-in "zoom/pan to show every node" call. Debounced through
`requestAnimationFrame` so a burst of Steps arriving faster than one frame (a warm cache can
replay a whole run in well under a second) collapses to one `fit()` call instead of fighting
itself once per Step. Gated behind a new `#d-autoFit` checkbox (Display panel, default on) —
same escape-hatch pattern as the existing `Physics` checkbox — so a user who's manually
positioned the view isn't fought by the camera snapping back on the next tick.

**Mode toggle.** Added a Connect/Explore segmented control, centered in the header (new 3-column
CSS grid: `1fr auto 1fr`, replacing the old flex row — centering independent of how wide "wikimap"
and the algorithm label on the other side happen to be). Explore ships **disabled** —
`explore/bfs.py`/`explore/beam.py` are still one-line docstring placeholders, there is no server
route for it, and the 2026-07-26 replan explicitly locked "finish Connect before starting
Explore." Wiring the toggle to a mode with no backend would mean it silently does nothing on
click, which is worse than a greyed-out button that says why (`title="Not built yet"`). Confirmed
with the user before building it this way rather than guessing — the alternative read was
"build Explore's backend now too," which would have reversed a locked roadmap decision on a
casual UI request.

Both changes are frontend-only, no `config.py`/contract/server changes. 106 tests green (the
other 2 beyond the last entry's 104 are from `astar.py`/`test_astar.py` work happening in
parallel in another terminal this session, not this entry). Not manually browser-tested — no
`claude-in-chrome` tooling this session (user declined the extension) — same owed-verification
caveat as the last two frontend entries.

---

## 2026-07-29 — frontend: node size can now be driven by score/depth, not just one flat slider

First item off the UI-refactor backlog gathered while researching Six Degrees of Wikipedia /
Connected Papers / Obsidian's graph view (see that session's note — condensed version: Connected
Papers encodes node size by a real data field, e.g. citation count, in addition to colour; wikimap's
`#d-nodeSize` was a single uniform multiplier even though every `Node` already carries `score` and
`depth`).

Added `sizeFor(node)` in `app.js`, mirroring the existing `nodeColor(node)` split (`colorBy` already
picks between score/depth for colour): a new `#d-sizeBy` select (`uniform` / `score` / `depth`,
default `uniform`) now decides whether `#d-nodeSize`'s slider value is applied flat to every node or
scaled per node — `scoreSizeScale` maps cosine `[0,1]` to a `[0.6x, 1.5x]` multiplier, `depthSizeScale`
decays with `abs(depth)` (abs matters because `bfs`'s backward frontier carries negative depth) down
to a `0.5x` floor. Both the live `applyStep` path and the `applyDisplay` resize-on-slider-change path
now call the same helper, so switching `sizeBy` mid-run or after a run both work.

Deliberately frontend-only, no `config.py`/contract changes — `Node.score`/`Node.depth` already
existed on the wire for colour-by, this just reads the same fields for a second purpose. Default is
`uniform`, so no existing behavior changes unless the new control is touched. 104 tests still green
(no Python file touched). Not manually click-tested in a browser by the agent that built it — no
`claude-in-chrome` tooling was available this session (user declined the extension) — confirmed only
that the running dev server (already up on `:8000` in the user's other terminal) is serving the
edited `index.html`/`app.js`. Visual confirmation is still owed, same caveat as the node-click panel
before it.

---

## 2026-07-29 — review pass on `bfs.py`: stale test docstring, `max_depth` semantics decided explicitly

Caught in a review of the previous entry's work, not while building it. Two findings:

- `test_backward_search_finds_a_meeting_forward_alone_would_take_longer_to_reach` (test_bfs.py)
  described its own outcome using "the smaller-queue rule" — that's Attempt 2's logic (frontier
  *size*), the one the module docstring documents as the second live-caught bug, not the
  depth-level rule that actually shipped. The test's assertions were always correct; only the
  prose explaining *why* was describing a discarded design. Traced by hand to confirm what's
  really going on: backward gets exactly one turn before the tie flips back to forward, and the
  meeting is found mid-*forward*-expansion, not during a backward turn as the old docstring
  claimed. Fixed to describe the depth-level rule.
- `max_depth` was applied independently to `bfs`'s forward and backward frontiers with no comment
  on what that implies: for greedy/A* the knob caps one directional walk (so it IS the max path
  length); for `bfs` it caps each side, so the real reachable path length is `2 * max_depth`, not
  `max_depth`. Same slider, different meaning depending on which algorithm is selected, and
  nothing said so. **Decided (not changed): keep it per-side, as it already behaved** — halving it
  to match greedy/A*'s meaning would make bidirectional BFS unable to certify the very depths
  greedy/A* are allowed to search to, which breaks its entire job as their ground-truth checker.
  Documented explicitly in the module docstring instead of left implicit.

No code behavior changed except the docstring addition; no existing assertion changed.

---

## 2026-07-29 — `bfs.py`'s `max_nodes` cap was checked once per whole ply, not per node

Found while reasoning about why an uncapped, unranked search like `bfs` (deliberately not
`top_k`-capped — see the module docstring, and don't reconsider that: pruning it would make it
just as blind as greedy/astar to the exact routes it exists to catch them missing) could still
overshoot its own resource cap by a lot. The check sat at the top of the `while` loop — once per
whole ply — and a ply is every node at one depth level processed as a batch, with no size limit of
its own. A concrete before-fix repro (a page fanning out to 10 links, each of THOSE fanning out to
10 more): asked for `max_nodes=20`, got **111** nodes back. On greedy/astar this can't happen
because `top_k` bounds a single tick's fan-out to ≤20; `bfs` had no equivalent backstop at any
granularity finer than "the whole ply."

**Fix:** moved the check inside the per-node loop, so it fires right after each node's own
(already-fetched, so free) fan-out finishes — overshoot is now bounded by one page's link count,
not by an entire ply's. Same pass also fixed a second, smaller waste: even after the two searches'
`meeting` point was found mid-ply, the old code kept fetching the rest of that ply's not-yet-touched
nodes before checking `meeting` at the bottom of the loop. Fixed to `break` the moment `meeting` is
set — nothing later in the same ply can be shorter anyway (the depth-level invariant the module
docstring already proves), so those fetches were pure waste. The two fixes shipped together since
they touch the same lines and interact: checking `meeting` before checking the cap, in that fixed
order, is *how* "found the target" is guaranteed to win over "hit the cap" when a single discovery
would trigger both — no extra flag needed, just the order of two `if`s.

104 fast tests green (was 102, +2: one pins the tightened overshoot bound, one constructs a case
where the same discovery would trip both `meeting` and the cap, asserting "reached" wins), `ruff
check` clean, no existing assertion changed.

**Considered and rejected in the same conversation: pruning `bfs`'s branching (via `top_k`, ranked
or even an arbitrary un-ranked slice) to control cost.** Any pruning — cosine-ranked or not — makes
`bfs` capable of missing the true shortest path, which is exactly greedy/astar's failure mode. A
"ground truth" that shares its checkee's blind spot isn't one. Real, not-yet-built levers that *don't*
touch this guarantee, for whenever `bfs`'s cost (inherent to being exhaustive on Wikipedia's ~300
branching factor) is worth attacking again: firing a ply's fetches concurrently (threads; the fetch
layer is sync I/O, so this doesn't need the async-httpx rewrite `CLAUDE.md` already defers) helps
both directions equally; batching multiple titles into one MediaWiki request (`titles=A|B|C`) was
considered and set aside — `list=backlinks` has no multi-title equivalent at all, so it would only
ever help the forward half of the search, for the cost of bypassing `wikipediaapi` in `get_links`
(a real architectural change, and exactly the async-httpx upgrade `CLAUDE.md` already says is
deliberately deferred, not something to back into as a side effect of a bfs perf pass).

Also worth a note for future-me: this session's memory of the *predecessor* repo having request
batching was checked against that repo's actual code and full git history — it isn't there, and
never was (confirmed: no `titles=`, no batch function, in any commit). Don't trust that memory again
without re-checking; it isn't a real pattern to port.

---

## Picking up where 2026-07-28 left off

**State: everything green and working.** 102 fast tests pass, `ruff check` clean, no empty files.
Run `uvicorn wikimap.server.app:app --reload` and open <http://127.0.0.1:8000>.

**All three Connect algorithms (greedy, astar, bfs) are now live-cross-checked against each other
on the same real pair** (`Mitsubishi → Kanye West`): astar found 3 hops, bfs (after fixing the
ply-synchronization bug below) also found 3 hops via a different route, and neither is longer than
the other — which is the sanity check bfs exists to provide. Worth re-running occasionally on other
pairs as a regression check, since nothing in the test suite exercises three real algorithms against
one live pair at once.

**The node-click detail panel (entry below) is proven at the API level but not yet clicked in a
real browser** — it was built in a background session with no browser attached. Backend verified
directly (`curl "/api/page?title=Cat"` returns a real summary; a nonexistent title 404s), and the
structural/unit tests are green, but nobody has actually opened the page and clicked a node yet.
Do that before treating the feature as fully proven.

**One review finding deliberately deferred: cache writes are not atomic.**
`LinkCache._lookup` does a bare `path.write_text(...)`. A crash or Ctrl-C mid-write leaves truncated
JSON, and the read path has no validation — so `json.loads` will raise for that title on *every*
subsequent run, permanently, curable only by deleting the file by hand. The fix is three lines
(write to `.tmp`, then `Path.replace`, which is atomic). **Held at the user's direction until
deployment**, since the failure needs a crash mid-crawl to trigger. Do not "helpfully" fix it early;
do not forget it either.

**Next task: `connect/bfs.py`.** Everything it needs already exists:

- `LinkCache.get_backlinks` (built, tested, live-verified) is the backward half.
- It must be **bidirectional** — unidirectional is 8,421 expansions for a 4-hop path versus 42.
- It must **not** be cosine-capped. A cosine-capped BFS just reproduces greedy's bias and therefore
  cannot answer "did greedy miss a shorter route", which is the only reason to build it.
- Register it in `algorithms/connect/__init__.py`'s `ALGORITHMS` dict and it appears in the UI
  automatically — the frontend picker is built from `/api/config`.

**Two known gaps, deliberately open** (both have full entries below): `MoveEvaluation.from_` does not
serialize as `from` despite its docstring saying so (fix in step 8), and this A* is not optimal
because the cosine heuristic is inadmissible — it returned a 3-hop `Cat → Astronomy` when a 2-hop
route existed.

**One thing never verified:** the display panel's slider *ranges* and feel. The structure, wiring and
persistence are proven, but nobody has actually dragged them — expect to retune min/max values.

---

## 2026-07-28

### Node-click detail panel: on-demand page lookup, not a Step-contract addition

Clicking any node (mid-run or after, any node, not just the winning path) now opens a panel with
title, score, depth, the page's real Wikipedia summary, and a link to the article. The interesting
decision wasn't the UI — it was **where the summary data comes from**, and the answer is
deliberately not "add it to `Node`."

**Why the summary isn't riding along in the Step stream.** `Node` (`graph/contracts.py`) stays
`id`/`score`/`depth`. Fetching a summary costs an `extracts` API call per page — paying that for
every node in every fan-out (up to `top_k` per tick) would multiply the already-expensive part of
a cold run (embedding ~300 links per page) by a second network round-trip nobody asked for, for
data most nodes will never have their panel opened. Fetching on click, once, only for the page the
user actually cares about, is the same "pay for what you use" shape as the cache layer already
uses. `GET /api/page?title=` is a new, independent lookup — the Step/Node contract is untouched,
and old clients of that contract (both algorithms, both sets of tests) needed zero changes.

**`WikiClient.get_summary` reads `.summary` and `.fullurl` off ONE `wikipediaapi` page object** —
the same object `get_links`/`exists` already construct via `self._wiki.page(title)`. Reading two
different attribute groups off one page object costs exactly two API calls (`extracts` for
`.summary`, `info` for `.fullurl`), not four, because `wikipediaapi` fetches attributes lazily in
groups keyed by which raw MediaWiki action produces them — fetching the same group twice is free
(cached on the page object), fetching two different groups once each is the two-call floor. Getting
this to sit right needed one non-obvious ordering: read `.summary` before checking `.exists()`,
because a page that raised no exception on `.summary` but reports `exists() == False` is exactly
the "genuinely no such page" case `get_links` already treats identically to a network failure
(both come back as one falsy result — `[]` there, `None` here — see that method's own docstring on
why it's deliberately not distinguished).

**Query param, not `/api/page/{title}` path param.** Wikipedia titles legally contain `/`
("AC/DC"), and a path segment can't carry that safely through Starlette's default matching —
`seed`/`target` on `/api/connect` already establish query params as this project's answer to
exactly this problem; `/api/page` follows the same rule rather than reopening the question.

**A second lazy singleton, `_wiki_client()`, instead of reaching into `_caches()`'s `LinkCache`.**
`LinkCache` holds a `WikiClient` as a private implementation detail for the *search* path.
Reaching into `_caches()[0]._client` to reuse it would have coupled an unrelated route to another
class's internals to save nothing — `WikiClient` itself does no caching (`LinkCache` is the
cache), so a second instance costs only a second `USER_AGENT` read. Kept separate on purpose;
"lazy `@lru_cache(maxsize=1)`, imports the heavy dependency inside the function" is the *pattern*
worth reusing here, not the specific existing instance.

**`network.on("click", ...)`, not `selectNode`.** `click` fires uniformly for node clicks, edge
clicks, and empty-canvas clicks, with `params.nodes`/`params.edges` saying which — one listener
gives both "open panel on node" and "close panel on background click" for free, instead of wiring
`selectNode` and `deselectNode` separately.

**A parser bug found while writing the regression test, worth remembering for the next structural
test.** The existing `test_settings_panel_is_not_inside_the_graph_container`'s `HTMLParser`
subclass doesn't push void/self-closed elements (`<input ... />`) onto its ancestor-tracking stack
— correct — but it also doesn't override `handle_startendtag`, whose *default* implementation
calls `handle_endtag` for every self-closed tag regardless. Net effect: every self-closing `<input
... />` silently popped one real ancestor off the stack. This never broke the original test because
`#panel` is found early, before any of the settings panel's own self-closing inputs are parsed —
but the new `#node-panel` sits *after* roughly a dozen of them, and the accumulated erroneous pops
emptied the stack completely by the time the parser reached it, producing a false "not found."
Fixed in the new test only (`handle_startendtag` overridden to call `handle_starttag` alone) — the
original, already-green test was left untouched rather than "helpfully" fixed, per the
non-destructive rule; it happens to still pass because its assertion never depended on exact stack
depth, only on `#panel` being found at all and `#graph` being absent from its ancestors.

### `connect/bfs.py`: bidirectional BFS, and a shortest-path bug caught only by testing it live

Built as planned — bidirectional (`get_links` forward from the seed, `get_backlinks` backward from
the target), deliberately NOT cosine-capped (decision C's top-K ranking is exactly what makes
greedy/A* untrustworthy as judges of their own optimality, so the algorithm built to check them
can't use the same shortcut), and touching no embedding at all (`Node.score` is always `None` —
a genuine efficiency win, not just an omission, since embedding is the expensive part of every
other algorithm's tick and BFS never needed a ranking).

**The interesting part was getting "first meeting found is provably shortest" to actually be true.**
Two wrong attempts, both caught by the same live test, neither caught by the unit test suite:

1. **Attempt 1** picked which side to expand next by comparing the two frontier *queues'* raw
   length, updated as each queue drained node-by-node. This lets one side's queue empty out while
   racing several hops deep, because a queue that happens to stay short keeps "winning" the
   comparison regardless of how deep it already is. Live-tested on `Mitsubishi → Kanye West`
   (chosen because it's a real, well-connected, unrelated pair — exactly the case that stresses
   branching factor) it returned a 4-hop route, `Mitsubishi -> Aircraft -> Sleep -> Bipolar disorder
   -> Kanye West`. That's a contradiction on its face: A* (no optimality guarantee at all) had
   already found a 3-hop route on the same pair moments earlier. A "ground truth" algorithm
   returning a *worse* answer than the heuristic search it exists to grade is not a performance
   quirk, it's a correctness bug.
2. **Attempt 2** fixed the queue-draining problem by comparing whole-frontier **size** between
   completed plies instead of mid-drained queues. Still wrong, for a subtler reason: size is not
   depth. A side whose frontier happens to stay numerically small — a thin, one-link-per-page
   chain, common on Wikipedia — keeps winning the size comparison and can race ahead in actual hop
   depth indefinitely, while the other side's wider-but-shallower frontier never gets a turn. Same
   live query, still wrong (would have reproduced the same class of failure had it been re-tested
   before noticing the reasoning gap).
3. **The fix:** compare depth *level* directly — `forward_depth[frontier[0]]` vs
   `backward_depth[frontier[0]]`, expand whichever is lower (ties either way, since a tie means both
   sides are about to process the same depth number). This bounds the two sides' depths to differ
   by at most one at any moment, which is the actual textbook bidirectional-BFS invariant: by the
   time any node at depth *d* is discovered, every node at depth *< d* on **both** sides has already
   been fully expanded, so nothing shorter remains unexplored. Re-tested live: 3 hops,
   `Mitsubishi -> Bank -> Liverpool -> Kanye West` — no longer than A*'s 3-hop answer, which is the
   actual bar "ground truth" has to clear.

**Why the unit tests caught neither bug.** The fake-graph test fixtures were small enough that the
depth gap the bugs depend on never opened up wide enough to matter, or — in the one test that *did*
happen to exercise cross-direction meeting — the bug produced a *different meeting node* on an
otherwise still-correct path, and the original assertion had over-specified which node the searches
met at (an implementation detail, not a guarantee) rather than just the path and hop count. Fixed the
test to assert only what's actually promised. **The general lesson, worth repeating next to the
vis-network one from 2026-07-26: a unit test suite proves the algorithm does what the fakes allow it
to do; it does not substitute for running the real thing on a real, adversarially-chosen pair.** Both
bugs here were only caught because the two algorithms were cross-checked against each other live —
neither would have been caught by either algorithm's own test suite in isolation.

---

## 2026-07-27

### Review-fix pass: seven findings from a read of the vibe-coded session

A full review of the three uncommitted commits' worth of work (backlinks, params, A*, panel). Seven
of eight findings fixed; the eighth (atomic cache writes) deferred to deployment — see the header
block above. Non-destructive as always: **no existing assertion changed**, +2 tests, 78 → 80.

**1. Stale comments in `config.py`.** Two comments still described the per-run-params work as
future ("a pre-run settings UI (post-MVP) will…", `# not yet wired`). It shipped in `ecb0a9a`. A doc
that describes a *false* future is worse than a missing one — the next session reads "not yet wired"
and rebuilds it. Rewritten to describe the mechanism that actually exists.

**2. `TOP_K_BOUNDS` floor raised 0 → 1.** K=0 keeps no candidates, so every run dead-ends on tick
one. The config comment had already flagged this and explicitly said to fix it "during the params
work" — the params work shipped and it was missed. It mattered more than the note suggested, because
those bounds are *published to the browser*: the UI was actively offering a value guaranteed to fail
silently. Verified end to end: `top_k=0` → HTTP 422, `/api/config` publishes `[1, 20]`,
`RunParams(top_k=0).top_k == 1`. Cost nothing in tests — every bounds assertion already read
`config.TOP_K_BOUNDS[0]` symbolically rather than hardcoding `0`. That is the payoff for writing
tests against the constant instead of the literal.

**3. Cache directories anchored to the project root.** `Path("data/links")` is relative, so it
resolved against the *launch* directory. Starting uvicorn from anywhere but the repo root would miss
the 165-file warm cache, silently re-crawl from cold, and scatter a stray `data/` folder. A cache
whose location depends on your shell's cwd is not a cache. Now `Path(__file__).resolve().parents[3]`.
Correct for the editable install this project uses; flagged in-code to revisit if it is ever
installed non-editably or containerised. No test churn — every cache test already passed
`data_dir=tmp_path` explicitly.

**4. The broad `except Exception` in `WikiClient` now logs before swallowing.** Both fetch methods
catch everything and return `[]`. That is right for a timeout and wrong for our own bugs: an
`AttributeError` from a typo was indistinguishable from "this page has no links", so a search would
quietly find nothing with no trace. Kept broad (retry-on-anything is the intent) but added a
`logger.warning(..., exc_info=True)`. **The general shape: a broad except is fine, a broad *silent*
except is not.**

**5. `max_nodes` now counts distinct pages, not sightings.** Both algorithms did
`node_count += len(top)`, adding the whole slice each tick — so a page appearing in several fan-outs
was counted several times. The cap tripped early and the figure in the Step note didn't match the
circles on screen. A* needed no new state (`len(cost_from_seed)` is already exactly the distinct
set, since every link in a `top` slice ends up a key); greedy gained a `seen` set kept deliberately
separate from `visited` — **`visited` is the path, `seen` is the drawing, and conflating them is what
caused the bug.**

Pinned by two new tests, and — per the practice established by the vis-network fix — **both were run
against the old counting first and confirmed to fail.** Writing them surfaced a genuine gotcha worth
recording: the first attempt used `RunParams(max_nodes=5)`, which `__post_init__` silently *clamped*
to the `MAX_NODES_BOUNDS` floor of 20, so the tests were quietly exercising the depth cap instead.
The clamp working as designed made a test lie about what it covered. Both tests now use in-bounds
values and set `max_depth=12` so only the node cap can trip.

**6. Frontend: `replayBtn` no longer stubbed with `|| {}`.** Assigning `.disabled` to a bare object
succeeds and does nothing, making a missing button undetectable — the opposite of the `bind()` helper
three lines away. Now a real element-or-null behind `setReplayEnabled()`, which logs once like
`bind()` does. The blast-radius protection from the vis-network fix is preserved; only the silence
is gone.

**7. Study-note comments removed from shipped source.** `# higher order functions`, `# wikipedia
user shit`, a dangling bare `#`, and a mis-typed note about the SSE blank line that duplicated the
docstring above it. Harmless individually; collectively they read as unfinished. `LEARN.md` is the
designated home for that kind of note and the concepts behind them have been moved there.

---

## 2026-07-26

### Bug: vis-network deletes its container's children — the settings panel must be a SIBLING of #graph

Shipped the display panel nested inside `#graph`. The page came up dead. Cause, read out of the
vis-network bundle rather than guessed at — `Canvas._create()` opens with:

```js
for (; this.body.container.hasChildNodes(); )
    this.body.container.removeChild(this.body.container.firstChild);
```

**vis-network wipes every child of the element it is handed.** So `#panel` was deleted the instant
the Network was constructed, and the failure then cascaded in a way worth remembering:

1. `querySelectorAll("[data-display]")` returned empty, so no display state existed.
2. `getElementById("reset-display")` returned `null`, and `.addEventListener` on it threw.
3. Module code runs top to bottom, so that **one** throw skipped every listener registered
   afterwards — including the run-form submit handler. **The Run button stopped working because of
   a bug in the settings panel.**

Fixes, in order of importance:

- **Structure.** `#canvas` (positioned) now wraps `#graph` and `#panel` as siblings; `#graph` is
  absolutely positioned to fill it. Comments in both the HTML and CSS say why, since the nesting
  looks perfectly reasonable.
- **A regression test**, `test_settings_panel_is_not_inside_the_graph_container`, parsing the served
  HTML and asserting `#graph` is not among `#panel`'s ancestors. Verified it actually fails on the
  broken markup and passes on the fixed one — a check that cannot fail is decoration.
- **Blast radius.** A `bind(id, event, handler)` helper logs a console error and returns instead of
  throwing on a missing element; `initDisplayControls()` now runs *last*, after the run form is
  wired; `applyDisplay()` no-ops when the panel is absent instead of writing `undefined` into every
  physics option; node size falls back to 12.

**The general lesson, recorded because it will recur:** a library handed a DOM container may *own*
it. And in a script with no module boundaries, an exception isn't contained to the broken feature —
it silently disables everything below it. Ordering listener registration by importance is cheap
insurance.

### Graph display settings — and the line between server knobs and browser knobs

Added an Obsidian-style floating settings panel over the graph canvas: arrows toggle, text fade
threshold, node size, link thickness, colour-by, replay, plus the four force-directed physics
sliders (centre / repel / link force / link distance) and a physics on-off escape hatch.

**The decision worth recording is where these live: the frontend, NOT `config.py`.** Contract 1 says
config owns every knob, which reads like it should cover these too. It doesn't, and the reasoning is
the reason contract 2 exists:

- A spring constant never reaches the server and cannot change what the algorithm does. Contract 1's
  purpose is that *algorithms* never hardcode *their* settings; its examples are all search knobs.
- Serving render settings from `/api/config` would give the backend an opinion about drawing —
  the same layering violation as an algorithm knowing about the renderer, just pointed the other way.
- They are per-browser preferences, so they belong in `localStorage`, which the server cannot own.

**Rule adopted: if it changes the SEARCH it lives in `config.py`; if it changes the PICTURE it lives
in the frontend.** The panel makes that split visible — three sections, with the Search section
labelled "sent to the server" and the others "browser only".

Implementation notes:

- **Controls are read generically.** Every display input carries `data-display` and an id of
  `d-<key>`; `readDisplay()` walks them and builds the settings object from the DOM. Adding a control
  is adding HTML — no second place to register it.
- **Repel slider is negated in JS.** vis-network wants a *negative* `gravitationalConstant` for
  repulsion; a slider that moves right for "more repel" is the only sane control, so the sign flip
  lives at the boundary.
- **Text fade has no vis-network option.** Implemented as a `zoom` listener that sets the global font
  size to 0 below the threshold — one option write rather than N DataSet updates.
- **Nodes now carry `score` and `depth` as DataSet fields.** vis-network ignores keys it doesn't
  recognise, which makes a DataSet item a fine place to park real data — and it is what lets
  "colour by depth" recolour an existing graph without re-running the search.
- **Replay is close to free.** The algorithm already emits a recorded Step stream, so animating the
  build is the same steps on a different clock. Obsidian has to synthesise this; we had the data.

**Zero server changes**, so the 77 tests were untouched and still pass. Verified by cross-checking
every `getElementById` in `app.js` against the ids `index.html` defines (no mismatches), `node
--check` on the JS, and fetching the served page.

### `connect/astar.py` complete — and it beat greedy on the first real run

`AStarConnect` implements weighted A*: `f = g + W * h`, `h = hop_scale * (1 - cosine(page, target))`.
`heapq` frontier, `cost_from_seed` map, `came_from` chain for path reconstruction. Two new knobs
(`HEURISTIC_WEIGHT`, `HEURISTIC_HOP_SCALE`) with bounds, plus an algorithm registry so the server can
offer both. **77 fast tests green** (18 new), ruff clean.

**Live result — A* found a shorter path than greedy on `Cat → Astronomy`:**

```
A* (W=1):  Cat -> Age of Discovery -> Astronomer -> Astronomy     (3 hops)
greedy:    Cat -> Science (journal) -> Spiral nebulae -> Galactic astronomy -> Astronomy   (4 hops)
```

Cost is the tradeoff: A* expanded 6 pages / 91s cold; greedy expanded 4 and reused warm caches.

**The weight endpoints, live-confirmed:**

```
W=0    f = 0.00, 1.00, 1.00, 1.00   <- f == g exactly; breadth-first ordering
       21 expansions, 67s
W=25   f = 79.91, 55.02, 55.57      <- g swamped by the heuristic; greedy ordering
       8 expansions, 0.05s
```

**A concrete demonstration that this A* is NOT optimal** — worth recording because it is the
inadmissibility caveat happening for real, not hypothetically. With `max_depth=6`, A* returned a
**3-hop** path. With `max_depth=2` forcing a wider sweep, it found a **2-hop** path that existed all
along: `Cat -> Night vision -> Astronomy`. Textbook A* would never do this; ours does because
cosine-derived `h` can overestimate the true remaining hops, so a deeper route can be popped before a
shallower one, and the search stops at the first pop of the target. Fixing it properly means
continuing until the frontier's minimum `f` exceeds the found path's cost — real work, deliberately
not done: decision B already accepted an estimate over ground truth, and the cost of exhaustive
confirmation is exactly what the top-K cap exists to avoid. Lowering `W` moves toward optimal and
pays for it in expansions; that tradeoff is now a UI slider.

**Design notes:**

- **Depth cap `continue`s instead of returning.** Greedy walks one path, so its depth cap ends the
  run. A* holds a frontier — a too-deep page is skipped while shallower candidates still get their
  turn. Pinned by `test_depth_cap_skips_deep_pages_but_keeps_searching`.
- **`h` reuses the similarity already computed for ranking**, so the heuristic costs zero extra
  embeddings — the expensive part of every tick.
- **`itertools.count()` tiebreaker in the heap tuples.** Without it, equal `f` values fall through to
  comparing the next element; a monotonic counter keeps comparisons off the titles and makes ties
  deterministic (FIFO).
- **`_caches()` split out from `_algorithm()`.** Both are `lru_cache`d, but the caches must be built
  once *in total* while algorithms are built once *per name*. Had the caches stayed inside
  `_algorithm`, switching greedy → astar would have handed A* a cold cache and re-crawled Wikipedia.
- **The registry lives in `algorithms/connect/__init__.py`, not the server.** Which algorithms exist
  is domain knowledge; the server should offer a new one without learning anything but its name.

**Test-instrument mistake worth remembering:** five A* tests failed against correct code because the
helper read the expanded page from `step.edges[0].source`. A page with no outbound links expands
normally but emits a Step with zero edges, so the helper silently dropped it. Same family as step 4's
score-ordering mix-up. The fix was to read the note, not the edges.

**Non-destructive tally:** two test doubles gained `lambda *_:` because `_algorithm` now takes a name.
No assertion changed.

### Step 6 (per-run params) complete — knobs are live controls

`RunParams` landed in `config.py`, `run()` gained a third argument, the server turns query params
into one per request, and the frontend builds its controls from `/api/config`. **59 fast tests
green** (15 new), ruff clean.

Implementation notes worth keeping:

- **`params: RunParams | None = None`, built inside the function**, not `params = RunParams()` as a
  default argument value. A default argument object is created once at function-definition time and
  shared by every call — the classic Python trap. Harmless for a frozen dataclass today; a
  landmine the moment anything mutable joins it.
- **Clamping lives in `__post_init__`** via `object.__setattr__` (normal assignment on a frozen
  dataclass raises). This is what actually enforces decision C's K≤20 ceiling: the server's 422 only
  covers HTTP callers, whereas any Python caller could otherwise construct `RunParams(top_k=999)`.
  Written after yesterday's "a docstring is not a test" lesson — the ceiling is now enforced by code.
- **Bounds are published, not hardcoded twice.** `/api/config` grew a `bounds` object; the route's
  `Query(ge=…, le=…)` reads the same tuples. The frontend's inputs ship with no `min`/`max`/`value`
  in the HTML at all and are disabled until the fetch fills them in, so the browser can never hold a
  stale copy of a number that lives in `config.py`.
- **Non-destructive, with one honest exception.** No assertion in any existing test changed. Two
  *test doubles* needed `params=None` added to their `run` signatures (`_FakeAlgorithm`,
  `_Exploding`) — an interface change necessarily reaches its fakes. Everything else, including the
  bare `?seed=&target=` URL, works untouched.

**Live verification** (warm `Cat → Astronomy`):

```
top_k=20  -> nodes per tick [1, 20, 20, 20, 20]
top_k=5   -> [1, 5, 5, 5, 5]
top_k=2   -> [1, 2, 2, 2, 2]
max_depth=6 -> solved: 'Galactic astronomy' -> 'Astronomy' (score 1.000)
max_depth=2 -> "stopped: hit cap at 'Spiral nebulae' (depth 2, 41 nodes)"
top_k=21    -> HTTP 422
```

### Measured branching factor: ~364 median, not ~300 — and K is not a cost knob for greedy

Measured over the 21 pages in `data/links/` (real cache, real pages this project has visited):

| stat | links |
| --- | --- |
| median | 364 |
| mean | 497 |
| max | 1804 (`kanye west`) |
| `Cat` | 1181 |

So `TOP_K = 20` keeps **12.6%** of an average page's links. CLAUDE.md's "~300" was a slight
underestimate. Note this is *not* the Wikipedia-wide figure — published stats put median outdegree
around 12–20 across all articles, dragged down by millions of stubs. The pages a speedrun actually
touches are popular, heavily-linked ones. Both numbers are right about different populations; the
one that matters for cost modelling is ours.

**The load-bearing discovery:** `greedy.py` embeds *every* link (line 56) and only then slices to
`TOP_K` (line 60). Per-page cost is therefore O(outdegree), **independent of K**. For greedy, K
controls only how many nodes get drawn — raising it to 100 costs nothing. K becomes a cost knob
only for algorithms that expand more than one node per level, i.e. BFS and A*, where cost grows as
K^depth. This means the settings UI's K slider means something completely different per algorithm,
which the UI will eventually have to communicate.

### BFS will be bidirectional, and will not be cosine-capped

Two decisions, both following from the above.

**Bidirectional.** To find an L-hop path, unidirectional BFS expands `sum(K^i for i < L)`; searching
from both ends and meeting in the middle expands roughly `2 * sum(K^i for i < L/2)`. At K=20, a
4-hop path costs 8,421 expansions unidirectionally versus **42** bidirectionally — ~200x. This is
the difference between "impossible" and "feasible", so BFS is not worth building unidirectionally.

**Correction to an earlier note in this entry:** it first said `wikipediaapi` exposes `.backlinks`
so the reverse direction was free. It exposes it; it is not usable. Reading the library source
turned up two blockers, both now pinned by tests:

1. `Wikipedia.backlinks` paginates to exhaustion — `while "continue" in raw` with no cap. Accessing
   `page.backlinks` on "Cat" would page through six figures of results: hundreds of requests, minutes
   of hanging, no way to stop it early through the public API.
2. Its continuation requests are rebuilt from the *original* params dict, so kwargs like
   `blnamespace=0` are dropped after the first page. You would get ns0 results followed by
   unfiltered ones — a silent correctness bug, the same family as the colon-filter bug this project
   already refuses to inherit.

**Decision: issue the backlinks query directly** (`requests`) inside `WikiClient`, capped, with
`blnamespace=0` re-sent on every continuation. `WikiClient` remains the only class that talks to
Wikipedia, so the data-layer rule holds, and CLAUDE.md already names the raw MediaWiki API as the
documented upgrade path — this arrives earlier than planned and stays synchronous.

**Accepted bias, recorded so BFS results aren't over-trusted:** `BACKLINK_LIMIT = 500` is one API
round trip, and MediaWiki returns backlinks in page-id order, *not* relevance order. So the cap
takes an arbitrary 500, not the best 500. Ranking them by relevance would require fetching all of
them first, which is exactly what the cap exists to prevent. No cheap fix exists.

**Live verification** (not just mocks): `Cat` returned exactly 25 backlinks in 0.53s with `limit=25`,
one request, no namespaced titles. The library's version would have paged through ~100k.

**Not cosine-capped.** Ranking links by cosine-to-target and keeping the top 20 *is* the greedy
bias. A BFS built on that filter is not a neutral baseline — it is greedy-with-more-branching, and
cannot answer "did greedy miss a shorter route" because it searches the graph greedy already
chose. If BFS is to be a baseline it must cap by something unbiased (random-K, or uncapped at low
depth). Recorded because the brief calls BFS a "correctness baseline" and that claim is only true
under this condition.

### A* heuristic: cosine must be rescaled into hop units before it can be added to `g`

`f = g + h` requires both terms in the same units. `g` counts hops (1, 2, 3…); raw cosine lives in
[0, 1]. Adding them directly means the heuristic can never outweigh even one hop, and A* silently
degenerates into BFS. This is the single easiest way to get A* wrong, so it is recorded before the
code is written.

Decided form:

```
h = LAMBDA * (1 - cosine(page, target))       # cosine -> estimated hops remaining
f = g + W * h                                  # W is the settings-UI dial
```

`LAMBDA` ≈ 4, grounded in published Wikipedia path-length measurements (~3.4–3.9 average clicks
between articles). `LAMBDA` should be *calibrated* against our own runs rather than left at 4 — we
already log path length and can record the seed↔target cosine for each solved run.

`W` makes weighted A* span the whole spectrum: `W = 0` ignores the heuristic (BFS behaviour),
`W = 1` is balanced, `W -> large` ignores hop count (greedy behaviour). One algorithm plus one
slider therefore demonstrates greedy and BFS as endpoints — which is the comparison the brief
wanted from building three separate algorithms.

**Explicitly not claimed: optimality.** A*'s shortest-path guarantee requires an *admissible*
heuristic (never overestimates true remaining cost). Cosine similarity is a semantic estimate with
no such bound, so this A* is a good search, not a proof of shortest path. The textbook-standard
admissible option (ALT: landmark distances plus the triangle inequality) needs the whole graph
precomputed offline and is therefore ruled out on live Wikipedia. Decision B already accepted an
estimate over ground truth; this just records that the guarantee does not sneak back in with A*.

### Enriched embeddings: anchor-only, and never mixed within one comparison

Considered embedding "title + summary" instead of bare titles, to give the model more than two
words to work with. **Cannot be done for all embeddings:** ranking one page's links needs ~364–497
embeddings (measured above) and `wikipedia-api` fetches summaries one page at a time, so enriching
candidates would mean ~500 extra HTTP requests *per expansion*. Title-only at ranking time is
forced by cost, not preference.

**Where it is affordable is the anchor** — the target in Connect, the seed in Explore. That is one
page per run, and every single comparison is made against it, so improving that one vector improves
all ~500 comparisons for the price of one fetch.

**The constraint that makes this safe:** never mix enriched and bare representations on the *same
side* of a comparison. Text length shifts a sentence-transformer's output, so an enriched vector and
a bare vector are not directly comparable. Anchor-enriched vs all-candidates-bare is fine, because
ranking only cares about relative order and a fixed anchor biases every candidate identically. Some
candidates enriched and others bare would silently corrupt the ranking.

**Correctness hazard this creates, to handle before implementing:** `EmbeddingCache._path_for` keys
on the title alone, and `data/embeddings/` already holds **9,616** bare-title vectors. Changing what
`embed(title)` returns without changing the key would serve enriched vectors for bare requests —
wrong, plausible-looking, and invisible. Enrichment must live under a separate cache namespace
(e.g. a `__rich` key suffix), not replace the existing one.

**Status: not implemented, and gated behind a measurement.** Enrichment could plausibly make things
*worse* — summaries add generic filler ("is an American...") that dilutes topical signal. It goes in
behind a config flag with a slow-marked test comparing ranking quality both ways, keeping whichever
wins. Not adopted on plausibility alone.

### Roadmap replan: finish Connect before starting Explore

The brief's step 6 is the Explore settings UI and step 7 is the rest of Connect. **Reversed by
decision, 2026-07-26:** Connect mode gets completed first, then Explore. Reasoning — Connect is the
only mode that exists (greedy ships and works), so finishing it produces a coherent, shippable mode
rather than two half-modes; and each Connect algorithm added is another consumer proving the shared
pieces before Explore inherits them.

Consequences recorded so we don't rediscover them:

- **No shared base above Connect and Explore yet.** A parent `Algorithm` class holding `__init__`
  (caches) and an anchor-parameterised link-ranking helper was proposed and **deliberately
  deferred** until Connect is entirely complete. Rationale: an abstraction generalised from one
  mode's needs is a guess; generalising after three Connect algorithms exist means the shared shape
  is observed rather than predicted. `ConnectAlgorithm` stays the only base for now, and
  `explore/` stays untouched.
- **Non-destructive is the constraint.** Every step must leave the existing 30 tests green without
  editing them. Practically that means new parameters arrive with defaults, `/api/config` only
  gains fields, and existing request URLs keep working.

### `TOP_K = 20` resolved: 20 is a ceiling, not a fixed value

Decision C called `TOP_K` "locked", which read as immovable and contradicted contract 1's promise
that the settings UI turns these dials. Resolved: **what decision C locks is the mechanism** (rank
links by cosine similarity to the anchor, keep the best K) **and the upper bound.** K may vary
below 20 and may never exceed it. Bounds recorded in `config.py` as `TOP_K_BOUNDS = (0, 20)`.

Open caveat, flagged not fixed: a floor of 0 keeps no candidates, so a Connect run dead-ends on tick
one. Legal but useless; raising the floor to 1 is the obvious call when these stop being comments
and become validated constants.

### Per-run params will travel as a `run()` argument, not constructor state

Design settled ahead of implementation. `RunParams` (a frozen dataclass, defaults sourced from the
`config` constants so the numbers live in exactly one place) will be passed as
`run(seed, target, params=None)` rather than injected at construction. Three reasons:

- It preserves the split `base.py` already documents — caches are long-lived shared infrastructure
  and belong in `__init__`; the *job* arrives per call, and knobs are part of the job.
- Mutating module globals to honor a user's setting races across concurrent requests (two tabs,
  one stomps the other). Per-run values must travel as arguments; this is the concurrency rule
  already recorded in `LEARN.md`.
- `_algorithm()` is an `@lru_cache(maxsize=1)` singleton. Params in `__init__` would force the
  cache to key on params, building a fresh algorithm per knob combination. Params in `run` leave
  the singleton — and its warm caches — untouched.

`RunParams` will live in `config.py`, not `contracts.py`: contracts promises it "imports nothing
from the rest of the project", and defaults have to come from config.

### Known gap: `MoveEvaluation.from_` does not actually serialize as `from`

Surfaced while walking through `asdict` in the step-5 code review. `contracts.py`'s
`MoveEvaluation` docstring claims: *"When this is serialized for the frontend, that maps back to a
plain `from` key."* **No code does that.** `dataclasses.asdict` copies field names verbatim, so the
JSON is `{"from_": ...}`. Verified by running it.

Harmless right now — step 5 streams `Step` only, and `MoveEvaluation` never crosses the wire. It
becomes real in **step 8** (grading), which is when it must be fixed. Deliberately not fixed now:
there is no consumer to fix it against, and inventing a serializer ahead of `feedback.py` would
guess at a shape step 8 should decide.

Two options when the time comes, preference noted: a small explicit `to_json()` on
`MoveEvaluation` (keeps the rename visible at the call site), rather than
`asdict(ev, dict_factory=...)` (hides it in a callback). The docstring stays as-is because it
describes the *intended* contract; this entry is what records that the implementation hasn't caught
up.

General lesson logged because it will recur: **a docstring is not a test.** This one asserted
behaviour confidently and was wrong from the moment it was written.

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
