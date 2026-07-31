# LEARN.md

Personal learning log for concepts hit while building this project. Not documentation about
the *project* (that's CLAUDE.md/HISTORY.md) — this is documentation about *me*: what's clicked,
what's still shaky, what to revisit. Newest entries at the top of each section.

## Struggling with / still shaky

_(2026-07-23 — flagged these while tired after building step 4; revisit fresh. Plain-English
versions on purpose. Move up to "Refining" once they actually click.)_

_(ABC/`base.py` was here; it clicked on 2026-07-25 — moved down to "Understood".)_

- **What `greedy.py` actually does (in words).** Start at the seed page → look at every page it links
  to → score each by "how related does this feel to the target?" (cosine similarity, higher = closer)
  → keep the best 20 → walk to the single best one I haven't visited → repeat until I hit the target
  or give up. "Greedy" = always grab the best-looking option right now, never backtrack. (Analogy:
  drive toward a mountain by always taking whichever road most points at it.)

- **`yield` / generators — hand back answers one at a time.** A normal function does all its work then
  returns ONE result at the end. `yield` lets a function pause and hand back results one by one
  ("here's step 1"…pause…"here's step 2"…). That's what will let the graph draw *live* on screen later
  instead of freezing until the search finishes. Still shaky — revisit when we wire the server (step 5),
  where each `yield` becomes one thing sent to the browser.

- **The `visited` set — why it's the important line.** `visited` is a bag of "pages I've already been
  to." Greedy checks it before moving. Needed because the page that "feels closest" is often *the page
  I just came from* (related pages score high for each other) — without the bag, greedy bounces between
  two pages forever. This is the one real bug the old repo had.

- **A failing test doesn't always mean the code is broken.** Two of my tests went red first try, but the
  algorithm was FINE — my *tests* were checking the wrong thing (I looked at the last item in a
  score-sorted list, which is the *worst* option, not where greedy actually walked). Fixed the test's
  expectation, not the code. Lesson: when a test fails, look at *why* before assuming the code is wrong.
  - **Happened again on 2026-07-26, same shape, bigger.** Five of the new A* tests failed at once
    against correct code. The helper read "which page did this tick expand?" off
    `step.edges[0].source` — but a page with **no outbound links** expands perfectly normally and
    emits a Step with zero edges, so the helper silently skipped it and the expansion order came out
    short. Fixed the helper (read the note instead), not the algorithm. **Pattern worth naming: when
    several tests fail simultaneously and the code looks right, suspect the thing they all share** —
    here, one helper function. A single broken instrument fails every measurement at once.

## Refining (mostly got it, some edge cases fuzzy)

- **2026-07-23 — Global config value vs per-run parameter: the concurrency line.** Came up planning
  the algorithm-tuning UI. A module-level constant like `config.TOP_K` is a *single shared cell*: if
  code *mutates* it to honor a user's setting, every run reading it sees the last writer's value. With
  one user and no server that's invisible; with a request-handling server, two runs at once (two
  browser tabs) race — tab B's K overwrites tab A's mid-search. The fix is to stop *sharing* the
  value: build a small per-run object from each request and pass it *into* the function
  (`run(seed, target, params)`), so each run carries its own copy and can't be stomped. Rule of thumb
  that landed: **read-only globals are safe to share; the moment a value becomes per-request-variable,
  it has to travel *as an argument*, not as mutable module state.** Still "refining" because I haven't
  hit a concurrency bug in practice yet — holding it as principle. For step 4 we deliberately read
  `config.TOP_K` directly (no server exists to race), and switch to per-run params when the UI lands.
  - **Follow-up (step 6 built, 2026-07-26) — the switch happened, exactly as planned above.**
    `greedy.py` no longer mentions `config` at all; it reads `params.top_k` / `params.max_depth` /
    `params.max_nodes` off a `RunParams` handed to `run()`. What made it click seeing it built: the
    constants didn't go away, they became the *dataclass field defaults*, so the number is still
    written in one place and nothing mutates. And the test that proves the point is
    `test_concurrent_runs_do_not_share_settings` — two requests with `top_k=3` and `top_k=17` reach
    the algorithm as `[3, 17]`, and `config.TOP_K` is still 20 afterwards. **The global was never
    written to; the value travelled.**

- **2026-07-23 — Generators / `yield` = pause-and-resume, the engine behind contract 2.** An
  algorithm's `run` will `yield` one `Step` at a time and *pause*, instead of building a full list
  and `return`ing it. That's what lets the server stream each Step to the browser the instant it's
  produced (live graph building). A returned list would render nothing until the whole search
  finished. New syntax to get hands-on with in step 4; understood in principle, not yet by muscle.
  - **Follow-up (step 4 built):** `GreedyConnect.run` is now a real generator — the tell is that its
    body uses `yield` and never `return`s a value. Things that clicked writing it: (1) a `return`
    inside a generator just *stops* it (ends the stream), it doesn't return data — used exactly that
    to halt on dead-end/cap. (2) Nothing runs until you iterate: `list(algo.run(...))` in the tests is
    what actually drives the search to completion; calling `.run()` alone would just build a paused
    generator object and do zero work. (3) State declared before the loop (`visited`, `current`,
    `depth`) persists *across* yields because the function is paused, not restarted — that persistence
    is what makes the visited set work at all.
  - **Follow-up (step 5 built, 2026-07-25) — this is the payoff the entry above was waiting for.**
    The generator now runs as a *chain*: `GreedyConnect.run` yields a Step → `_stream` yields an SSE
    frame → Starlette writes it to the socket → the browser paints it → and only *then* does the
    search resume for the next tick. Nothing is collected into a list at any layer, which is the
    entire reason the graph grows on screen instead of appearing at the end. Proof it's genuinely
    incremental, not just theoretically so: a cold `Banana → Quantum mechanics` run delivered frames
    at +0.00s, +5.71s, +6.27s, +10.17s. A *warm* run finished in <0.01s and delivered everything at
    once — same code, and it proves nothing about streaming. **Caching can hide the very behaviour
    you're trying to observe; test streaming on cold data.**

- **Dependency injection vs "forced by architecture".** Understood that `LinkCache` receives
  an already-built `WikiClient` instance rather than constructing its own. Initially framed
  this as mandatory for the layering to work — it isn't (nothing stops `LinkCache.__init__`
  from doing `self._client = WikiClient()` itself). It's a deliberate design choice for (a) one
  shared instance across the app instead of redundant ones, and (b) testability — tests hand
  in a `MagicMock()` instead of a real client. Revisit if this comes up again in `server/app.py`
  wiring, where the shared-instance argument will matter more concretely.

## Understood (apprehended, for reference)

- **2026-07-30 — Turn-selection starvation, in ascending levels. Fixed by redesign, not patch.**
  Found live: a real "israel" -> "john f kennedy" search showed the target node sitting completely
  disconnected — forward kept expanding, backward never did, not even once.

  **Level 1 — one sentence.** Forward kept getting picked, tick after tick, because the question
  deciding "whose turn is it" was one forward could barely ever lose.

  **Level 2 — why, with an analogy.** Two tunnel crews digging toward each other, and a foreman who
  decides who digs next by asking "whose current rock sample looks closer to the middle?" Crew B
  hasn't swung a pick yet — their sample is the guess taken before anyone moved, and it never
  updates until crew B is actually picked. Crew A digs, gets a fresh sample every time, and if that
  sample ever looks even slightly decent, they win the next turn too. B isn't losing because they're
  worse — they're losing because the thing being compared only updates for the side already moving.

  **Level 3 — the rule, in this codebase's terms.** `default.py`'s old design ran two searches (one
  from each end) and picked ONE to expand per tick by comparing each side's current best "how
  promising is this" number. Backward's very first number was set once, at the start, and never
  recalculated until backward was actually picked — so if forward kept finding decent candidates,
  forward kept winning, and backward's frozen number just got relatively worse forever.

  **Level 4 — precise mechanics, and the connection to `bfs.py`'s already-learned lesson.** Every
  page carries `g` (real hops so far, exact) and `h` (a *guess* of hops remaining, from cosine
  similarity). `f = g + W*h` is the "total estimated cost." The bug: using `f` — partly a guess — to
  decide *whose turn it is*, instead of `g`, which is exact and directly comparable (both sides
  start at 0). `bfs.py`'s own HISTORY entries already fought this exact bug class twice — comparing
  raw queue length, then whole-frontier size, both proven wrong live — landing on "the only safe
  comparison is depth LEVEL itself." The old `default.py` compared `f`, worse than either of
  `bfs.py`'s two already-rejected attempts, since `f` isn't even monotonic.

  **Level 5 — the fix actually chosen, and why it's stronger than a better comparison.** Proposed by
  the user: don't compare anything — run both sides' *entire* current frontier every tick,
  unconditionally, batch their candidates, prune each side's own top-K. There's no "whose turn"
  question left to get wrong, because there's no turn. This turned out to also delete a whole other
  piece of machinery for free: `astar.py`-style reopening (handling a cheap-looking route that later
  turns out not to be cheapest) needed a persistent priority queue where "later" could mean "a
  lower-cost path found after a higher-cost one already closed." In a design where both sides
  advance exactly one hop, together, every tick, "later" can only ever mean "deeper" — so first
  discovery is already the best any given tick's pruning can produce. **The general lesson: when a
  comparison is fundamentally unfair (one side's number updates, the other's doesn't), the fix
  usually isn't a better comparison — it's checking whether the comparison needs to exist at all.**

  **Where to stop:** Level 3 is enough to understand what a screenshot of this bug looks like.
  Level 4 is enough to reason about why a fix works. Level 5 only if reading/changing the code.

- **2026-07-27 — A broad `except` is fine; a broad *silent* except is not.**
  `WikiClient.get_links` wraps its fetch in `except Exception: return []`. Catching everything is
  correct here — a timeout, a 429 and a malformed payload all mean "retry". The problem is what else
  it catches: **your own bugs.** A typo raising `AttributeError` gets swallowed and returned as `[]`,
  and `[]` is indistinguishable from "this page genuinely has no links". The search then finds
  nothing, and there is no trace of why. Fix wasn't to narrow the catch (the breadth is deliberate)
  but to make it speak: `logger.warning(..., exc_info=True)` before giving up. **Rule: if you swallow
  an exception, leave a receipt.**

- **2026-07-27 — A relative path is resolved against where you *launched*, not where the file lives.**
  `Path("data/links")` looked like "the data folder in this project". It isn't — it means "a folder
  called data/links, starting from whatever directory the process was started in". Launch uvicorn
  from the Desktop and the app cheerfully creates a brand-new empty cache there and re-crawls
  Wikipedia from cold, while the real 165-file cache sits untouched. Nothing errors; it just looks
  inexplicably slow. Fix: anchor to the file itself with `Path(__file__).resolve().parents[3]`.
  **`__file__` is where the code is; the cwd is where the human was standing. For anything the
  program owns — caches, data, bundled assets — you want the former.**

- **2026-07-27 — Count the things, not the sightings.** `max_nodes` is meant to cap how many circles
  land on the canvas. Both algorithms implemented it as `node_count += len(top)` — add the batch size
  each tick. But a page linked from many others appears in many batches, so it got counted many
  times: cap trips early, reported number disagrees with the screen. The fix in greedy is the part
  worth keeping: it now holds **two** sets that are easy to mistake for one.
  - `visited` — pages greedy has *stood on*. Drives the loop guard. One per hop.
  - `seen` — pages that have been *drawn*. Drives `max_nodes`. Twenty-odd per hop.

  They answer different questions, and merging them is precisely what caused the bug. A* needed no
  new state at all, because `len(cost_from_seed)` was already exactly the right number — **when a
  count is drifting from reality, look for an existing collection that already holds the truth
  before adding a counter to maintain by hand.**

- **2026-07-27 — A clamp can make a test lie about what it tests.** Writing the test for the above,
  the first attempt passed `RunParams(max_nodes=5)`. It went green. It was also testing nothing:
  `__post_init__` *clamps* to `MAX_NODES_BOUNDS`, whose floor is 20, so `5` silently became `20` and
  the run hit the **depth** cap instead — a different code path entirely. The safety feature worked
  exactly as designed and quietly invalidated the test. Two things to carry:
  - **Clamping and validating fail differently.** A validator rejects `5` and you find out
    immediately. A clamp accepts it, changes it, and says nothing. Both are legitimate — this project
    uses a validator at the HTTP edge and a clamp internally, on purpose — but when writing a test
    against clamped input, **check your value is actually in bounds** or you're testing a value you
    never chose.
  - The tell was that the test passed on the *first* try against code I'd just changed. That deserved
    suspicion, not relief.

- **2026-07-27 — Prove the test fails, every time, not just when it's convenient.** Both new
  node-count tests were run against the *old* counting logic first and confirmed to fail, then run
  against the fix and confirmed to pass. This is the same habit the vis-network fix established, and
  it is what caught the clamp problem above — the first version of the test passed against the broken
  code too, which is the definition of a test that isn't testing anything.

- **2026-07-26 — One throw in a `<script>` kills every listener below it.** The settings panel broke
  and took the **Run button** down with it, which made no sense until the order was clear. The chain:
  vis-network deleted `#panel` → `getElementById("reset-display")` returned `null` →
  `null.addEventListener(...)` threw → **and module code runs top to bottom, so everything after that
  line never executed** — including `form.addEventListener("submit", ...)` much further down. Two
  things to keep:
  - **A browser script has no error containment.** Unlike Python, where an exception at import time
    is loud and total, a JS `<script>` dies quietly at the failing line and the page *looks* fine.
    Nothing visibly broke; things just didn't respond.
  - **So register listeners in order of importance,** and make optional lookups non-fatal. The fix
    was a `bind(id, event, handler)` helper that logs an error and returns when the element is
    missing, plus moving all settings-panel wiring to the very bottom of the file. The product's
    listeners get attached before anything that might fail.

- **2026-07-26 — A library handed a DOM element may OWN it.** `new vis.Network(container, ...)`
  doesn't just draw into `#graph` — reading the bundle, `Canvas._create()` starts with
  `for (; container.hasChildNodes(); ) container.removeChild(container.firstChild)`. It **empties the
  container first.** So putting the settings panel inside `#graph` — which looked completely
  reasonable — deleted the panel on page load. Fix: `#panel` is a *sibling* of `#graph`, both inside
  a positioned `#canvas` wrapper, so it can still float over the graph. **Question to ask before
  putting anything inside an element you've handed to a library: does this library consider the
  container its own?** Related habit that paid off: I found the answer by *downloading the library
  and grepping it*, not by guessing — the behaviour is real and documented nowhere obvious.

- **2026-07-26 — A test that cannot fail is decoration.** After fixing the above I wrote a regression
  test asserting `#panel` isn't nested inside `#graph`. Then I ran the check against the *broken*
  markup to confirm it actually reported a failure, and against the fixed markup to confirm it
  didn't. Worth doing every time a test is written for a bug that already happened: **prove the test
  would have caught it.** Otherwise you've added confidence without adding coverage.

- **2026-07-26 — "Config owns every knob" has a boundary: search knobs vs display knobs.**
  Adding the Obsidian-style graph panel raised a question contract 1 seemed to have already answered:
  do node size and physics forces belong in `config.py` like `TOP_K` does? **No** — and working out
  why sharpened what contract 1 is actually for. The test: **can this setting change what the
  algorithm does?** `TOP_K` changes which pages get searched. A spring constant changes where a dot
  sits on screen and *cannot reach the algorithm at all*. So:
  - Contract 1 exists so **algorithms** don't hardcode **their** settings. Its examples are all
    search knobs; a render setting was never in scope.
  - Putting them in `/api/config` would give the **server an opinion about drawing** — which is
    contract 2 ("algorithms never draw") violated from the other direction. The backend not knowing
    the renderer exists has to cut both ways.
  - They're per-person preferences, so `localStorage` is their natural home, and the server can't
    own that anyway.
  **Rule kept: changes the SEARCH → `config.py`; changes the PICTURE → frontend.** General lesson
  worth more than this instance: *"everything in one place" rules always have a scope, and finding
  the boundary means asking what the rule was protecting against, not applying it literally.*

- **2026-07-26 — Data-driven UI: name a convention once instead of listing controls twice.**
  Ten display controls could each have been wired by hand (`document.getElementById("d-nodeSize")`,
  read it, apply it — ten times, in three places each). Instead every control carries a
  `data-display` attribute and an id of `d-<key>`, and the JS does:
  ```js
  const displayInputs = [...document.querySelectorAll("[data-display]")];
  const key = el.id.slice(2);          // "d-nodeSize" -> "nodeSize"
  ```
  So **adding a control means adding HTML and nothing else** — no second registration list to forget.
  Same instinct as `LinkCache._lookup` taking the fetch function instead of a direction flag, and as
  `/api/config` publishing bounds so the frontend never hardcodes a range: *when the same fact would
  otherwise be written in two places, find the convention that lets it be written once.*
  Two details that made it work: `[...querySelectorAll(...)]` spreads a NodeList into a real array
  (NodeList has `forEach` but not `map`/`filter`), and reading defaults from the HTML **before**
  loading `localStorage` is what makes a "Reset" button possible — the markup is the record of what
  default meant.

- **2026-07-26 — A*, in ascending levels. Level 1: it's greedy that also counts its steps.**
  Greedy asks one question — *which neighbour looks closest to the target?* A* asks a second —
  *and how far have I already walked?* **Level 2 — why that matters:** greedy will cheerfully take
  ten downhill hops and never notice the count. A* orders its options by the sum of both, so a
  brilliant-looking page five hops deep can lose to a decent page one hop deep. **Level 3 — the
  formula.** `f = g + W*h`, where `g` = hops already walked (known exactly) and `h` = hops estimated
  remaining (a guess). Lowest `f` gets expanded next. **Level 4 — THE trap, and the thing I'd have
  got wrong:** `g` is a hop count (1, 2, 3) and cosine similarity is a number in [0, 1]. **Adding
  them directly is meaningless** — the heuristic could never outweigh even a single hop, so A* would
  silently behave like breadth-first search and I'd have spent a day wondering why the heuristic
  "wasn't working". Cosine must be converted into hops first:
  `h = hop_scale * (1 - cosine)`, `hop_scale ≈ 4` because published measurements put arbitrary
  Wikipedia articles ~3.4–3.9 clicks apart. **The general rule: before adding two numbers, check
  they're the same kind of thing.** **Level 5 — what the weight `W` does**, confirmed by running it:
  ```
  W=0     f = 0.00, 1.00, 1.00, 1.00    <- f is literally just g. Breadth-first.
  W=25    f = 79.91, 55.02, 55.57       <- g is noise next to h. Greedy.
  ```
  So **one algorithm plus one slider contains both greedy and BFS as its endpoints** — which is why
  it was worth building A* before writing a separate BFS. **Level 6 — the honesty caveat.** Textbook
  A* is guaranteed to find the *shortest* path only if `h` never overestimates ("admissible").
  Cosine is a vibe, not a bound, so **this A* has no such guarantee** — and it demonstrably lost:
  it returned a 3-hop `Cat → Astronomy` route while a 2-hop one (`Cat → Night vision → Astronomy`)
  existed. ~~Not a bug — the accepted cost of decision B.~~ The lesson to keep: **a famous algorithm's
  guarantees come with preconditions, and using the name doesn't buy the guarantee.**

  **Correction, 2026-07-29 — that was too hasty.** "Cosine is inadmissible" was true but incomplete;
  it hid a second, *separate*, fixable bug riding along with it. **Level 7 — admissible vs.
  consistent, the distinction I'd conflated.** *Admissible* means `h` never overestimates the true
  remaining cost. *Consistent* is stricter: `h` also can't drop by more than one hop per hop walked
  (the triangle inequality, one hop at a time). Textbook A* is allowed to close a node forever the
  first time it's popped **only because a consistent heuristic proves that first pop already found
  that node's cheapest cost.** Cosine has neither property — but the old code closed nodes forever
  *anyway*, as if it did. That's not "the heuristic is a guess" — that's a stale invariant borrowed
  from a precondition the code never checked. **The concrete failure this caused:** a page reachable
  both via a route that merely *looks* cheap (low `h`) and, later, via a route that's genuinely
  fewer hops, would close on the first (worse) route, and the second (better) discovery was thrown
  away by `if link in expanded: continue` with no further thought. **The fix — reopening:** when a
  strictly cheaper route to an already-closed page turns up, un-close it (`expanded.discard(link)`)
  so it gets re-expanded from the better cost. Bounded, because costs only ever move down and are
  small integers. **What's still true after the fix:** the run still stops at the first pop of the
  *target itself*, and nothing proves that's the true minimum without an admissible heuristic or
  exhaustive search (`bfs.py`'s job) — so "NOT OPTIMAL" stays correct, just for a narrower, honest
  reason than before. **The general lesson, sharpened:** when a textbook algorithm's precondition
  doesn't hold, check which of its *behaviors* were relying on that precondition — some may be
  fixable (reopening) even though the headline guarantee (optimality) isn't fully recoverable.

- **2026-07-26 — `heapq` = "always hand me the smallest thing next".**
  A* needs to expand the frontier page with the lowest `f`. Re-sorting a list every tick would be
  wasteful; `heapq` keeps a list *partially* ordered so `heappush`/`heappop` are cheap and pop always
  returns the minimum. Two practical things learned using it:
  - **You push tuples, and it compares them left to right.** `(f, tiebreak, title)` — so equal `f`
    values fall through to the second element. That's why the code carries an `itertools.count()`:
    without it, ties would be broken by comparing *titles* (alphabetical, arbitrary), and if the
    third element were ever a dict it would crash outright. A monotonic counter makes ties FIFO and
    deterministic.
  - **You can't update an entry's priority.** The standard workaround, used here: push a *new* entry
    when a better route is found and ignore stale pops via `if current in expanded: continue`. So the
    heap can hold the same page several times, and that's normal, not a leak.

- **2026-07-26 — The mutable default argument trap (why `params=None` and not `params=RunParams()`).**
  `def run(self, seed, target, params=None)` then `if params is None: params = RunParams()`. Looks
  like a pointless extra line — it isn't. **A default argument's value is created ONCE, when the
  `def` line runs, and every call that doesn't pass one shares that same object.** Write
  `def run(..., params=RunParams())` and there is exactly one RunParams for the life of the program.
  Frozen dataclasses make that survivable today; the classic disaster version is `def f(items=[])`,
  where every call appends to the *same* list and results bleed between calls. The `None` sentinel is
  the standard fix and worth doing reflexively, before anything mutable shows up. Same family of bug
  as the `config.TOP_K` mutation problem — **one shared object where you meant one per run.**

- **2026-07-26 — Writing to a frozen dataclass, legally: `object.__setattr__` in `__post_init__`.**
  `RunParams` is `frozen=True`, so `params.top_k = 5` raises `FrozenInstanceError`. But it still
  needs to clamp its own values on construction. `__post_init__` is a hook the dataclass calls at
  the end of `__init__`, and inside it:
  ```python
  object.__setattr__(self, "top_k", _clamp(self.top_k, TOP_K_BOUNDS))
  ```
  This reaches past the frozen machinery to the raw attribute set. **Legitimate here specifically
  because it runs during construction** — nobody can observe the unclamped value, so the object is
  still immutable from every outside perspective. Anywhere else it would be defeating the point.
  Why bother clamping at all when the server already returns 422 for out-of-range input: the 422
  only protects *HTTP* callers. Any Python code could write `RunParams(top_k=999)` and blow past
  decision C's locked ceiling. **An invariant enforced only by a docstring is not enforced** — the
  lesson from the `from_` gap the day before, applied.

- **2026-07-26 — Passing a *function* as an argument (`Callable`), and why it beat a flag.**
  `LinkCache` now caches two things — outbound links and backlinks — which are the *same* lookup
  (memory → disk → network) over different data. Three ways to avoid writing it twice:
  (1) copy-paste, (2) `_lookup(title, direction="backward")` and branch inside on the flag,
  (3) hand `_lookup` the fetch function itself. Took option 3:
  ```python
  return self._lookup(title, self._memory, self._data_dir, self._client.get_links)
  #                                                        ^ no (), not being called here
  ```
  **The key idea: a function is a value.** `self._client.get_links` without parentheses doesn't call
  anything — it hands over the function itself, to be called later inside `_lookup` as `fetch(title)`.
  Same idea as decorators (`@lru_cache` receives the function below it) and as `key=lambda pair:
  pair[1]` in greedy's `sorted` — I'd already used it twice without naming it. Why it beats the flag:
  with a flag, `_lookup` has to *know* every direction that exists and grow an `if` per case; passing
  the function in means `_lookup` never learns there are directions at all. `Callable[[str],
  list[str]]` is the type annotation — "something callable that takes a str and returns a list of
  str".

- **2026-07-26 — A cache key must encode everything that changes the answer.**
  Came up planning richer embeddings (title + summary instead of bare title). The plan looked
  harmless until the cache key got checked: `EmbeddingCache._path_for` keys on **the title alone**,
  and `data/embeddings/` already holds **9,616** bare-title vectors. Change what `embed(title)`
  *means* without changing the key, and every one of those files silently becomes a wrong answer to
  a question nobody re-asked — no error, no crash, just quietly worse results forever. **The rule:
  if two different computations can produce different answers for the same key, the key is
  incomplete.** The fix is a separate namespace (`title__rich.json`), not a smarter lookup. Same
  trap avoided deliberately in `LinkCache`: links and backlinks are both "a list of titles related
  to X", so they get separate *directories* — sharing one would return backlinks where links were
  asked for, plausibly enough that nothing would ever look wrong.
  - **Companion idea — don't mix representations inside one comparison.** Text length shifts a
    sentence-transformer's output, so a "title + summary" vector and a bare-title vector aren't
    directly comparable. Enriching *only the anchor* (the target) is safe because ranking cares
    about relative order and a fixed anchor shifts every candidate equally; enriching *some*
    candidates and not others would corrupt the ranking invisibly. Cost decides the split anyway:
    ~500 candidates per expansion can't each afford a summary fetch, but one target can.

- **2026-07-26 — Read the library's source before trusting its API.** `wikipediaapi` has a
  `page.backlinks` property, which looked like exactly what bidirectional search needed. Reading
  the source showed it paginates to exhaustion (`while "continue" in raw`, no cap — "Cat" is six
  figures of backlinks) and rebuilds continuation requests from the *original* params, silently
  dropping a `blnamespace=0` filter after the first page. Neither is in the docstring; both would
  have shown up as "why is this hanging" and "why are there Category: pages in my results" much
  later. **An attribute existing is not the same as it being usable at your scale** — and the two
  failure modes here (unbounded work, silently dropped filter) are worth recognising generally.

- **2026-07-26 — `asdict` = "turn a dataclass into a plain dict", and it goes all the way down.**
  **Level 1:** `asdict(step)` turns `Step(nodes=[...], note='...')` into
  `{'nodes': [...], 'note': '...'}`. **Level 2 — why I need it at all:** `json.dumps` only knows
  dict/list/str/int/float/bool/None. Hand it a `Step` and it refuses outright —
  `TypeError: Object of type Step is not JSON serializable`. It has no idea what a `Step` is;
  `asdict` translates into vocabulary it speaks. That's the entire reason `app.py` says
  `yield _sse("step", asdict(step))`. **Level 3 — the part that matters: it recurses.** My `Step`
  isn't flat, it *contains* lists of other dataclasses (`Node`, `Edge`). `asdict` walks into those
  lists and converts them too — proved it: `type(d["nodes"][0])` comes back `dict`, not `Node`.
  Without recursion I'd get `{'nodes': [Node(...), Node(...)]}`, outer layer converted and inner
  objects still unserializable, and I'd be hand-writing the walk. One call does the whole
  translation from typed contract to browser-parseable JSON. **Level 4 — what it does NOT do:** it
  only converts *dataclasses*; everything else passes through untouched. Demoed with numpy —
  `asdict` handed back an `ndarray` and `json.dumps` still failed. Relevant here because embeddings
  *are* numpy arrays; if a contract ever holds one directly, `asdict` won't save me (need
  `.tolist()`, exactly what `EmbeddingCache` already does writing to disk). Contrast: `Grade`
  serializes to a clean `"Best"` — but that's the `str` mixin on the enum doing the work, not
  `asdict`, which merely passed the value along. **Level 5 — two gotchas:** it's a *deep copy*
  (mutating the result never touches the original `Step`), and it's recursion so it costs — 41
  objects walked per tick here (20 nodes + 20 edges + the Step), trivial now, worth remembering if
  a Step ever carries thousands.
  - **A real bug this surfaced:** `contracts.py` says `from_` "maps back to a plain `from` key" when
    serialized. **It doesn't** — `asdict` copies field names literally, so the output is `"from_"`,
    and nothing anywhere performs that rename. The docstring describes an intention that was never
    implemented. Harmless today (step 5 only streams `Step`), real in step 8 when grades reach the
    UI. Lesson worth more than the fact: **a docstring is not a test.** It asserted behaviour
    confidently and was wrong for weeks; only running the code showed it.

- **2026-07-26 — `@lru_cache(maxsize=N)` = "remember what you already worked out."**
  **Level 1:** stick it above a function and the function's body runs *once* per distinct set of
  arguments; every repeat call gets the remembered answer back without running anything. **Level 2 —
  what it actually is:** a dict living beside the function, keyed by the arguments, holding the
  return value. Call → look up the key → hit means skip the work entirely. Nothing cleverer than
  that. **Level 3 — what `maxsize` means:** how many *argument combinations* to keep. Rolled my own
  version with a printable notebook to see it: `maxsize=2`, then `square(3)` MISS, `square(4)` MISS,
  `square(3)` HIT, `square(5)` MISS → notebook full → **evicts `square(4)`**, the one gone longest
  without use. That's the whole of "LRU" = *least recently used* — the eviction rule, nothing more.
  `.cache_info()` prints hits/misses/currsize for free. **Level 4 — why `maxsize=1` on
  `_algorithm()`:** it takes **no arguments**, so there's only ever one possible key and one possible
  answer. Size 1 isn't a tuning choice, it's the honest size. The effect is a **lazy singleton**:
  first request builds `GreedyConnect(LinkCache(...), EmbeddingCache(...))`, every later request gets
  the *same object* — verified with `x is y is z` → `True`. That sameness is the entire point; a new
  `LinkCache` per request would mean an empty cache per request. **Level 5 — it's the same idea I
  already wrote by hand**: `Embedder._get_model`'s `if self._model is None: ...` guard is memoization
  spelled out longhand. `lru_cache` is that pattern as a decorator. Rule for choosing: hand-write the
  guard when the thing lives on an instance (`self._model`), reach for `lru_cache` when it's a
  module-level function.
  - **Correction I needed:** I assumed `lru_cache` had something to do with `_stream` yielding. It
    doesn't — **zero connection.** `lru_cache` is on `_algorithm()`, which returns an object and has
    no `yield` in it. Caching is about *not repeating work*; `yield` is about *handing back results
    one at a time*. They sit next to each other in `app.py` and are completely independent ideas.
    (Genuine hazard for later: `@lru_cache` on a *generator* function is a trap — it caches the
    generator object, and a generator can only be consumed once, so the second caller gets an
    exhausted one. Not a problem here; would be if I ever decorated `run`.)

- **2026-07-26 — One shared algorithm object is safe *because* its state lives in locals.**
  Follows straight from the `lru_cache` entry: every request shares one `GreedyConnect` instance, so
  why don't two browser tabs corrupt each other's search? Because `run` keeps `visited`, `current`,
  `depth`, `node_count` as **local variables inside the function**, not as `self._visited` etc. Each
  call to `run(...)` creates a fresh generator with its own private set of locals; two concurrent
  runs are two separate frames that cannot see each other. Had greedy stashed `self.visited` instead,
  tab B would wipe tab A's visited set mid-search. **The rule:** an object shared across requests may
  hold *immutable/shared infrastructure* (the caches — sharing those is the whole point) but must not
  hold *per-run mutable state*. Same principle as the config entry above (read-only globals are safe
  to share; per-request-variable values must travel as arguments) — arrived at from the opposite
  direction.

- **2026-07-25 — SSE is a text format, not a library. Level 1: it's an HTTP response that never
  ends.** Normal request/response = browser asks, server answers once, connection closes. SSE = the
  server keeps the connection open and dribbles messages down it until it's done. **Level 2 — the
  entire wire format** is three lines per message, and the *blank line is the protocol*:
  ```
  event: step
  data: {"nodes": [...], "edges": [...], "note": "..."}
              <- this blank line is what says "message over, deliver it"
  ```
  Omit the trailing `\n\n` and the browser sits waiting for a message it already has. **Level 3 —
  the browser side is one built-in object**: `new EventSource(url)`, then
  `.addEventListener("step", ...)` per event name — which is *why* the server bothers writing the
  `event:` line, since without it everything arrives as generic `"message"`. **Level 4 — why not
  WebSockets** (the locked stack decision): SSE is one-way and that's all Connect needs — the server
  pushes Steps, the browser never replies mid-run. SSE is plain HTTP with auto-reconnect built in;
  WebSockets buy bidirectionality we don't use. Gotcha worth remembering: that auto-reconnect will
  silently *re-run the whole search* on a dropped connection unless you `.close()` the source.

- **2026-07-25 — Sync vs async generator: which one blocks the server.** Wrote `_stream` as a plain
  `def` (not `async def`) on purpose. If a route is `async` and its body does something *blocking*
  (our Wikipedia fetch, the model forward pass), it freezes the whole event loop — one search would
  make the entire server unresponsive to everyone. Handing Starlette a **sync** iterator makes it
  run the iteration in a background threadpool instead, which is the right home for blocking work.
  Rule of thumb: **`async` is only a win when the work actually awaits (real async I/O); wrapping
  blocking code in `async` makes it worse, not better.** Our fetch layer is deliberately synchronous
  (CLAUDE.md), so sync generator is the honest choice — revisit if we ever move to async httpx.

- **2026-07-25 — Testing with fakes proves wiring; only a live run proves it works.** The 8 server
  tests all passed while the app had never once talked to Wikipedia — they substitute a fake
  algorithm, so they prove the *plumbing* (routes exist, one SSE frame per Step, errors arrive
  in-band) and nothing about whether a real search succeeds. Both kinds matter and neither replaces
  the other: the fakes stay fast and run every time; the live run is what turns "green" into
  "working". Related trap from the same session: **a warm cache can hide the behaviour you're
  testing** (see the generators follow-up above).

- **2026-07-25 — ABCs, finally. Written in ascending levels because that's what made it land.**
  (Replaces the earlier ABC notes, which were technically right but started at the wrong altitude —
  see also the "ascending levels" teaching rule now in CLAUDE.md.)

  **Level 1 — one sentence.** `class ConnectAlgorithm(ABC):` means **you can't make one of these.**
  `ConnectAlgorithm(link_cache, embed_cache)` → `TypeError`, always. `GreedyConnect(...)` → fine.
  That's the whole feature: `(ABC)` makes the class unbuildable.

  **Level 2 — why want that?** Because `ConnectAlgorithm` *isn't a thing, it's a category*. You don't
  own "a vehicle" — you own a car or a bike. There's no "Connect algorithm" running a search; there's
  greedy, or A*, or BFS. `(ABC)` tells Python "this is a category name, don't let anyone build one."

  **Level 3 — what it buys me.** A category is only useful if everything in it behaves the same, so
  the base doubles as a **checklist**: "to count as a Connect algorithm you must have
  `run(seed, target)`." `@abstractmethod` writes one checklist item. Forget `run` in a new algorithm
  and Python refuses to build it — I find out immediately, not mid-search.

  **Level 4 — the exact rule.** Two pieces, two jobs: `@abstractmethod` **marks a blank**; `(ABC)`
  **turns on the inspector**. Rule: *Python refuses to create an object from any class that still has
  an unfilled blank.* Consequences that matter:
  - The blocker is `@abstractmethod`, **not `ABC`**. A class inheriting `ABC` with zero abstract
    methods instantiates perfectly fine. `ABC` only makes the decorator mean something.
  - It blocks **existence, not arguments** — the base refuses even when called with no arguments at
    all. Two different `TypeError`s to keep apart: "Can't instantiate abstract class…" (unfilled
    blank) vs "missing 1 required positional argument" (wrong args).
  - The base's **non-abstract code is fully alive.** `__init__` has no decorator, so `GreedyConnect`
    — which defines no `__init__` of its own — inherits it and gets the cache-storing free. That's
    why greedy can use `self._link_cache` without ever assigning it. An ABC is **mostly real code
    with one hole punched in it**, not "everything blank."
  - "Abstract" means **unfinished, not inaccessible**. Nothing is hidden or restricted — a subclass
    can even call `super().run()` into the abstract body. Access in Python is the underscore
    convention (`_link_cache`), a completely separate idea.
  - Algorithms are **sibling subclasses**, not stacked wrappers — they *replace* each other's `run`.
    Base *declares*, subclass *does*.

  **Level 5 — where it pays off (step 5).** The server will hold *some* algorithm and call
  `.run(seed, target)` without knowing which. `(ABC)` is the guarantee that call won't blow up, so
  dropping in A* later changes zero server code. `isinstance(greedy_instance, ConnectAlgorithm)` is
  `True` — a `GreedyConnect` genuinely *is* a `ConnectAlgorithm`.

  **Level 6 — internals (trivia; safe to ignore).** `@abstractmethod` is two lines in `Lib/abc.py`:
  it sets `funcobj.__isabstractmethod__ = True` and returns the function unchanged. Just a flag on
  an attribute — no magic, no reserved syntax. `ABC` swaps the class's *metaclass* to `ABCMeta`,
  whose `__new__` runs **when the class is defined** (not when instantiated), scanning every name in
  the class body with `getattr(value, "__isabstractmethod__", False)` and freezing the hits into
  `cls.__abstractmethods__`. Mine: `ConnectAlgorithm` → `{'run'}`, `GreedyConnect` → `set()`.
  Instantiation is then just "is that set empty?" **Two moments: scan at class-definition time,
  check at object-creation time.** Level 3 is enough to read and write every algorithm here.

  **Level 4b — which way inheritance runs (I had this backwards).** I called `GreedyConnect` the
  *parent*. It's the **child**. The rule: **whatever sits in the parentheses is the parent.**
  ```python
  class ConnectAlgorithm(ABC):            # ABC is the parent
  class GreedyConnect(ConnectAlgorithm):  # ConnectAlgorithm is the parent
  ```
  Chain (`GreedyConnect.__mro__`): `GreedyConnect` → `ConnectAlgorithm` → `ABC` → `object`. Left to
  right = child to ancestor. Why it matters beyond vocabulary: **inheritance flows downhill** — the
  child receives from the parent, never the reverse. That's how `GreedyConnect` gets a working
  `__init__` it never wrote; hold the direction backwards and that looks impossible. Sanity check:
  **the child is the more specific thing** ("greedy Connect" is a kind of "Connect algorithm"), so
  specific inherits from general. Vocabulary: *parent = base class = superclass* (`ConnectAlgorithm`);
  *child = subclass = derived class* (`GreedyConnect`); *siblings* = `GreedyConnect` and
  `AStarConnect` — same parent, no relationship to each other. Also: the decorator is
  `@abstractmethod`, there is no `@abstractclass` — it marks one *method*, and the class becomes
  abstract as a consequence of containing one.

  **Related syntax in `base.py`, not ABC-specific:**
  - `if TYPE_CHECKING:` = "read these imports for labels only, never actually run them" — avoids
    dragging in wikipediaapi or a model load just to *name* a type in an annotation.
  - The abstract body is `...`, deliberately **not** `yield`: a `yield` anywhere in a function body
    makes the whole thing a real (do-nothing) generator. `...` keeps it an empty declaration.
    Python needs *some* body — an empty one is a syntax error — and `...` is the idiom for
    "intentionally blank."
  - `@decorator` syntax is a **general Python mechanism**, not an ABC thing: a function that takes
    the function below it and does something with it. Meeting it again in step 5 — FastAPI's
    `@app.get("/connect")` registers the function under it as a URL route. Same syntax, same idea.

- **2026-07-25 — Two different modules both named "abc"; don't conflate them.** `base.py` imports
  from both on adjacent lines: `from abc import ABC, abstractmethod` and `from collections.abc import
  Iterator`. They are NOT the same module. **`abc`** = the *machinery* for building abstract classes
  (`ABC`, `@abstractmethod`) — the tools we use to declare `ConnectAlgorithm`. **`collections.abc`** =
  a *collection* of ready-made abstract base classes describing container behaviors (`Iterator`,
  `Iterable`, `Mapping`, `Sequence`, `Callable`, …) — the standard library already used the `abc`
  machinery to define types for the common container shapes. Same three letters, same underlying idea,
  different files: on disk they're `Lib/abc.py` and `Lib/_collections_abc.py`, both shipped with Python
  (stdlib, nothing to install). My code only uses `collections.abc.Iterator` in *type annotations* —
  `run(...) -> Iterator[Step]` = "calling this hands back something you can loop over, each item a
  `Step`." So the two abcs do complementary jobs: `abc` *enforces* that subclasses provide `run`;
  `collections.abc` *describes* what `run` returns. (Historical note so old tutorials don't confuse me:
  `from typing import Iterator` is the deprecated old spelling — since 3.9 import these from
  `collections.abc` directly; `typing`'s versions are now just aliases pointing back to the same
  classes.)

- **2026-07-23 — The three-way split: ABC *declares*, subclass *does*, config *configures*.**
  Where step 4's pieces live, and why they're separate: `algorithms/base.py` (ABC) declares the
  *shape* (`run() -> Iterator[Step]`); `algorithms/connect/greedy.py` (subclass) holds the *actual
  loop*; and the *knobs* (`TOP_K=20`, `MAX_DEPTH`, `MAX_NODES`) live in neither class — they sit in
  **`config.py`** as plain data, and the subclass *reads* them (`config.TOP_K`). That's contract 1
  ("config owns every knob; algorithms never hardcode"). Two reasons the knobs aren't baked into
  greedy: (1) Explore mode's whole purpose is turning those dials live — a hardcoded `TOP_K` can't
  become a UI slider; (2) `astar` reads the *same* `TOP_K` from the *same* place — the cap is a
  property of the project, not one algorithm. So behavior lives in the class, numbers live in
  config, shape lives in the ABC — three separate things, on purpose.

- **2026-07-23 — networkx stores structure only; it knows nothing about meaning or pixels.**
  A networkx node = an identity (the page title) + a plain attribute dict hanging off it (a
  "sticky note"). In `add_node(node.id, score=..., depth=...)`, `score`/`depth` are arbitrary key
  names *we* invented — networkx never inspects or interprets them; rename `score` to `banana` and
  it behaves identically. The *meaning* ("score = cosine similarity to the anchor") lives only in
  our code, never in the library. Corollary that had to be un-learned: networkx does NOT "graph
  using score," and stores zero visual info — no x/y, no positions. Layout is a *separate* concern:
  in this project vis-network runs a force-directed physics sim in the browser (structure ships
  over SSE as pure data). The universal thing is the *mechanism* (every node gets a generic dict
  you can stuff any keys into); the keys and their meaning are project-specific. Clean split:
  library holds arbitrary data, app assigns meaning. Same contract-2 spirit — `WikiGraph` couldn't
  name a single pixel and that's correct.

- **2026-07-23 — Edges auto-create their endpoints (blank), so `apply` adds nodes first.**
  In networkx `add_edge("A", "B")` does NOT require A/B to pre-exist — it helpfully springs them
  into being if missing, but with an *empty* attribute dict (no score/depth). That over-eagerness,
  not a hard requirement, is the hazard. If edges ran before nodes, an edge pointing at a node the
  Step didn't explicitly declare would leave a "ghost" node — present in the graph but `node_attrs`
  returns `{}`. Adding all declared nodes first guarantees every node is born with its real
  attributes rather than being conjured blank by an edge that raced ahead. The danger reversed-order
  creates is a *blank node*, not a failed edge (the edge always succeeds).

- **2026-07-23 — Move grading is arithmetic on ONE cosine axis.** The whole scoring scheme
  (decision B, built in step 8) runs on a single number line: each page's position =
  `cosine_similarity(embed(page), embed(target))` (its "eval" — warmer = closer to target).
  From that: `your_delta` = how far your move moved you along the axis, `best_delta` = how far
  the best available neighbor would have, `regret = best_delta - your_delta`. Five of the six
  grades (Best/Good/Inaccuracy/Mistake/Blunder) are just *bands of regret* — one computation,
  memoryless, no move history. There is no separate metric per grade; it's one instrument
  (cosine similarity) read multiple times. Only **Brilliant** breaks the pattern: it needs the
  regret ≈ 0 (was best) AND a second test on a *different* axis — `cosine_similarity(link,
  from_page)` low, i.e. "looked unrelated on the surface but paid off." That's why Brilliant
  isn't forced through the same formula. `feedback.py` (contract 3) is where this messy
  special-casing is allowed to live; downstream only ever sees the six-value `Grade` enum.

- **2026-07-23 — Lazy load + memoization guard (`Embedder._get_model`).** Three-stage lifecycle
  for an expensive resource: `__init__` only *names* it (stores the model-name string, sets
  `self._model = None` — loads nothing); `_get_model` *builds* it, but guarded by
  `if self._model is None:` so the ~80MB `SentenceTransformer(...)` construction happens exactly
  once and every later call reuses the cached object; `embed()` *uses* it. The guard is
  memoization ("build once, remember, reuse"), NOT hardcoding. Loading lazily (in `_get_model`,
  with the import inside it too) rather than eagerly in `__init__` is what keeps merely importing
  `embed.py` — or running the fast test suite — from triggering the model download. Same
  single-front-door spirit as `WikiClient` for `wikipediaapi` (see wrapper-layering below).

- **2026-07-23 — A public method calling a private one is just ordinary composition.** Calling
  `embedder.embed(title)` transitively runs `self._get_model()` because `embed`'s body calls it —
  not because of any injection or special resolution. `_get_model` isn't a "dependency" wired in
  from outside; it's a plain method call on the same instance, the leading underscore only marking
  it as internal plumbing `embed()` is built on top of. Outside code calls `embed()`; `_get_model`
  is implementation detail. (Reinforces the underscore-is-convention item below.)

- **2026-07-21 — Classes are toolboxes, not top-down scripts.** Long-standing mental block:
  expected data to "enter" a class and something to happen automatically, like a script running
  top to bottom. Correct model: a class body defines methods (tools on a shelf) but nothing
  executes until something *outside* the class calls `instance.method(...)`. Execution only
  starts at the call site, not at class definition. This reframe ("we're just using tools
  defined within them, not stuff entering the class") is the one to keep coming back to as the
  project adds more classes (algorithms, feedback grader, server routes).

- **2026-07-21 — `self` is "whichever instance is currently running this method".** A class is
  a blueprint; `client = WikiClient()` builds one real instance in memory. Inside any method,
  `self` refers to that specific instance — not a global, not the class itself. Two instances
  (`WikiClient()` vs `WikiClient(language="fr")`) each get their own separate attributes
  (`self._wiki`, etc.) from separate `__init__` runs, even with identical arguments.

- **2026-07-21 — Leading underscore vs dot are two different things.** The dot (`self._wiki`)
  is just attribute access — required syntax, "reach into this object." The underscore prefix
  is a naming *convention* (not enforced by Python) signaling "internal, don't touch from
  outside the class." They got conflated at first as one idea; they're orthogonal.

- **2026-07-21 — Wrapper/shell layering (`LinkCache` → `WikiClient` → `wikipediaapi.Wikipedia`).**
  Each layer only knows about the one directly inside it, never the reverse. `LinkCache` checks
  memory, then disk, and only calls inward to `self._client.get_links(...)` (a `WikiClient`
  instance) as a last resort; `WikiClient` is the only thing that ever imports `wikipediaapi`
  directly, per the CLAUDE.md rule ("nothing else in the codebase talks to Wikipedia directly").
  Swapping the underlying library later only touches `client.py`.

- **2026-07-21 — `p.ns == 0` costs no extra API call.** `page.links` returns
  `{title: WikipediaPage}` in a single HTTP request, and each `WikipediaPage` object already
  has `.ns` (namespace) populated as part of that same response. Filtering on `p.ns == 0` reads
  metadata that already arrived, rather than requiring one lookup per linked page. `ns == 0`
  means "real article" (as opposed to `14` = Category, `1` = Talk, etc.) — this replaces the old
  repo's buggy `if ':' not in title` heuristic, which dropped real articles like
  "Aliens: The Ride".
