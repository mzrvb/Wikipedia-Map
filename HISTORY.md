# HISTORY

Running log of significant changes and the reasoning behind them.

**What belongs here:** decisions and their rationale, architecture changes, reversals,
roadmap step completions, anything a future session would misread the repo without.
**What does not:** routine edits, typo fixes, anything `git log` already tells you.
This file explains *why*; git explains *what*. Newest entries at the top.

---

## Picking up where 2026-07-28 left off

**State: everything green and working.** 90 fast tests pass, `ruff check` clean, no empty files.
Run `uvicorn wikimap.server.app:app --reload` and open <http://127.0.0.1:8000>.

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
