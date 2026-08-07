// Connect · Human-play mode.
//
// The human is the search: start on one article, click real links, try to reach
// the target in as few hops as possible. This file owns the game loop and the three
// screens (start → play → recap). It talks to the backend through four endpoints and
// holds no grading logic of its own — feedback.py is the only grader (contract 3),
// so this file just collects the moves and asks the server to score them at the end.

"use strict";

// ── Backend calls, in one place so the rest of the file reads as game logic ──────
const api = {
  suggest: (q) =>
    fetch(`/api/suggest?q=${encodeURIComponent(q)}`).then((r) => r.json()),
  article: (title) =>
    fetch(`/api/article?title=${encodeURIComponent(title)}`).then((r) => r.json()),
  evaluateRun: (target, moves) =>
    fetch("/api/evaluate_run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The wire format uses "from" (the Python side aliases it off the from_
      // keyword clash — see graph/contracts.py / server/app.py).
      body: JSON.stringify({ target, moves }),
    }).then((r) => r.json()),
};

// ── Game state ───────────────────────────────────────────────────────────────────
// One flat object rather than scattered globals so resetting a run is a single
// reassignment. `moves` is the list POSTed for grading; `path` is the same journey
// as titles, kept separately only because the breadcrumb wants titles and the
// grader wants {from,to} pairs.
let game = null;

function freshGame(seed, target) {
  return {
    target,
    current: null, // set by navigate()
    path: [], // ["Cat", "Mammal", ...] in click order
    moves: [], // [{from:"Cat", to:"Mammal"}, ...]
    startTime: performance.now(),
    finished: false,
  };
}

// ── Elements ───────────────────────────────────────────────────────────────────
const el = (id) => document.getElementById(id);
const screens = {
  start: el("start"),
  play: el("play"),
  recap: el("recap"),
};

function showScreen(name) {
  for (const [key, node] of Object.entries(screens)) {
    node.hidden = key !== name;
  }
}

// ── Start ────────────────────────────────────────────────────────────────────────
el("start-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const seed = el("seed").value.trim();
  const target = el("target").value.trim();
  const errorBox = el("start-error");
  errorBox.hidden = true;

  if (!seed || !target) return;

  // Resolve both fields to a REAL title before starting, the same fix app.js made
  // for the AI run (2026-07-31): the grader compares titles to Wikipedia links with
  // exact string equality, so a hand-typed "astronomy" must become "Astronomy" or
  // it never matches. /api/suggest's top hit is that canonical spelling.
  const [realSeed, realTarget] = await Promise.all([
    resolveTitle(seed),
    resolveTitle(target),
  ]);

  game = freshGame(realSeed, realTarget);
  el("hud-target").textContent = realTarget;

  // seed === target is a valid (trivial) run: already there, zero moves.
  if (realSeed === realTarget) {
    game.current = realSeed;
    game.path = [realSeed];
    finishRun("reached");
    return;
  }

  showScreen("play");
  startTimer();
  await navigate(realSeed, { record: false });
});

async function resolveTitle(text) {
  try {
    const hits = await api.suggest(text);
    return hits && hits.length ? hits[0] : text;
  } catch {
    return text; // offline / error: fall back to what they typed
  }
}

// ── Navigation ─────────────────────────────────────────────────────────────────
// The heart of the loop. `record` is false only for the opening page (landing on
// the seed isn't a move); every click after that records a {from,to} move first.
async function navigate(title, { record }) {
  if (record) {
    game.moves.push({ from: game.current, to: title });
  }
  game.current = title;
  game.path.push(title);
  renderPath();
  el("hud-moves").textContent = game.moves.length;

  // Winning is checked on the CLICK that reaches the target, not after loading it —
  // no reason to fetch and render the target's article just to immediately cover it
  // with the recap.
  if (title === game.target) {
    finishRun("reached");
    return;
  }

  const article = el("article");
  const loading = el("article-loading");
  article.setAttribute("aria-busy", "true");
  loading.hidden = false;

  let data;
  try {
    data = await api.article(title);
  } catch {
    loading.textContent = "Couldn't load that page. Try another link.";
    return;
  }
  loading.hidden = true;
  article.removeAttribute("aria-busy");

  if (!data || typeof data.html !== "string") {
    // 404 or unexpected shape — the server returns {message} on a miss.
    article.innerHTML = "";
    loading.hidden = false;
    loading.textContent =
      (data && data.message) || "That article has no content to play.";
    return;
  }

  // Safe innerHTML: the string is server-annotated (scripts/styles gone, text
  // re-escaped, links rewritten). See play.html's comment and wiki/article.py.
  article.innerHTML = data.html;
  article.scrollTop = 0;
  window.scrollTo(0, 0);
}

// One delegated click listener for the whole article, set up once. Re-attaching per
// navigation would leak listeners and miss the point of event delegation.
el("article").addEventListener("click", (event) => {
  const link = event.target.closest("a.wm-link");
  if (!link) {
    // A wm-disabled link (or any non-link) — swallow the click so a stray href="#"
    // can't jump the page, but do nothing else.
    if (event.target.closest("a")) event.preventDefault();
    return;
  }
  event.preventDefault();
  if (game.finished) return;
  const title = link.getAttribute("data-title");
  if (title) navigate(title, { record: true });
});

// ── Breadcrumb ─────────────────────────────────────────────────────────────────
function renderPath() {
  const nav = el("hud-path");
  nav.textContent = "";
  game.path.forEach((title, i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "→";
      nav.append(sep);
    }
    const crumb = document.createElement("span");
    crumb.className = "crumb";
    if (i === game.path.length - 1) crumb.classList.add("current");
    // textContent, never innerHTML: a page title is untrusted text from Wikipedia.
    crumb.textContent = title;
    nav.append(crumb);
  });
}

// ── Timer ──────────────────────────────────────────────────────────────────────
// Purely a display concern (like the AI run's client-side timings) — measured off
// performance.now(), never sent to the server, never part of any contract.
let timerHandle = null;
function startTimer() {
  stopTimer();
  timerHandle = setInterval(() => {
    const secs = Math.floor((performance.now() - game.startTime) / 1000);
    const m = Math.floor(secs / 60);
    const s = String(secs % 60).padStart(2, "0");
    el("hud-time").textContent = `${m}:${s}`;
  }, 500);
}
function stopTimer() {
  if (timerHandle) clearInterval(timerHandle);
  timerHandle = null;
}

// ── Finish + recap ───────────────────────────────────────────────────────────────
el("give-up").addEventListener("click", () => finishRun("gave-up"));
el("play-again").addEventListener("click", () => showScreen("start"));

async function finishRun(reason) {
  if (game.finished) return;
  game.finished = true;
  stopTimer();

  const won = reason === "reached";
  el("recap-title").textContent = won ? "🏁 You made it!" : "Run ended";

  const card = el("recap-summary");
  const seconds = Math.round((performance.now() - game.startTime) / 1000);
  const timeLabel = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  card.textContent = won
    ? `${game.path[0]} → ${game.target} in ${game.moves.length} moves · ${timeLabel}`
    : `Gave up after ${game.moves.length} moves · ${timeLabel}`;

  const list = el("recap-moves");
  showScreen("recap");

  if (game.moves.length === 0) {
    list.innerHTML = "";
    return;
  }

  list.innerHTML = "";
  const pending = document.createElement("li");
  pending.className = "recap-pending";
  pending.textContent = "Grading your moves…";
  list.append(pending);

  let result;
  try {
    result = await api.evaluateRun(game.target, game.moves);
  } catch {
    pending.textContent = "Couldn't reach the grader.";
    return;
  }
  renderEvaluations(result.evaluations || []);
}

function renderEvaluations(evaluations) {
  const list = el("recap-moves");
  list.innerHTML = "";
  for (const ev of evaluations) {
    const li = document.createElement("li");
    li.className = "recap-move";

    const badge = document.createElement("span");
    // Grade values are a closed set (Brilliant…Blunder); slug to a CSS class so the
    // colour lives in play.css, not here.
    badge.className = `grade grade-${ev.grade.toLowerCase()}`;
    badge.textContent = ev.grade;
    li.append(badge);

    const move = document.createElement("span");
    move.className = "recap-move-titles";
    move.textContent = `${ev.from} → ${ev.to}`;
    li.append(move);

    const delta = document.createElement("span");
    // delta > 0 means the move increased similarity-to-target (moved closer).
    delta.className = "recap-delta " + (ev.delta >= 0 ? "up" : "down");
    delta.textContent = (ev.delta >= 0 ? "+" : "") + ev.delta.toFixed(3);
    delta.title = "Change in semantic distance-to-target";
    li.append(delta);

    if (ev.note) {
      const note = document.createElement("span");
      note.className = "recap-note";
      note.textContent = ev.note;
      li.append(note);
    }
    list.append(li);
  }
}

// ── Autocomplete ─────────────────────────────────────────────────────────────────
// A compact, self-contained version of app.js's dropdown — same hard-won lessons
// baked in (debounce, stale-response guard, blur/focus guard, mousedown-not-click),
// but not shared code because the two pages ship no JS in common by design.
function setupAutocomplete(inputId, listId) {
  const input = el(inputId);
  const list = el(listId);
  let debounce = null;
  let seq = 0; // rising id: a slow response for an old query must not clobber a new one

  const close = () => {
    list.hidden = true;
    list.innerHTML = "";
  };

  input.addEventListener("input", () => {
    const q = input.value.trim();
    clearTimeout(debounce);
    if (!q) return close();
    debounce = setTimeout(async () => {
      const mine = ++seq;
      let hits;
      try {
        hits = await api.suggest(q);
      } catch {
        return close();
      }
      // Drop the response if a newer query started, or the field lost focus while
      // we waited (a late reopen over the page is the bug app.js hit on 2026-08-02).
      if (mine !== seq || document.activeElement !== input) return;
      if (!hits || !hits.length) return close();

      list.innerHTML = "";
      for (const title of hits) {
        const li = document.createElement("li");
        li.textContent = title; // textContent: untrusted Wikipedia text
        // mousedown, not click: blur fires before click and would close the list
        // first, swallowing the selection.
        li.addEventListener("mousedown", (e) => {
          e.preventDefault();
          input.value = title;
          close();
        });
        list.append(li);
      }
      list.hidden = false;
    }, 150);
  });

  input.addEventListener("blur", () => setTimeout(close, 100));
}

setupAutocomplete("seed", "seed-suggestions");
setupAutocomplete("target", "target-suggestions");

showScreen("start");
