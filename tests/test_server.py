"""The FastAPI server and its SSE stream (roadmap step 5).

All fast: `_algorithm` is monkeypatched to a fake that yields canned Steps, so no
Wikipedia call and no model load ever happens. That substitution is exactly what the
ABC buys us — the server only ever calls `run(seed, target)`, so anything with that
method can stand in for GreedyConnect.
"""

import json

import pytest
from fastapi.testclient import TestClient

from wikimap.graph.contracts import Edge, Node, Step
from wikimap.server import app as app_module


class _FakeAlgorithm:
    """Stand-in for GreedyConnect: yields whatever Steps the test hands it."""

    def __init__(self, steps: list[Step]):
        self._steps = steps
        self.calls: list[tuple[str, str]] = []
        self.params = []

    def run(self, seed: str, target: str, params=None):
        self.calls.append((seed, target))
        self.params.append(params)
        yield from self._steps


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture
def fake_algo(monkeypatch):
    """Install a fake algorithm and return it, so tests can assert on its calls."""

    def _install(steps: list[Step]) -> _FakeAlgorithm:
        algo = _FakeAlgorithm(steps)
        # `lambda *_:` because _algorithm now takes the algorithm name.
        monkeypatch.setattr(app_module, "_algorithm", lambda *_: algo)
        return algo

    return _install


def _events(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into (event_name, payload) pairs.

    Frames are separated by a blank line; within a frame, `event:` names it and
    `data:` carries the JSON. Parsing it here rather than trusting a library keeps
    the test honest about the wire format the browser actually receives.
    """
    parsed = []
    for frame in text.strip().split("\n\n"):
        name, data = None, None
        for line in frame.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if name is not None:
            parsed.append((name, data))
    return parsed


def test_index_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "wikimap" in response.text


def test_settings_panel_is_not_inside_the_graph_container(client):
    """Regression: vis-network's Canvas._create() begins with

        for (; container.hasChildNodes(); ) container.removeChild(firstChild)

    so every child of #graph is deleted the instant the Network is constructed.
    Nesting #panel there wiped the whole settings UI, and the resulting null
    getElementById killed app.js before the Run button was ever wired up.

    A browser-free structural check, because the failure is invisible server-side
    and costs a manual reload to notice.
    """
    from html.parser import HTMLParser

    class _Nesting(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[str | None] = []
            self.panel_ancestors: list[str] = []

        def handle_starttag(self, tag, attrs):
            element_id = dict(attrs).get("id")
            if element_id == "panel":
                self.panel_ancestors = [a for a in self.stack if a]
            # void elements never open a scope
            if tag not in {"input", "br", "img", "meta", "link", "hr"}:
                self.stack.append(element_id)

        def handle_endtag(self, tag):
            if self.stack:
                self.stack.pop()

    parser = _Nesting()
    parser.feed(client.get("/").text)

    assert parser.panel_ancestors, "#panel not found in index.html"
    assert "graph" not in parser.panel_ancestors, (
        f"#panel is nested inside #graph (ancestors: {parser.panel_ancestors}) — "
        "vis-network will delete it on startup"
    )


def test_node_panel_is_not_inside_the_graph_container(client):
    """Same regression as test_settings_panel_is_not_inside_the_graph_container,
    for the node-detail panel added alongside it: a THIRD sibling of #graph inside
    #canvas, never nested inside #graph, for the identical Canvas._create() reason.
    A standalone test (not a parametrization of the existing one) so that
    already-green regression test stays untouched.
    """
    from html.parser import HTMLParser

    class _Nesting(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[str | None] = []
            self.node_panel_ancestors: list[str] = []

        def handle_starttag(self, tag, attrs):
            element_id = dict(attrs).get("id")
            if element_id == "node-panel":
                self.node_panel_ancestors = [a for a in self.stack if a]
            if tag not in {"input", "br", "img", "meta", "link", "hr"}:
                self.stack.append(element_id)

        def handle_endtag(self, tag):
            if self.stack:
                self.stack.pop()

        def handle_startendtag(self, tag, attrs):
            # Self-closed void tags (<input .../>) never pushed onto the stack
            # above, so they must not pop one either — the base HTMLParser's
            # default calls handle_endtag too, which would unwind real ancestors
            # (there are over a dozen self-closing <input>s inside #panel, above
            # where #node-panel sits in the document).
            self.handle_starttag(tag, attrs)

    parser = _Nesting()
    parser.feed(client.get("/").text)

    assert parser.node_panel_ancestors, "#node-panel not found in index.html"
    assert "graph" not in parser.node_panel_ancestors, (
        f"#node-panel is nested inside #graph (ancestors: {parser.node_panel_ancestors}) "
        "— vis-network will delete it on startup"
    )


class _FakeWikiClient:
    """Stand-in for WikiClient: get_summary looks up a canned title -> dict table;
    search_titles looks up a canned query -> title-list table. Both endpoints that
    use this fixture (/api/page, /api/suggest) share the one WikiClient singleton
    in real code, so one fake covers both here too."""

    def __init__(self, summaries: dict[str, dict], suggestions: dict[str, list[str]] | None = None):
        self._summaries = summaries
        self._suggestions = suggestions or {}

    def get_summary(self, title: str) -> dict | None:
        return self._summaries.get(title)

    def search_titles(self, query: str) -> list[str]:
        return self._suggestions.get(query, [])


@pytest.fixture
def fake_wiki_client(monkeypatch):
    def _install(
        summaries: dict[str, dict], suggestions: dict[str, list[str]] | None = None
    ) -> _FakeWikiClient:
        client = _FakeWikiClient(summaries, suggestions)
        monkeypatch.setattr(app_module, "_wiki_client", lambda: client)
        return client

    return _install


class TestPageDetailEndpoint:
    """/api/page: the on-demand lookup behind the node-click detail panel."""

    def test_returns_title_summary_and_url(self, client, fake_wiki_client):
        fake_wiki_client(
            {
                "Cat": {
                    "summary": "Cats are small mammals.",
                    "url": "https://en.wikipedia.org/wiki/Cat",
                }
            }
        )

        response = client.get("/api/page", params={"title": "Cat"})

        assert response.status_code == 200
        assert response.json() == {
            "title": "Cat",
            "summary": "Cats are small mammals.",
            "url": "https://en.wikipedia.org/wiki/Cat",
        }

    def test_404s_for_a_title_with_no_summary(self, client, fake_wiki_client):
        fake_wiki_client({})

        response = client.get("/api/page", params={"title": "Not A Real Page Xyz"})

        assert response.status_code == 404
        assert "message" in response.json()

    @pytest.mark.parametrize("params", [{}, {"title": ""}, {"title": "x" * 201}])
    def test_rejects_bad_title(self, client, params):
        assert client.get("/api/page", params=params).status_code == 422


class TestSuggestEndpoint:
    """/api/suggest: the seed/target autocomplete dropdown's data source."""

    def test_returns_matching_titles(self, client, fake_wiki_client):
        fake_wiki_client({}, {"Cat": ["Cat", "Category theory"]})

        response = client.get("/api/suggest", params={"q": "Cat"})

        assert response.status_code == 200
        assert response.json() == ["Cat", "Category theory"]

    def test_no_matches_is_an_empty_list_not_an_error(self, client, fake_wiki_client):
        fake_wiki_client({}, {})

        response = client.get("/api/suggest", params={"q": "Zzznotarealtitlezzz"})

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "x" * 201}])
    def test_rejects_bad_query(self, client, params):
        assert client.get("/api/suggest", params=params).status_code == 422


def test_config_endpoint_reports_the_knobs(client):
    from wikimap import config

    body = client.get("/api/config").json()
    # Contract 1: the frontend reads these from config, never its own copy.
    assert body["top_k"] == config.TOP_K
    assert body["max_depth"] == config.MAX_DEPTH
    assert body["max_nodes"] == config.MAX_NODES


def test_connect_streams_one_event_per_step(client, fake_algo):
    fake_algo(
        [
            Step(nodes=[Node(id="Cat", score=0.1, depth=0)], note="start"),
            Step(
                nodes=[Node(id="Star", score=0.7, depth=1)],
                edges=[Edge(source="Cat", target="Star")],
                note="Cat -> Star",
            ),
        ]
    )

    response = client.get("/api/connect", params={"seed": "Cat", "target": "Astronomy"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _events(response.text)
    names = [name for name, _ in events]
    assert names == ["status", "step", "step", "done"]

    steps = [payload for name, payload in events if name == "step"]
    assert steps[0]["nodes"][0]["id"] == "Cat"
    assert steps[1]["edges"][0] == {"source": "Cat", "target": "Star"}
    assert steps[1]["note"] == "Cat -> Star"


def test_connect_passes_seed_and_target_through(client, fake_algo):
    algo = fake_algo([Step(note="only")])

    client.get("/api/connect", params={"seed": "Cat", "target": "Astronomy"})

    assert algo.calls == [("Cat", "Astronomy")]


def test_connect_reports_algorithm_failure_in_band(client, monkeypatch):
    """A crash mid-stream can't become a 500 — headers are already sent — so it has
    to arrive as an `error` event instead. Proving that keeps a failed run visible
    in the UI rather than looking like a silent hang."""

    class _Exploding:
        def run(self, seed, target, params=None):
            yield Step(note="first tick")
            raise RuntimeError("wikipedia is on fire")

    monkeypatch.setattr(app_module, "_algorithm", lambda *_: _Exploding())

    response = client.get("/api/connect", params={"seed": "Cat", "target": "Astronomy"})
    events = _events(response.text)
    names = [name for name, _ in events]

    assert names == ["status", "step", "error", "done"]
    assert "wikipedia is on fire" in dict(events)["error"]["message"]


@pytest.mark.parametrize(
    "params",
    [
        {"seed": "Cat"},  # target missing
        {"target": "Astronomy"},  # seed missing
        {"seed": "", "target": "Astronomy"},  # empty seed
    ],
)
def test_connect_rejects_bad_query_params(client, params):
    assert client.get("/api/connect", params=params).status_code == 422


class TestRunParamsOverTheWire:
    """Step 6: knobs travel per request. These pin the three things that make that
    safe — defaults still apply, user values reach the algorithm, and out-of-range
    values are rejected at the edge rather than clamped somewhere invisible."""

    def test_defaults_apply_when_no_knobs_are_given(self, client, fake_algo):
        """The original ?seed=&target= URL must keep working untouched."""
        from wikimap import config

        algo = fake_algo([Step(note="only")])
        client.get("/api/connect", params={"seed": "Cat", "target": "Astronomy"})

        assert algo.params[0] == config.RunParams()
        assert algo.params[0].top_k == config.TOP_K

    def test_user_values_reach_the_algorithm(self, client, fake_algo):
        algo = fake_algo([Step(note="only")])

        client.get(
            "/api/connect",
            params={
                "seed": "Cat",
                "target": "Astronomy",
                "top_k": 5,
                "max_depth": 2,
                "max_nodes": 50,
            },
        )

        assert algo.params[0].top_k == 5
        assert algo.params[0].max_depth == 2
        assert algo.params[0].max_nodes == 50

    def test_config_endpoint_publishes_bounds(self, client):
        """The frontend builds its controls from these, so they can't be absent."""
        from wikimap import config

        bounds = client.get("/api/config").json()["bounds"]

        assert bounds["top_k"] == list(config.TOP_K_BOUNDS)
        assert bounds["max_depth"] == list(config.MAX_DEPTH_BOUNDS)
        assert bounds["max_nodes"] == list(config.MAX_NODES_BOUNDS)

    @pytest.mark.parametrize(
        "knob,value",
        [
            ("top_k", 21),  # above decision C's locked ceiling of 20
            ("top_k", -1),
            ("max_depth", 0),
            ("max_depth", 99),
            ("max_nodes", 1),
            ("max_nodes", 99999),
        ],
    )
    def test_out_of_range_knobs_are_rejected(self, client, knob, value):
        response = client.get(
            "/api/connect",
            params={"seed": "Cat", "target": "Astronomy", knob: value},
        )
        assert response.status_code == 422

    def test_astar_knobs_reach_the_algorithm(self, client, fake_algo):
        algo = fake_algo([Step(note="only")])

        client.get(
            "/api/connect",
            params={
                "seed": "Cat",
                "target": "Astronomy",
                "algorithm": "astar",
                "heuristic_weight": 0.0,
                "hop_scale": 2.5,
            },
        )

        assert algo.params[0].heuristic_weight == 0.0
        assert algo.params[0].hop_scale == 2.5

    def test_concurrent_runs_do_not_share_settings(self, client, fake_algo):
        """The whole reason params are an argument and not module state: two runs
        with different K must not see each other's value."""
        algo = fake_algo([Step(note="only")])

        client.get(
            "/api/connect",
            params={"seed": "Cat", "target": "Astronomy", "top_k": 3},
        )
        client.get(
            "/api/connect",
            params={"seed": "Dog", "target": "Biology", "top_k": 17},
        )

        assert [p.top_k for p in algo.params] == [3, 17]
        # And config itself was never written to.
        from wikimap import config

        assert config.TOP_K == 20


class TestAlgorithmSelection:
    """Step 7: the server offers more than one Connect algorithm."""

    def test_config_publishes_the_registry(self, client):
        from wikimap.algorithms.connect import ALGORITHMS, DEFAULT_ALGORITHM

        body = client.get("/api/config").json()

        assert body["algorithms"] == sorted(ALGORITHMS)
        assert body["default_algorithm"] == DEFAULT_ALGORITHM
        assert "astar" in body["algorithms"]

    def test_name_selects_the_algorithm(self, client, monkeypatch):
        seen: list[str] = []

        class _Recording:
            def run(self, seed, target, params=None):
                yield Step(note="ok")

        monkeypatch.setattr(
            app_module,
            "_algorithm",
            lambda name: (seen.append(name), _Recording())[1],
        )

        client.get(
            "/api/connect",
            params={"seed": "Cat", "target": "Astronomy", "algorithm": "astar"},
        )

        assert seen == ["astar"]

    def test_unknown_algorithm_is_rejected_at_the_edge(self, client):
        """A 422 here rather than a KeyError deep inside _algorithm."""
        response = client.get(
            "/api/connect",
            params={"seed": "Cat", "target": "Astronomy", "algorithm": "nonsense"},
        )
        assert response.status_code == 422

    def test_algorithms_share_one_set_of_caches(self, monkeypatch):
        """Greedy and A* must not each get their own LinkCache — a fresh cache per
        algorithm would mean re-crawling Wikipedia after switching."""
        link_cache, embed_cache = "shared-links", "shared-embeddings"

        # __wrapped__ is the undecorated function — calling it bypasses the lru_cache
        # so this test can't be polluted by, or pollute, other tests' cached instances.
        monkeypatch.setattr(app_module, "_caches", lambda: (link_cache, embed_cache))
        greedy = app_module._algorithm.__wrapped__("greedy")
        astar = app_module._algorithm.__wrapped__("astar")

        assert greedy._link_cache is astar._link_cache is link_cache
        assert greedy._embed_cache is astar._embed_cache is embed_cache
