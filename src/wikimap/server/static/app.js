// vis-network setup, SSE client, and mode controls.
// Applies incoming Steps to the graph as they arrive — this is what makes the
// graph build live on screen. No search logic here; the server sends Steps.
//
// Two kinds of setting live in this file and they are deliberately separate:
//   - SEARCH knobs are the server's (config.py). Fetched from /api/config, sent back
//     as query params, never stored here.
//   - DISPLAY knobs are the browser's. They never touch the network; contract 2 says
//     the backend has no opinion about drawing. Stored in localStorage.

// --- graph -----------------------------------------------------------------
// DataSet is vis-network's observable collection: the network redraws itself when
// you add to it, so "live building" needs no explicit re-render call anywhere below.
const nodes = new vis.DataSet();
const edges = new vis.DataSet();

const network = new vis.Network(
  document.getElementById("graph"),
  { nodes, edges },
  {
    nodes: { shape: "dot", size: 12, font: { color: "#e8e8ea", size: 13 } },
    edges: { color: { color: "#3f4350" }, arrows: { to: { scaleFactor: 0.4 } }, smooth: false },
    physics: {
      // Force-directed layout: the browser decides positions. The server never
      // sends coordinates — networkx stores structure only (see LEARN.md).
      solver: "forceAtlas2Based",
      forceAtlas2Based: { gravitationalConstant: -45, springLength: 110 },
      stabilization: { iterations: 60 },
    },
    interaction: { hover: true },
  }
);

// Binding helper. A plain `getElementById(...).addEventListener(...)` throws on a
// missing element, and because module code runs top to bottom that ONE throw kills
// every listener registered after it — which is how a wiped settings panel silently
// disabled the Run button. Loud in the console, but never fatal.
function bind(id, event, handler) {
  const el = document.getElementById(id);
  if (!el) {
    console.error(`wikimap: no element #${id} — control disabled`);
    return null;
  }
  el.addEventListener(event, handler);
  return el;
}

// --- log -------------------------------------------------------------------
const logEl = document.getElementById("log");

function log(message, kind) {
  const line = document.createElement("div");
  line.className = "entry" + (kind ? " " + kind : "");
  // textContent, never innerHTML: page titles come from Wikipedia and land in this
  // panel verbatim. textContent renders them as text, so a title containing markup
  // can never become markup. (vis-network labels are drawn on canvas, so they're
  // safe by construction — this panel is the only place raw titles meet the DOM.)
  line.textContent = message;
  logEl.prepend(line);
}

// --- timing ------------------------------------------------------------
// Benchmarks measured entirely in the browser, off SSE arrival times — never sent
// to or read from the server. This is deliberate, not a shortcut: contract 2 says
// an algorithm must not know the renderer or transport exists, and "how long did
// this tick take to reach the screen" is exactly a rendering-side question, same
// family as node size/colour. performance.now() (not Date.now()) is monotonic —
// immune to system clock adjustments — and sub-millisecond, which wall-clock
// Date.now() is not guaranteed to be.
function formatMs(ms) {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;
}

function formatTiming(timing) {
  return `[+${formatMs(timing.deltaMs)} · ${formatMs(timing.elapsedMs)} total]`;
}

// --- applying a Step -------------------------------------------------------
// The whole of contract 2 on the client side: a Step says which nodes and edges
// appeared this tick, and this function is the only thing that touches the graph.
// `timing`, if given, is purely a log-line decoration (see above) — never used to
// decide what gets drawn.
function applyStep(step, seed, target, timing) {
  for (const node of step.nodes || []) {
    const isSeed = node.id === seed;
    const isTarget = node.id === target;
    const payload = {
      id: node.id,
      label: node.id,
      title: node.score == null ? node.id : `${node.id} — score ${node.score.toFixed(3)}`,
      color: isSeed ? "#4ade80" : isTarget ? "#f472b6" : nodeColor(node),
      // sizeFor falls back to 12 internally so the graph still draws even if the
      // display panel failed to load — a broken settings UI must not take the
      // actual product down with it.
      size: (isSeed || isTarget ? 1.6 : 1) * sizeFor(node),
      // Kept on the node so a later "colour by" change can recolour without
      // re-running the search. vis-network ignores fields it doesn't recognise,
      // which is what makes a DataSet item a fine place to park real data.
      score: node.score,
      depth: node.depth,
      endpoint: isSeed || isTarget,
    };
    // update() = insert or overwrite. A page can legitimately reappear in a later
    // Step (it's linked from several pages); overwriting keeps the newest score
    // rather than throwing a duplicate-id error the way add() would.
    nodes.update(payload);
  }

  for (const edge of step.edges || []) {
    const id = `${edge.source}->${edge.target}`;
    if (!edges.get(id)) edges.add({ id, from: edge.source, to: edge.target });
  }

  // Only when the graph actually grew — a note-only Step (e.g. "reached target",
  // "stopped: node cap") has nothing new to fit the camera to.
  if ((step.nodes && step.nodes.length) || (step.edges && step.edges.length)) scheduleFit();
  if (step.note) log(timing ? `${formatTiming(timing)} ${step.note}` : step.note);
}

// Keeps the camera zoomed to fit the whole graph as it grows, instead of the user
// having to scroll-zoom out by hand every few nodes. requestAnimationFrame coalesces
// bursts of Steps arriving faster than one frame (a warm cache can replay a whole run
// in well under a second — see HISTORY) into a single fit() call rather than fighting
// itself once per Step.
let fitPending = false;
function scheduleFit() {
  if (!display.autoFit || fitPending) return;
  fitPending = true;
  requestAnimationFrame(() => {
    // vis-network's actual option key is "easingFunction", not "easing" — an
    // unrecognised key is silently dropped, not an error, so this typo cost nothing
    // visible on its own, but it's still wrong. Caught alongside the real bug below.
    network.fit({ animation: { duration: 250, easingFunction: "easeInOutQuad" } });
    fitPending = false;
  });
}

function nodeColor(node) {
  return display.colorBy === "depth" ? depthColor(node.depth) : scoreColor(node.score);
}

// Same score-vs-depth split as colour, but for size: d-sizeBy picks a field and
// this scales the d-nodeSize slider per node instead of applying it uniformly.
// "uniform" (the default) reproduces the old one-slider-fits-all behaviour exactly.
function sizeFor(node) {
  const base = display.nodeSize ?? 12;
  if (display.sizeBy === "score") return base * scoreSizeScale(node.score);
  if (display.sizeBy === "depth") return base * depthSizeScale(node.depth);
  return base;
}

function scoreSizeScale(score) {
  if (score == null) return 1;
  const t = Math.max(0, Math.min(1, score));
  return 0.6 + 0.9 * t; // 0.6x at score 0, up to 1.5x at score 1
}

function depthSizeScale(depth) {
  if (depth == null) return 1;
  // bfs's backward frontier carries negative depth (see bfs.py) — abs() so both
  // directions shrink the same way as they get farther from their own endpoint.
  const hops = Math.abs(depth);
  return Math.max(0.5, 1.4 - hops * 0.12); // shrinks with distance, floors at 0.5x
}

function scoreColor(score) {
  if (score == null) return "#64748b";
  const t = Math.max(0, Math.min(1, score));
  const hue = 210 - 170 * t; // 210 = cool slate, 40 = warm gold
  return `hsl(${hue}, 65%, ${35 + 20 * t}%)`;
}

function depthColor(depth) {
  if (depth == null) return "#64748b";
  // Cycles through distinct hues so each hop ring reads as its own band, rather
  // than a gradient where depth 5 and 6 look identical.
  const hue = (depth * 47) % 360;
  return `hsl(${hue}, 60%, 55%)`;
}

// --- display settings ------------------------------------------------------
// Every control carries data-display and its id is "d-<key>", so this reads them
// generically instead of naming each one twice. Adding a control = adding HTML.
const DISPLAY_STORAGE_KEY = "wikimap.display";
const displayInputs = [...document.querySelectorAll("[data-display]")];
const displayDefaults = Object.fromEntries(
  displayInputs.map((el) => [el.id.slice(2), el.type === "checkbox" ? el.checked : el.value])
);
let display = {};

function readDisplay() {
  display = {};
  for (const el of displayInputs) {
    const key = el.id.slice(2); // strip the "d-" prefix
    if (el.type === "checkbox") display[key] = el.checked;
    else if (el.type === "range") display[key] = parseFloat(el.value);
    else display[key] = el.value;
  }
}

function applyDisplay() {
  readDisplay();
  // Nothing to apply — the panel is missing. Leave the network on its constructor
  // defaults rather than writing `undefined` into every physics option.
  if (!displayInputs.length) return;

  network.setOptions({
    nodes: { size: display.nodeSize },
    edges: {
      width: display.linkWidth,
      arrows: { to: { enabled: display.arrows, scaleFactor: 0.4 } },
    },
    physics: {
      enabled: display.physics,
      solver: "forceAtlas2Based",
      forceAtlas2Based: {
        centralGravity: display.centralGravity,
        // Negated here: vis-network wants a negative constant for repulsion, but a
        // slider that moves right for "more repel" is the only sane control.
        gravitationalConstant: -display.repel,
        springConstant: display.springConstant,
        springLength: display.springLength,
      },
    },
  });

  // Endpoints stay larger than ordinary nodes, so their per-node size override has
  // to be rewritten whenever the base size or size-by field changes.
  const resized = nodes.get().map((n) => ({
    id: n.id,
    size: (n.endpoint ? 1.6 : 1) * sizeFor(n),
    color: n.endpoint ? n.color : nodeColor(n),
  }));
  if (resized.length) nodes.update(resized);

  applyLabelFade();
  localStorage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify(display));
}

// vis-network has no "hide labels below zoom X" option, so this watches the zoom
// level and drops the font to 0 below the threshold. Cheaper than rewriting every
// node's label, because it's one global option rather than N DataSet updates.
function applyLabelFade() {
  if (display.labelZoom == null) return;
  const visible = network.getScale() >= display.labelZoom;
  network.setOptions({ nodes: { font: { size: visible ? 13 : 0 } } });
}

network.on("zoom", applyLabelFade);

// --- node detail panel -------------------------------------------------
// Third sibling of #graph inside #canvas — see index.html's comment on why it
// can never be nested inside #graph.
const nodePanel = document.getElementById("node-panel");
const nodePanelTitle = document.getElementById("node-panel-title");
const nodePanelMeta = document.getElementById("node-panel-meta");
const nodePanelSummary = document.getElementById("node-panel-summary");
const nodePanelLink = document.getElementById("node-panel-link");
if (!nodePanel) console.error("wikimap: no element #node-panel — node detail disabled");

// Guards against a slow /api/page response for a node the user has since
// clicked away from landing in the panel late and overwriting what's shown now.
let openNodeTitle = null;

function closeNodePanel() {
  openNodeTitle = null;
  nodePanel?.classList.add("hidden");
}

function nodeMetaLine(node) {
  const score = node.score == null ? "score —" : `score ${node.score.toFixed(3)}`;
  const depth = node.depth == null ? "depth —" : `depth ${node.depth}`;
  return `${score} · ${depth}`;
}

function showNodeDetail(id) {
  if (!nodePanel) return;
  const node = nodes.get(id);
  if (!node) return; // clicked an id vis-network still remembers but the DataSet doesn't

  openNodeTitle = id;
  nodePanel.classList.remove("hidden");
  nodePanelTitle.textContent = node.id;
  nodePanelMeta.textContent = nodeMetaLine(node);
  nodePanelSummary.textContent = "Loading summary…";
  nodePanelLink.classList.add("hidden");

  fetch(`/api/page?${new URLSearchParams({ title: id })}`)
    .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
    .then(({ ok, body }) => {
      if (openNodeTitle !== id) return; // user has since clicked a different node
      if (!ok) {
        nodePanelSummary.textContent = body.message || "Summary unavailable.";
        return;
      }
      // textContent, not innerHTML — same rule as log(): this is real Wikipedia
      // text landing in the DOM verbatim.
      nodePanelSummary.textContent = body.summary || "No summary available.";
      nodePanelLink.href = body.url;
      nodePanelLink.classList.remove("hidden");
    })
    .catch(() => {
      if (openNodeTitle !== id) return;
      nodePanelSummary.textContent = "Could not reach the server.";
    });
}

if (nodePanel) {
  // "click", not "selectNode": click fires for node/edge/background clicks alike
  // (params.nodes/params.edges say which), so one listener gives us both "open on
  // node" and "close on background click" instead of combining two events.
  network.on("click", (params) => {
    if (params.nodes.length > 0) showNodeDetail(params.nodes[0]);
    else closeNodePanel();
  });
  bind("node-panel-close", "click", closeNodePanel);
}

function loadDisplay() {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(DISPLAY_STORAGE_KEY)) || {};
  } catch {
    saved = {}; // corrupt or absent — fall back to the HTML defaults
  }
  for (const el of displayInputs) {
    const key = el.id.slice(2);
    if (!(key in saved)) continue;
    if (el.type === "checkbox") el.checked = saved[key];
    else el.value = saved[key];
  }
  applyDisplay();
}

// Called from the init block at the bottom of this file, deliberately AFTER the run
// form is wired. Order matters: the search UI is the product, the settings panel is
// a convenience, so the product gets its listeners first.
function initDisplayControls() {
  for (const el of displayInputs) el.addEventListener("input", applyDisplay);

  bind("reset-display", "click", () => {
    for (const el of displayInputs) {
      const value = displayDefaults[el.id.slice(2)];
      if (el.type === "checkbox") el.checked = value;
      else el.value = value;
    }
    applyDisplay();
  });

  bind("toggle-panel", "click", () => {
    document.getElementById("panel")?.classList.toggle("hidden");
  });

  loadDisplay();
}

// --- SSE -------------------------------------------------------------------
let source = null;
// A Step marks the instant a node/edge is ADDED, but forceAtlas2 keeps pushing the
// whole layout outward for a while afterward as it settles — and Steps arrive with
// real network latency between them (a cold run's fetches are seconds apart, see
// HISTORY), which is plenty of time for physics to drift the graph back out past
// whatever scheduleFit() last framed. One fit() per Step alone chases a moving
// target and loses. This interval keeps re-fitting while a run is in flight so the
// camera tracks the settling, not just the arrival. scheduleFit() itself is cheap
// to over-call (guarded by fitPending + requestAnimationFrame), so a short period
// costs nothing when there's nothing new to do.
let fitInterval = null;
// Every Step of the last run, kept so the build can be replayed without searching
// again. This is free: the algorithm already emits a recorded stream, so "animate"
// is just the same steps on a different clock.
let recorded = [];
let recordedTimings = []; // parallel to recorded — one {deltaMs, elapsedMs} per Step
let lastRun = null;
// Anchors for the current run's benchmarks (see "timing" above). Null between runs
// so termination handlers can tell "no run has started" from "run took ~0ms".
let runStartTime = null;
let lastStepTime = null;

const form = document.getElementById("run-form");
const runBtn = document.getElementById("run");
const stopBtn = document.getElementById("stop");
// Lives in the settings panel, so unlike the buttons above it may legitimately be
// absent — and a missing one must not throw and kill the run handler. Kept as a real
// element-or-null and funnelled through setReplayEnabled(), rather than stubbed with
// `|| {}`: assigning .disabled to a bare object silently succeeds and does nothing,
// so a missing button would be undetectable. This matches what bind() does — say so
// once, in the console, then carry on.
const replayBtn = document.getElementById("replay");
if (!replayBtn) console.error("wikimap: no element #replay — replay disabled");

function setReplayEnabled(enabled) {
  if (replayBtn) replayBtn.disabled = !enabled;
}

// --- title autocomplete -----------------------------------------------------
// Dropdown of real Wikipedia titles under #seed/#target, backed by /api/suggest
// (WikiClient.search_titles — a raw list=prefixsearch call, see wiki/client.py).
// Not a search knob (contract 1): it never changes what an algorithm does, only
// helps the user land on a real title instead of guessing one that dead-ends.
const SUGGEST_MIN_CHARS = 2;
const SUGGEST_DEBOUNCE_MS = 200;

function setupAutocomplete(inputId, listId) {
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  if (!input || !list) {
    console.error(`wikimap: no element #${inputId}/#${listId} — autocomplete disabled`);
    return;
  }

  let debounceTimer = null;

  function hide() {
    list.hidden = true;
    list.replaceChildren();
  }

  function renderSuggestions(titles) {
    list.replaceChildren();
    for (const title of titles) {
      const item = document.createElement("li");
      // textContent, never innerHTML — same rule as log()/nodePanelSummary: these
      // are real Wikipedia titles landing in the DOM verbatim.
      item.textContent = title;
      // mousedown, not click: it fires BEFORE the input's blur, so the value is
      // set before blur's hide() (below) would otherwise race the list closed and
      // swallow the click.
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
        input.value = title;
        hide();
      });
      list.append(item);
    }
    list.hidden = titles.length === 0;
  }

  input.addEventListener("input", () => {
    const query = input.value.trim();
    clearTimeout(debounceTimer);
    if (query.length < SUGGEST_MIN_CHARS) {
      hide();
      return;
    }
    debounceTimer = setTimeout(() => {
      fetch(`/api/suggest?${new URLSearchParams({ q: query })}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((titles) => {
          // Stale guard: a slow response for a query the user has since typed
          // past must not overwrite what a faster, more recent one already drew —
          // same shape as showNodeDetail()'s openNodeTitle check, keyed on the
          // query text instead of a node id.
          if (input.value.trim() !== query) return;
          renderSuggestions(titles);
        })
        .catch(() => {
          // A failed lookup just means no suggestions — the user can still type
          // and submit a title by hand, so this fails silently rather than
          // logging over what may just be a flaky connection.
        });
    }, SUGGEST_DEBOUNCE_MS);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  input.addEventListener("blur", hide);
}

setupAutocomplete("seed", "seed-suggestions");
setupAutocomplete("target", "target-suggestions");

function stop() {
  if (source) {
    source.close();
    source = null;
  }
  if (fitInterval) {
    clearInterval(fitInterval);
    fitInterval = null;
  }
  runBtn.disabled = false;
  stopBtn.disabled = true;
  // Cleared last, after every caller above has already read it into its own
  // `total` — see the "Null between runs" comment where these are declared.
  runStartTime = null;
  lastStepTime = null;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  stop();

  nodes.clear();
  edges.clear();
  logEl.replaceChildren();
  closeNodePanel(); // the previously-inspected node no longer exists in the graph
  recorded = [];
  recordedTimings = [];
  setReplayEnabled(false);

  const seed = document.getElementById("seed").value.trim();
  const target = document.getElementById("target").value.trim();
  if (!seed || !target) return;
  lastRun = { seed, target };

  runBtn.disabled = true;
  stopBtn.disabled = false;

  // URLSearchParams handles the encoding for every value at once, so titles with
  // &, ?, # or spaces survive the query string. Only SEARCH knobs go here —
  // display settings never leave the browser.
  const query = new URLSearchParams({
    seed,
    target,
    algorithm: document.getElementById("algorithm").value || "default",
    ...knobValues(),
  });
  source = new EventSource(`/api/connect?${query}`);
  fitInterval = setInterval(scheduleFit, 400);
  // t=0 for this run's benchmarks — right where the request actually goes out, so
  // "elapsed" includes real network/server time, not just client-side work.
  runStartTime = performance.now();
  lastStepTime = runStartTime;

  // One handler per event name the server emits. This is why _sse() writes an
  // "event:" line — without it everything would arrive as a generic "message".
  source.addEventListener("status", (e) => log(JSON.parse(e.data).message, "status"));
  source.addEventListener("step", (e) => {
    const step = JSON.parse(e.data);
    const now = performance.now();
    const timing = { deltaMs: now - lastStepTime, elapsedMs: now - runStartTime };
    lastStepTime = now;
    recorded.push(step);
    recordedTimings.push(timing);
    applyStep(step, seed, target, timing);
  });
  source.addEventListener("error", (e) => log(JSON.parse(e.data).message, "failure"));
  source.addEventListener("done", () => {
    const total = runStartTime == null ? null : performance.now() - runStartTime;
    log(total == null ? "done" : `done — total ${formatMs(total)}`, "status");
    setReplayEnabled(recorded.length > 0);
    stop();
    // The interval that was tracking physics settling just got cleared by stop() —
    // one more fit shortly after catches whatever the layout does in the last
    // fraction of a second, rather than freezing the view exactly at cutoff.
    setTimeout(scheduleFit, 400);
  });

  // Fired on transport failure (server died, connection dropped) — distinct from
  // our own "error" event above, which is an in-band message the server chose to
  // send. Without closing here, EventSource would auto-reconnect and re-run the
  // whole search, which is the last thing we want.
  source.onerror = () => {
    if (source && source.readyState === EventSource.CLOSED) {
      const total = runStartTime == null ? null : performance.now() - runStartTime;
      log(total == null ? "connection closed" : `connection closed — ran ${formatMs(total)}`, "failure");
      stop();
    }
  };
});

bind("stop", "click", () => {
  const total = runStartTime == null ? null : performance.now() - runStartTime;
  stop();
  log(total == null ? "stopped" : `stopped — ran ${formatMs(total)}`, "status");
});

// Replay the recorded Steps on a timer. Obsidian has to synthesise an animation;
// ours is the real build order, because the algorithm genuinely emitted it one
// tick at a time (contract 2).
bind("replay", "click", () => {
  if (!recorded.length || !lastRun) return;
  const steps = recorded;
  // Replay's ticks land every 600ms on a fake clock — that's for watchability, not
  // a benchmark. The REAL per-step timing from the live run is preserved here so
  // replayed log lines still show what actually happened, not the animation's pace.
  const timings = recordedTimings;
  nodes.clear();
  edges.clear();
  logEl.replaceChildren();
  closeNodePanel();
  setReplayEnabled(false);

  let i = 0;
  const timer = setInterval(() => {
    if (i >= steps.length) {
      clearInterval(timer);
      setReplayEnabled(true);
      log("replay done", "status");
      return;
    }
    applyStep(steps[i], lastRun.seed, lastRun.target, timings[i]);
    i++;
  }, 600);
});

// --- search knobs ----------------------------------------------------------
// Owned by config.py, rendered here (contract 1). The inputs ship disabled and with
// no value/min/max in the HTML; everything below is filled in from /api/config, so
// the browser never keeps a copy of a number that could drift out of sync. If the
// fetch fails the controls simply stay disabled and the server's defaults apply.
const KNOBS = ["top_k", "max_depth", "max_nodes", "heuristic_weight", "hop_scale"];
let defaults = null;

function knobValues() {
  // Read straight off the inputs at submit time, not from a cached object — the
  // DOM is the single source of truth for what the user currently has selected.
  const values = {};
  for (const knob of KNOBS) {
    const input = document.getElementById(knob);
    if (input && input.value !== "") values[knob] = input.value;
  }
  return values;
}

function applyDefaults() {
  for (const knob of KNOBS) document.getElementById(knob).value = defaults[knob];
}

// Weight/hop-scale knobs are dimmed for algorithms that ignore them (greedy, bfs),
// so the panel never implies a control is doing something it isn't. Both astar and
// default (bidirectional A* — see default.py) read them, so both stay active.
//
// max nodes is the mirror image: bfs-only as of 2026-07-30 (see config.py) — the
// other three cap fan-out per node already, so max_depth * top_k bounds them without
// it.
function syncAlgorithmUI() {
  const chosen = document.getElementById("algorithm").value;
  for (const label of document.querySelectorAll(".weighted")) {
    label.classList.toggle("inactive", chosen !== "astar" && chosen !== "default");
  }
  for (const label of document.querySelectorAll(".nodecap")) {
    label.classList.toggle("inactive", chosen !== "bfs");
  }
  document.querySelector("header .mode").textContent = `Connect — ${chosen}`;
}

fetch("/api/config")
  .then((r) => r.json())
  .then((cfg) => {
    defaults = Object.fromEntries(KNOBS.map((knob) => [knob, cfg[knob]]));

    const picker = document.getElementById("algorithm");
    for (const name of cfg.algorithms) {
      const option = document.createElement("option");
      option.value = name;
      // textContent, not innerHTML — same rule as the log panel.
      option.textContent = name;
      picker.append(option);
    }
    picker.value = cfg.default_algorithm;
    picker.disabled = false;
    picker.addEventListener("change", syncAlgorithmUI);
    syncAlgorithmUI();

    for (const knob of KNOBS) {
      const [min, max] = cfg.bounds[knob];
      const input = document.getElementById(knob);
      input.min = min;
      input.max = max;
      input.disabled = false;
      // The same bounds the server validates against, so the browser can't offer a
      // value that would come back 422. The server still checks — client-side
      // limits are a convenience, never the enforcement.
      document.getElementById(`${knob}-range`).textContent = `${min}–${max}`;
    }
    applyDefaults();
    const reset = document.getElementById("reset-knobs");
    reset.disabled = false;
    reset.addEventListener("click", applyDefaults);
  })
  .catch(() => {});

// --- init ------------------------------------------------------------------
// Last, on purpose: everything above has already registered its listeners, so a
// fault in the settings panel can no longer stop the search UI from working.
initDisplayControls();
