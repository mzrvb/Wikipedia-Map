"""Data layer: ns0 filtering, User-Agent is set, and the two-layer cache.

Roadmap step 1 must prove: a known page returns ns0-only links, the UA is sent,
a second call hits the cache without network, and the cache survives a restart.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from wikimap.wiki.cache import LinkCache
from wikimap.wiki.client import WikiClient


def _fake_page(links: dict[str, int]):
    """Fake wikipediaapi page whose .links maps title -> object with .ns."""
    page = MagicMock()
    page.links = {title: MagicMock(ns=ns) for title, ns in links.items()}
    return page


class TestWikiClient:
    def test_missing_user_agent_raises(self, monkeypatch):
        monkeypatch.delenv("USER_AGENT", raising=False)
        with pytest.raises(RuntimeError):
            WikiClient()

    def test_get_links_filters_to_namespace_zero(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient()
        client._wiki.page = MagicMock(
            return_value=_fake_page(
                {
                    "Aliens: The Ride": 0,  # real article, contains a colon
                    "Category:Films": 14,  # namespace to drop
                    "Talk:Python": 1,  # namespace to drop
                    "Python (programming language)": 0,
                }
            )
        )

        links = client.get_links("Python (programming language)")

        assert set(links) == {"Aliens: The Ride", "Python (programming language)"}

    def test_user_agent_passed_to_wikipediaapi(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "wikimap-test/0.1 (test@example.com)")
        with patch("wikimap.wiki.client.wikipediaapi.Wikipedia") as mock_wiki:
            WikiClient()
        _, kwargs = mock_wiki.call_args
        assert kwargs["user_agent"] == "wikimap-test/0.1 (test@example.com)"

    def test_get_links_retries_then_gives_up(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient(retries=2, delay=0)
        client._wiki.page = MagicMock(side_effect=RuntimeError("boom"))

        assert client.get_links("Anything") == []
        assert client._wiki.page.call_count == 2


class TestGetSummary:
    """The lookup behind the node-click detail panel — a title's real summary text
    and article URL, fetched on demand rather than during a search run."""

    def test_returns_summary_and_url_for_an_existing_page(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient()
        page = MagicMock()
        page.summary = "Cats are small mammals."
        page.exists.return_value = True
        page.fullurl = "https://en.wikipedia.org/wiki/Cat"
        client._wiki.page = MagicMock(return_value=page)

        result = client.get_summary("Cat")

        assert result == {
            "summary": "Cats are small mammals.",
            "url": "https://en.wikipedia.org/wiki/Cat",
        }

    def test_returns_none_for_a_nonexistent_page(self, monkeypatch):
        """.fullurl is only worth the "info" API call for a page that exists — a
        plain class (not MagicMock) so the property access is unmissable, and
        recorded rather than raised: get_summary's except is deliberately broad
        (matching get_links), so a raise here would just be retried and swallowed,
        silently passing the test whether or not the bug it's checking for exists."""
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient()
        accessed = []

        class _NonexistentPage:
            summary = ""

            def exists(self):
                return False

            @property
            def fullurl(self):
                accessed.append(True)
                return "unexpected"

        client._wiki.page = MagicMock(return_value=_NonexistentPage())

        assert client.get_summary("Not A Real Page Xyz") is None
        assert not accessed

    def test_fetches_off_one_page_object(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient()
        page = MagicMock()
        page.summary = "Summary."
        page.exists.return_value = True
        page.fullurl = "https://en.wikipedia.org/wiki/Cat"
        client._wiki.page = MagicMock(return_value=page)

        client.get_summary("Cat")

        client._wiki.page.assert_called_once_with("Cat")

    def test_retries_then_gives_up(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient(retries=2, delay=0)
        client._wiki.page = MagicMock(side_effect=RuntimeError("boom"))

        assert client.get_summary("Anything") is None
        assert client._wiki.page.call_count == 2


def _api_response(titles: list[str], continue_token: str | None = None):
    """Fake requests.Response for a list=backlinks query."""
    payload = {"query": {"backlinks": [{"title": t} for t in titles]}}
    if continue_token:
        payload["continue"] = {"blcontinue": continue_token}
    response = MagicMock()
    response.json.return_value = payload
    return response


class TestBacklinks:
    """The backward half of bidirectional search.

    These pin the two library bugs get_backlinks exists to avoid: unbounded
    pagination, and namespace filtering being dropped on continuation requests.
    """

    def test_returns_titles_and_filters_namespace_server_side(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient()

        with patch("wikimap.wiki.client.requests.get") as mock_get:
            mock_get.return_value = _api_response(["Cat", "Aliens: The Ride"])
            backlinks = client.get_backlinks("Astronomy")

        assert backlinks == ["Cat", "Aliens: The Ride"]
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["blnamespace"] == 0
        assert kwargs["params"]["bltitle"] == "Astronomy"
        assert kwargs["headers"]["User-Agent"] == "test/0.0 (test@example.com)"

    def test_stops_at_limit_instead_of_paginating_forever(self, monkeypatch):
        """The library's version loops until the API stops offering a continue
        token. A page like "Cat" would page through six figures of backlinks."""
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient()

        # Every response offers another continue token — an infinite feed.
        with patch("wikimap.wiki.client.requests.get") as mock_get:
            mock_get.side_effect = lambda *a, **k: _api_response(
                ["A", "B", "C"], continue_token="more"
            )
            backlinks = client.get_backlinks("Cat", limit=7)

        assert len(backlinks) == 7
        assert mock_get.call_count == 3  # 3+3+3 = 9 collected, truncated to 7

    def test_namespace_filter_survives_continuation(self, monkeypatch):
        """wikipediaapi rebuilds continuation requests from the original params and
        drops kwargs, so its ns filter applies to page 1 only. Ours must not."""
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient()

        with patch("wikimap.wiki.client.requests.get") as mock_get:
            mock_get.side_effect = [
                _api_response(["A"], continue_token="page2"),
                _api_response(["B"]),
            ]
            client.get_backlinks("Astronomy", limit=500)

        second_call_params = mock_get.call_args_list[1].kwargs["params"]
        assert second_call_params["blnamespace"] == 0
        assert second_call_params["blcontinue"] == "page2"

    def test_retries_then_gives_up(self, monkeypatch):
        monkeypatch.setenv("USER_AGENT", "test/0.0 (test@example.com)")
        client = WikiClient(retries=2, delay=0)

        with patch("wikimap.wiki.client.requests.get") as mock_get:
            mock_get.side_effect = RuntimeError("boom")
            assert client.get_backlinks("Anything") == []

        assert mock_get.call_count == 2


class TestLinkCache:
    def test_second_call_hits_memory_not_network(self, tmp_path):
        client = MagicMock()
        client.get_links.return_value = ["A", "B"]
        cache = LinkCache(client, data_dir=tmp_path)

        first = cache.get_links("Some Page")
        second = cache.get_links("Some Page")

        assert first == second == ["A", "B"]
        client.get_links.assert_called_once_with("Some Page")

    def test_cache_survives_restart_via_disk(self, tmp_path):
        client = MagicMock()
        client.get_links.return_value = ["A", "B"]
        LinkCache(client, data_dir=tmp_path).get_links("Some Page")

        # Fresh instance, same directory, empty in-memory dict, and a client that
        # errors if called — proves the disk layer alone is what serves this.
        cold_client = MagicMock()
        cold_client.get_links.side_effect = AssertionError("should not hit network")
        cold_cache = LinkCache(cold_client, data_dir=tmp_path)

        assert cold_cache.get_links("Some Page") == ["A", "B"]
        cold_client.get_links.assert_not_called()

    def test_writes_json_to_disk(self, tmp_path):
        client = MagicMock()
        client.get_links.return_value = ["A", "B"]
        cache = LinkCache(client, data_dir=tmp_path)

        cache.get_links("Aliens: The Ride")

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert json.loads(files[0].read_text()) == ["A", "B"]

    def test_backlinks_cache_the_same_way(self, tmp_path):
        client = MagicMock()
        client.get_backlinks.return_value = ["Cat", "Dog"]
        cache = LinkCache(
            client, data_dir=tmp_path / "links", backlink_dir=tmp_path / "backlinks"
        )

        first = cache.get_backlinks("Astronomy")
        second = cache.get_backlinks("Astronomy")

        assert first == second == ["Cat", "Dog"]
        client.get_backlinks.assert_called_once_with("Astronomy")
        assert (tmp_path / "backlinks").glob("*.json")

    def test_directions_do_not_share_a_namespace(self, tmp_path):
        """Both directions are "a list of titles related to X". If they shared a
        cache key, asking for links would plausibly return backlinks instead."""
        client = MagicMock()
        client.get_links.return_value = ["forward"]
        client.get_backlinks.return_value = ["backward"]
        cache = LinkCache(
            client, data_dir=tmp_path / "links", backlink_dir=tmp_path / "backlinks"
        )

        assert cache.get_links("Astronomy") == ["forward"]
        assert cache.get_backlinks("Astronomy") == ["backward"]
        # And again, now that both layers are warm.
        assert cache.get_links("Astronomy") == ["forward"]
        assert cache.get_backlinks("Astronomy") == ["backward"]
