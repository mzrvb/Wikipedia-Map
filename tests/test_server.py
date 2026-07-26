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

    def run(self, seed: str, target: str):
        self.calls.append((seed, target))
        yield from self._steps


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture
def fake_algo(monkeypatch):
    """Install a fake algorithm and return it, so tests can assert on its calls."""

    def _install(steps: list[Step]) -> _FakeAlgorithm:
        algo = _FakeAlgorithm(steps)
        monkeypatch.setattr(app_module, "_algorithm", lambda: algo)
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
        def run(self, seed, target):
            yield Step(note="first tick")
            raise RuntimeError("wikipedia is on fire")

    monkeypatch.setattr(app_module, "_algorithm", lambda: _Exploding())

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
