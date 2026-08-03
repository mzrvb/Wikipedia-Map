"""The FastAPI server and its SSE stream (roadmap step 5).

All fast: `_algorithm` is monkeypatched to a fake that yields canned Steps, so no
Wikipedia call and no model load ever happens. That substitution is exactly what the
ABC buys us — the server only ever calls `run(seed, target)`, so anything with that
method can stand in for DefaultConnect.
"""

import json

import pytest
from fastapi.testclient import TestClient

from wikimap.graph.contracts import Edge, Node, Step
from wikimap.server import app as app_module


class _FakeAlgorithm:
    """Stand-in for DefaultConnect: yields whatever Steps the test hands it."""

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
        # `lambda *_:` because _algorithm still takes the algorithm name (just
        # always DEFAULT_ALGORITHM now — see algorithms/connect/__init__.py).
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
    search_titles looks up a canned query -> title-list table. Every endpoint that
    uses this fixture (/api/page, /api/suggest, /api/article) shares the one
    WikiClient singleton in real code, so one fake covers all three here too."""

    def __init__(
        self,
        summaries: dict[str, dict],
        suggestions: dict[str, list[str]] | None = None,
        articles: dict[str, str] | None = None,
    ):
        self._summaries = summaries
        self._suggestions = suggestions or {}
        self._articles = articles or {}

    def get_summary(self, title: str) -> dict | None:
        return self._summaries.get(title)

    def search_titles(self, query: str) -> list[str]:
        return self._suggestions.get(query, [])

    def get_article_html(self, title: str) -> str | None:
        return self._articles.get(title)


class _StubLinkCache:
    """Minimal LinkCache stand-in for /api/article: get_links looks up a canned
    title -> ns0-links table. A plain class, not a fake with backlinks/caching
    behavior, since /api/article only ever calls get_links."""

    def __init__(self, links: dict[str, list[str]]):
        self._links = links

    def get_links(self, title: str) -> list[str]:
        return self._links.get(title, [])


def _stub_link_cache(links: dict[str, list[str]]) -> _StubLinkCache:
    return _StubLinkCache(links)


@pytest.fixture
def fake_wiki_client(monkeypatch):
    def _install(
        summaries: dict[str, dict],
        suggestions: dict[str, list[str]] | None = None,
        articles: dict[str, str] | None = None,
    ) -> _FakeWikiClient:
        client = _FakeWikiClient(summaries, suggestions, articles)
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


class TestArticleEndpoint:
    """/api/article: real rendered HTML with links marked real/inert, behind
    Connect's human-play mode."""

    def test_returns_title_and_annotated_html(self, client, fake_wiki_client, monkeypatch):
        fake_wiki_client(
            {}, articles={"Cat": '<p>The <a href="/wiki/Felidae">family</a> lives on.</p>'}
        )
        link_cache = _stub_link_cache({"Cat": ["Felidae"]})
        monkeypatch.setattr(app_module, "_caches", lambda: (link_cache, None))

        response = client.get("/api/article", params={"title": "Cat"})

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Cat"
        assert 'class="wm-link" data-title="Felidae"' in body["html"]

    def test_a_link_link_cache_does_not_know_about_is_disabled(
        self, client, fake_wiki_client, monkeypatch
    ):
        fake_wiki_client(
            {}, articles={"Cat": '<a href="/wiki/Category:Cats">Cats</a>'}
        )
        link_cache = _stub_link_cache({"Cat": []})  # get_links already drops ns != 0
        monkeypatch.setattr(app_module, "_caches", lambda: (link_cache, None))

        response = client.get("/api/article", params={"title": "Cat"})

        assert 'class="wm-disabled"' in response.json()["html"]

    def test_404s_for_a_title_with_no_article(self, client, fake_wiki_client, monkeypatch):
        fake_wiki_client({}, articles={})
        monkeypatch.setattr(app_module, "_caches", lambda: (_stub_link_cache({}), None))

        response = client.get("/api/article", params={"title": "Not A Real Page Xyz"})

        assert response.status_code == 404
        assert "message" in response.json()

    @pytest.mark.parametrize("params", [{}, {"title": ""}, {"title": "x" * 201}])
    def test_rejects_bad_title(self, client, params):
        assert client.get("/api/article", params=params).status_code == 422


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
            },
        )

        assert algo.params[0].top_k == 5
        assert algo.params[0].max_depth == 2

    def test_config_endpoint_publishes_bounds(self, client):
        """The frontend builds its controls from these, so they can't be absent."""
        from wikimap import config

        bounds = client.get("/api/config").json()["bounds"]

        assert bounds["top_k"] == list(config.TOP_K_BOUNDS)
        assert bounds["max_depth"] == list(config.MAX_DEPTH_BOUNDS)

    @pytest.mark.parametrize(
        "knob,value",
        [
            ("top_k", 21),  # above decision C's locked ceiling of 20
            ("top_k", -1),
            ("max_depth", 0),
            ("max_depth", 99),
        ],
    )
    def test_out_of_range_knobs_are_rejected(self, client, knob, value):
        response = client.get(
            "/api/connect",
            params={"seed": "Cat", "target": "Astronomy", knob: value},
        )
        assert response.status_code == 422

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


class TestAlgorithmRegistry:
    """The `algorithm` HTTP param and multi-algorithm selection were removed
    2026-07-31 (greedy/astar stripped — see algorithms/connect/__init__.py and
    HISTORY), but `_algorithm(name)` and the `ALGORITHMS` registry stay in shape
    so a genuinely new algorithm could still drop in without restructuring this
    module. These two tests pin what's left of that shape.
    """

    def test_default_algorithm_is_the_only_registry_entry(self):
        from wikimap.algorithms.connect import ALGORITHMS, DEFAULT_ALGORITHM

        assert list(ALGORITHMS) == [DEFAULT_ALGORITHM]

    def test_algorithm_lookups_share_one_set_of_caches(self, monkeypatch):
        """A fresh cache per lookup would mean re-crawling Wikipedia on every call —
        `_algorithm` must keep handing back caches built once by `_caches()`."""
        link_cache, embed_cache = "shared-links", "shared-embeddings"

        # __wrapped__ is the undecorated function — calling it bypasses the lru_cache
        # so this test can't be polluted by, or pollute, other tests' cached instances.
        monkeypatch.setattr(app_module, "_caches", lambda: (link_cache, embed_cache))
        first = app_module._algorithm.__wrapped__("default")
        second = app_module._algorithm.__wrapped__("default")

        assert first._link_cache is second._link_cache is link_cache
        assert first._embed_cache is second._embed_cache is embed_cache
