# LEARN.md

Personal learning log for concepts hit while building this project. Not documentation about
the *project* (that's CLAUDE.md/HISTORY.md) — this is documentation about *me*: what's clicked,
what's still shaky, what to revisit. Newest entries at the top of each section.

## Struggling with / still shaky

(nothing currently — move items here as they come up)

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

- **2026-07-23 — ABC (abstract base class) = a declared shape, not runnable code.** Introduced
  while planning step 4; not yet written in code, so revisit once `algorithms/base.py` exists.
  `base.py`'s `ConnectAlgorithm(ABC)` will define `run(seed, target)` with `@abstractmethod` and
  an empty body (`...`). Key points that landed: (1) the ABC *executes nothing* — it's a promise
  that every subclass provides its own `run`; (2) `@abstractmethod` makes Python forbid
  instantiating the base directly and forces subclasses to implement `run`; (3) algorithms are
  **sibling subclasses** (`GreedyConnect`, `AStarConnect`, `BFSConnect`), NOT stacked wrappers —
  they *replace* each other's `run`, they don't wrap. The server picks *which subclass to build*.
  Corrected mental model: not "layer 1 runs, layer 2 wraps" — it's "base *declares*, subclass
  *does*." Still shaky because I haven't written or subclassed an ABC by hand yet.

- **2026-07-23 — Generators / `yield` = pause-and-resume, the engine behind contract 2.** An
  algorithm's `run` will `yield` one `Step` at a time and *pause*, instead of building a full list
  and `return`ing it. That's what lets the server stream each Step to the browser the instant it's
  produced (live graph building). A returned list would render nothing until the whole search
  finished. New syntax to get hands-on with in step 4; understood in principle, not yet by muscle.

- **Dependency injection vs "forced by architecture".** Understood that `LinkCache` receives
  an already-built `WikiClient` instance rather than constructing its own. Initially framed
  this as mandatory for the layering to work — it isn't (nothing stops `LinkCache.__init__`
  from doing `self._client = WikiClient()` itself). It's a deliberate design choice for (a) one
  shared instance across the app instead of redundant ones, and (b) testability — tests hand
  in a `MagicMock()` instead of a real client. Revisit if this comes up again in `server/app.py`
  wiring, where the shared-instance argument will matter more concretely.

## Understood (apprehended, for reference)

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
