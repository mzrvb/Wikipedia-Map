// vis-network setup, SSE client, and mode controls.
// Applies incoming Steps to the graph as they arrive — this is what makes the
// graph build live on screen. No search logic here; the server sends Steps.

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
      // Warmer = closer to the target. score is cosine similarity in [-1, 1];
      // clamp to [0, 1] and use it as a hue ramp from slate to gold.
      color: isSeed ? "#4ade80" : isTarget ? "#f472b6" : scoreColor(node.score),
      size: isSeed || isTarget ? 20 : 12,
      depth: node.depth,
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

function scoreColor(score) {
  if (score == null) return "#64748b";
  const t = Math.max(0, Math.min(1, score));
  const hue = 210 - 170 * t; // 210 = cool slate, 40 = warm gold
  return `hsl(${hue}, 65%, ${35 + 20 * t}%)`;
}

// --- SSE -------------------------------------------------------------------
let source = null;

const form = document.getElementById("run-form");
const runBtn = document.getElementById("run");
const stopBtn = document.getElementById("stop");

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

  const seed = document.getElementById("seed").value.trim();
  const target = document.getElementById("target").value.trim();
  if (!seed || !target) return;

  runBtn.disabled = true;
  stopBtn.disabled = false;

  // URLSearchParams handles the encoding for every value at once, so titles with
  // &, ?, # or spaces survive the query string. The knobs ride along as ordinary
  // query params; omitting them entirely would still work, since the server
  // defaults each one to config's value.
  const query = new URLSearchParams({ seed, target, ...knobValues() });
  source = new EventSource(`/api/connect?${query}`);

  // One handler per event name the server emits. This is why _sse() writes an
  // "event:" line — without it everything would arrive as a generic "message".
  source.addEventListener("status", (e) => log(JSON.parse(e.data).message, "status"));
  source.addEventListener("step", (e) => applyStep(JSON.parse(e.data), seed, target));
  source.addEventListener("error", (e) => log(JSON.parse(e.data).message, "failure"));
  source.addEventListener("done", () => {
    log("done", "status");
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

// --- settings --------------------------------------------------------------
// Owned by config.py, rendered here (contract 1). The inputs ship disabled and with
// no value/min/max in the HTML; everything below is filled in from /api/config, so
// the browser never keeps a copy of a number that could drift out of sync. If the
// fetch fails the controls simply stay disabled and the server's defaults apply.
const KNOBS = ["top_k", "max_depth", "max_nodes"];
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
    defaults = { top_k: cfg.top_k, max_depth: cfg.max_depth, max_nodes: cfg.max_nodes };
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
