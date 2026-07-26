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

// --- applying a Step -------------------------------------------------------
// The whole of contract 2 on the client side: a Step says which nodes and edges
// appeared this tick, and this function is the only thing that touches the graph.
function applyStep(step, seed, target) {
  for (const node of step.nodes || []) {
    const isSeed = node.id === seed;
    const isTarget = node.id === target;
    const payload = {
      id: node.id,
      label: node.id,
      title: node.score == null ? node.id : `${node.id} — score ${node.score.toFixed(3)}`,
      color: isSeed ? "#4ade80" : isTarget ? "#f472b6" : nodeColor(node),
      size: isSeed || isTarget ? display.nodeSize * 1.6 : display.nodeSize,
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

  if (step.note) log(step.note);
}

function nodeColor(node) {
  return display.colorBy === "depth" ? depthColor(node.depth) : scoreColor(node.score);
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
  // to be rewritten whenever the base size changes.
  const resized = nodes.get().map((n) => ({
    id: n.id,
    size: n.endpoint ? display.nodeSize * 1.6 : display.nodeSize,
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
  const visible = network.getScale() >= display.labelZoom;
  network.setOptions({ nodes: { font: { size: visible ? 13 : 0 } } });
}

network.on("zoom", applyLabelFade);

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

for (const el of displayInputs) el.addEventListener("input", applyDisplay);

document.getElementById("reset-display").addEventListener("click", () => {
  for (const el of displayInputs) {
    const value = displayDefaults[el.id.slice(2)];
    if (el.type === "checkbox") el.checked = value;
    else el.value = value;
  }
  applyDisplay();
});

document.getElementById("toggle-panel").addEventListener("click", () => {
  document.getElementById("panel").classList.toggle("hidden");
});

// --- SSE -------------------------------------------------------------------
let source = null;
// Every Step of the last run, kept so the build can be replayed without searching
// again. This is free: the algorithm already emits a recorded stream, so "animate"
// is just the same steps on a different clock.
let recorded = [];
let lastRun = null;

const form = document.getElementById("run-form");
const runBtn = document.getElementById("run");
const stopBtn = document.getElementById("stop");
const replayBtn = document.getElementById("replay");

function stop() {
  if (source) {
    source.close();
    source = null;
  }
  runBtn.disabled = false;
  stopBtn.disabled = true;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  stop();

  nodes.clear();
  edges.clear();
  logEl.replaceChildren();
  recorded = [];
  replayBtn.disabled = true;

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
    algorithm: document.getElementById("algorithm").value || "greedy",
    ...knobValues(),
  });
  source = new EventSource(`/api/connect?${query}`);

  // One handler per event name the server emits. This is why _sse() writes an
  // "event:" line — without it everything would arrive as a generic "message".
  source.addEventListener("status", (e) => log(JSON.parse(e.data).message, "status"));
  source.addEventListener("step", (e) => {
    const step = JSON.parse(e.data);
    recorded.push(step);
    applyStep(step, seed, target);
  });
  source.addEventListener("error", (e) => log(JSON.parse(e.data).message, "failure"));
  source.addEventListener("done", () => {
    log("done", "status");
    replayBtn.disabled = recorded.length === 0;
    stop();
  });

  // Fired on transport failure (server died, connection dropped) — distinct from
  // our own "error" event above, which is an in-band message the server chose to
  // send. Without closing here, EventSource would auto-reconnect and re-run the
  // whole search, which is the last thing we want.
  source.onerror = () => {
    if (source && source.readyState === EventSource.CLOSED) {
      log("connection closed", "failure");
      stop();
    }
  };
});

stopBtn.addEventListener("click", () => {
  stop();
  log("stopped", "status");
});

// Replay the recorded Steps on a timer. Obsidian has to synthesise an animation;
// ours is the real build order, because the algorithm genuinely emitted it one
// tick at a time (contract 2).
replayBtn.addEventListener("click", () => {
  if (!recorded.length || !lastRun) return;
  const steps = recorded;
  nodes.clear();
  edges.clear();
  logEl.replaceChildren();
  replayBtn.disabled = true;

  let i = 0;
  const timer = setInterval(() => {
    if (i >= steps.length) {
      clearInterval(timer);
      replayBtn.disabled = false;
      log("replay done", "status");
      return;
    }
    applyStep(steps[i++], lastRun.seed, lastRun.target);
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

// A*-only knobs are dimmed for algorithms that ignore them, so the panel never
// implies a control is doing something it isn't.
function syncAlgorithmUI() {
  const chosen = document.getElementById("algorithm").value;
  for (const label of document.querySelectorAll(".astar-only")) {
    label.classList.toggle("inactive", chosen !== "astar");
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

loadDisplay();
