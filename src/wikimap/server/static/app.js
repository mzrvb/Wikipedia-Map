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
    nodes: { shape: "dot", size: 12, font: { color: "#1a1c22", size: 13 } },
    edges: { color: { color: "#c7cbd6" }, arrows: { to: { scaleFactor: 0.4 } }, smooth: false },
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

// --- log: rendered as a transit-map "line" (see style.css) -----------------
const logEl = document.getElementById("log");

// One CSS class per stop kind (style.css draws the dot/rail for each). `step.path`
// (contracts.py) is checked directly rather than sniffing the note's text for
// "reached" — it's the one case with real structured data to key off instead of
// parsing a string meant for humans.
function stepKind(step) {
  if (step.path) return "destination";
  if (step.note.startsWith("start:")) return "origin";
  if (step.note.startsWith("exhausted")) return "exhausted";
  if (step.note.startsWith("round ")) return "round";
  return undefined;
}

// `meta`, if given, renders as a small caption under the main label — the
// per-step timing benchmark, kept visually separate from the note itself instead
// of crammed into one line (see style.css's ".meta" comment).
function log(message, kind, meta) {
  const line = document.createElement("div");
  line.className = "entry" + (kind ? " " + kind : "");

  const dot = document.createElement("span");
  dot.className = "dot";

  const label = document.createElement("span");
  label.className = "label";
  // textContent, never innerHTML: page titles come from Wikipedia and land in this
  // panel verbatim. textContent renders them as text, so a title containing markup
  // can never become markup. (vis-network labels are drawn on canvas, so they're
  // safe by construction — this panel is the only place raw titles meet the DOM.)
  label.textContent = message;
  line.append(dot, label);

  if (meta) {
    const metaEl = document.createElement("span");
    metaEl.className = "meta";
    metaEl.textContent = meta;
    line.append(metaEl);
  }

  // Appended, not prepended: a transit line reads top-to-bottom as a route, run
  // start at the top — the old log read newest-on-top, which doesn't have a
  // "direction of travel" for this metaphor to attach to. scrollTop tracks the
  // newest stop into view as the line grows, the same way a live departure board
  // follows a train instead of making you scroll to find it.
  logEl.append(line);
  logEl.scrollTop = logEl.scrollHeight;
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
  // One tick per Step, for "colour by discovery order" below. Only recorded on a
  // node's FIRST sighting (guarded by `existing` below) — a page reappearing in a
  // later Step (linked from more than one page) must keep the tick it was actually
  // discovered in, not the tick of its most recent mention.
  tickCounter++;
  for (const node of step.nodes || []) {
    const isSeed = node.id === seed;
    const isTarget = node.id === target;
    const existing = nodes.get(node.id);
    // First sighting gets this tick; a repeat sighting keeps the tick it already
    // has. Computed before nodeColor() below so "colour by discovery order" can
    // see it — the raw Step node object has no `tick` field of its own.
    const tick = existing ? existing.tick : tickCounter;
    if (!existing) maxTick = tickCounter;
    const payload = {
      id: node.id,
      label: node.id,
      title: node.score == null ? node.id : `${node.id} — score ${node.score.toFixed(3)}`,
      color: isSeed ? "#4ade80" : isTarget ? "#f472b6" : nodeColor({ ...node, tick }),
      // sizeFor falls back to 12 internally so the graph still draws even if the
      // display panel failed to load — a broken settings UI must not take the
      // actual product down with it.
      size: (isSeed || isTarget ? 1.6 : 1) * sizeFor(node),
      // Kept on the node so a later "colour by" change can recolour without
      // re-running the search. vis-network ignores fields it doesn't recognise,
      // which is what makes a DataSet item a fine place to park real data.
      score: node.score,
      depth: node.depth,
      tick,
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
  if (step.note) log(step.note, stepKind(step), timing ? formatTiming(timing) : undefined);
  // path is only ever set on the terminal success Step (see contracts.py) — every
  // node/edge it names was already added by an earlier Step, so this only needs to
  // restyle what's already on the canvas, never create anything.
  if (step.path) highlightPath(step.path);
}

const PATH_COLOR = "#facc15"; // amber — distinct from every scoreColor/depthColor hue

// Restyles the winning seed -> ... -> target route so it reads as one connected
// line at a glance instead of making the viewer trace individual edge colours
// through a graph that may hold hundreds of other nodes by the time a run finishes.
// Node fill colour is left alone (still score/depth-coded) — only a border ring is
// added, so "colour by" stays meaningful for path nodes too. `onPath` is kept on
// the DataSet item (same trick as score/depth) so applyDisplay()'s resize pass
// below can re-derive the border after a later display-setting change instead of
// silently losing it the next time nodeColor() recomputes the fill.
function highlightPath(path) {
  const nodeUpdates = path
    .map((id) => nodes.get(id))
    .filter(Boolean)
    .map((n) => ({
      id: n.id,
      onPath: true,
      borderWidth: 3,
      borderWidthSelected: 4,
      color: { background: n.color, border: PATH_COLOR },
    }));
  if (nodeUpdates.length) nodes.update(nodeUpdates);

  const edgeUpdates = [];
  for (let i = 0; i < path.length - 1; i++) {
    const id = `${path[i]}->${path[i + 1]}`;
    if (edges.get(id)) edgeUpdates.push({ id, onPath: true, color: { color: PATH_COLOR }, width: 3 });
  }
  if (edgeUpdates.length) edges.update(edgeUpdates);

  applyOffPathDim();
}

// "Dim off-path" (d-dimOffPath) is a separate toggle from "colour by" — it doesn't
// pick a colour scheme, it mutes everything OUTSIDE whichever scheme is active so
// the winning route reads as the one thing in full colour. A no-op until a path
// actually exists (checked via `onPath` rather than a separate boolean, so this
// can't drift out of sync with what highlightPath() actually marked), and it re-
// runs from applyDisplay() too, so toggling the checkbox after a run finishes
// still takes effect immediately.
function applyOffPathDim() {
  const anyPath = nodes.get().some((n) => n.onPath);
  const dim = !!(display.dimOffPath && anyPath);
  const nodeUpdates = nodes.get().map((n) => ({ id: n.id, opacity: dim && !n.onPath ? 0.15 : 1 }));
  if (nodeUpdates.length) nodes.update(nodeUpdates);
  const edgeUpdates = edges.get().map((e) => ({ id: e.id, opacity: dim && !e.onPath ? 0.15 : 1 }));
  if (edgeUpdates.length) edges.update(edgeUpdates);
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
  switch (display.colorBy) {
    case "depth":
      return depthColor(node.depth);
    case "side":
      return sideColor(node.depth);
    case "recency":
      return recencyColor(node.tick);
    case "band":
      return bandColor(node.score);
    default:
      return scoreColor(node.score);
  }
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
  // default's backward frontier carries negative depth (see default.py) — abs() so
  // both directions shrink the same way as they get farther from their own endpoint.
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

// Two flat colours, not a gradient — this answers a different question than depth
// does: depth says "how far from its own endpoint", side says "which half of the
// bidirectional search found this at all" (default.py's forward/backward frontiers
// — see its module docstring). Depth's per-hop gradient blurs that distinction
// since both directions share one hue ramp; this makes the split absolute.
function sideColor(depth) {
  if (depth == null) return "#64748b";
  return depth > 0 ? "#2563eb" : depth < 0 ? "#ea580c" : "#64748b";
}

// Same gradient formula as scoreColor, keyed on WHEN a node was first discovered
// (tick / maxTick) rather than how similar it is. Distinct from depth: on a wide
// round, tick order and hop count can diverge a lot (a same-round node discovered
// late because its parent was slow to process still shares that round's depth).
function recencyColor(tick) {
  if (tick == null || maxTick === 0) return "#64748b";
  const t = tick / maxTick;
  const hue = 210 - 170 * t; // 210 = cool slate (earliest), 40 = warm gold (newest)
  return `hsl(${hue}, 65%, ${35 + 20 * t}%)`;
}

// Discrete buckets instead of scoreColor's continuous gradient — trades precision
// for scannability: at a glance, "which of 4 named bands is this node in" is
// easier to compare across a big graph than judging a gradient's exact shade.
const SIMILARITY_BANDS = [
  { max: 0.25, color: "#64748b" }, // far
  { max: 0.5, color: "#3b82f6" }, // medium
  { max: 0.75, color: "#f59e0b" }, // close
  { max: Infinity, color: "#dc2626" }, // very close
];

function bandColor(score) {
  if (score == null) return "#64748b";
  return SIMILARITY_BANDS.find((band) => score <= band.max).color;
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
  // to be rewritten whenever the base size or size-by field changes. Endpoints are
  // always path nodes when a path exists (seed/target are its first/last stops),
  // and their `color` is already the {background, border} object highlightPath()
  // built — reusing it as-is preserves the border with no extra branch. A
  // non-endpoint path node's color is a flat string from nodeColor(), so its
  // border has to be re-added explicitly or a later display change would erase it.
  const resized = nodes.get().map((n) => {
    const fill = n.endpoint ? n.color : nodeColor(n);
    return {
      id: n.id,
      size: (n.endpoint ? 1.6 : 1) * sizeFor(n),
      color: n.onPath && !n.endpoint ? { background: fill, border: PATH_COLOR } : fill,
    };
  });
  if (resized.length) nodes.update(resized);
  applyOffPathDim();

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
// "Colour by discovery order" state (recencyColor above). tickCounter increments
// once per applyStep() call (live or replayed); maxTick is the highest tick any
// node has actually been stamped with, used to normalize recencyColor's gradient.
// Both reset alongside `recorded` — a fresh run/replay restarts the clock.
let tickCounter = 0;
let maxTick = 0;
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

// Shared by the dropdown below AND resolveTitle() (near the submit handler) —
// one place that knows how to ask the server for real titles matching a query.
function fetchSuggestions(query) {
  return fetch(`/api/suggest?${new URLSearchParams({ q: query })}`)
    .then((r) => (r.ok ? r.json() : []))
    .catch(() => []);
}

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
      fetchSuggestions(query).then((titles) => {
        // Stale guard: a slow response for a query the user has since typed
        // past must not overwrite what a faster, more recent one already drew —
        // same shape as showNodeDetail()'s openNodeTitle check, keyed on the
        // query text instead of a node id.
        if (input.value.trim() !== query) return;
        renderSuggestions(titles);
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

// Best-effort autocorrect for whoever presses Enter/Run without clicking a
// dropdown suggestion first. default.py compares seed/target to real Wikipedia
// link titles with exact string equality, so a hand-typed "astronomy" never
// matches the "Astronomy" the search actually walks through — the run just
// dead-ends at max_depth with a misleading "stopped" message instead of a
// clear typo error. Autocomplete already solves this when a suggestion is
// clicked; this closes the gap for Enter/Run by resolving to the top
// /api/suggest hit for whatever was typed. Deliberately a frontend fix, not a
// change to the algorithm's comparison logic: /api/suggest already exists for
// exactly this "turn user text into a real title" job, so reusing it here is
// one small addition instead of a second, redundant fix inside the algorithm.
async function resolveTitle(query) {
  if (query.length < SUGGEST_MIN_CHARS) return query;
  const titles = await fetchSuggestions(query);
  return titles.length ? titles[0] : query; // no match — fall back to what was typed
}

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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  stop();

  const rawSeed = document.getElementById("seed").value.trim();
  const rawTarget = document.getElementById("target").value.trim();
  if (!rawSeed || !rawTarget) return;

  // Disabled immediately, before the resolve-title round trip below, so a
  // second Enter/click during that brief window can't fire a second run.
  runBtn.disabled = true;

  const [seed, target] = await Promise.all([resolveTitle(rawSeed), resolveTitle(rawTarget)]);
  // Reflect the correction visibly — the user should see what actually ran,
  // not silently get a different search than the text still sitting in the box.
  document.getElementById("seed").value = seed;
  document.getElementById("target").value = target;
  document.getElementById("seed-suggestions").hidden = true;
  document.getElementById("target-suggestions").hidden = true;

  nodes.clear();
  edges.clear();
  logEl.replaceChildren();
  closeNodePanel(); // the previously-inspected node no longer exists in the graph
  recorded = [];
  recordedTimings = [];
  tickCounter = 0;
  maxTick = 0;
  setReplayEnabled(false);
  lastRun = { seed, target };

  stopBtn.disabled = false;

  // URLSearchParams handles the encoding for every value at once, so titles with
  // &, ?, # or spaces survive the query string. Only SEARCH knobs go here —
  // display settings never leave the browser.
  const query = new URLSearchParams({
    seed,
    target,
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
  tickCounter = 0;
  maxTick = 0;

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
const KNOBS = ["top_k", "max_depth"];
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

fetch("/api/config")
  .then((r) => r.json())
  .then((cfg) => {
    defaults = Object.fromEntries(KNOBS.map((knob) => [knob, cfg[knob]]));

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
