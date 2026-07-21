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
