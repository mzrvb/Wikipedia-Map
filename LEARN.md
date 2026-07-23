# LEARN.md

Personal learning log for concepts hit while building this project. Not documentation about
the *project* (that's CLAUDE.md/HISTORY.md) — this is documentation about *me*: what's clicked,
what's still shaky, what to revisit. Newest entries at the top of each section.

## Struggling with / still shaky

(nothing currently — move items here as they come up)

## Refining (mostly got it, some edge cases fuzzy)

- **Dependency injection vs "forced by architecture".** Understood that `LinkCache` receives
  an already-built `WikiClient` instance rather than constructing its own. Initially framed
  this as mandatory for the layering to work — it isn't (nothing stops `LinkCache.__init__`
  from doing `self._client = WikiClient()` itself). It's a deliberate design choice for (a) one
  shared instance across the app instead of redundant ones, and (b) testability — tests hand
  in a `MagicMock()` instead of a real client. Revisit if this comes up again in `server/app.py`
  wiring, where the shared-instance argument will matter more concretely.

## Understood (apprehended, for reference)

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
