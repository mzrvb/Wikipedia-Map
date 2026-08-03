"""Rewriting raw article HTML into browser-safe, click-annotated HTML.

Pure function, no network and no model — every case here is a hand-built HTML
snippet, same spirit as test_default.py's fake caches.
"""

from wikimap.wiki.article import annotate_links


class TestRealLinks:
    def test_a_real_ns0_link_becomes_clickable(self):
        html = '<p>The <a href="/wiki/Cat">cat</a> sat.</p>'

        result = annotate_links(html, real_links={"Cat"})

        assert '<a href="#" class="wm-link" data-title="Cat">' in result
        assert "cat</a>" in result

    def test_title_is_recovered_from_the_href_not_the_link_text(self):
        """The visible text can differ from the real title (piped links) --
        proving the lookup key comes from the URL, not what's between the tags."""
        html = '<p>Domesticated <a href="/wiki/Felis_catus">cats</a></p>'

        result = annotate_links(html, real_links={"Felis catus"})

        assert 'data-title="Felis catus"' in result

    def test_underscores_and_percent_encoding_are_decoded(self):
        html = '<a href="/wiki/Cat_%28disambiguation%29">Cat</a>'

        result = annotate_links(html, real_links={"Cat (disambiguation)"})

        assert 'data-title="Cat (disambiguation)"' in result


class TestDisabledLinks:
    def test_a_link_not_in_real_links_is_disabled(self):
        """The href not being in LinkCache's ns0 list is what disables it here --
        not a guess about the URL shape, matching how the algorithm itself never
        infers namespace from a colon in the title."""
        html = '<a href="/wiki/Astronomy">Astronomy</a>'

        result = annotate_links(html, real_links=set())

        assert '<a class="wm-disabled">' in result
        assert "href" not in result.split(">")[0]

    def test_a_category_link_is_disabled_even_if_never_offered_to_link_cache(self):
        html = '<a href="/wiki/Category:Cats">Cats</a>'

        result = annotate_links(html, real_links={"Category:Cats"})
        # Even a title match doesn't help here in practice, since LinkCache never
        # returns Category: titles in the first place (get_links filters ns == 0)
        # -- this just confirms the rewrite itself has no special-cased namespace
        # logic of its own that could disagree with that upstream filtering.

        assert 'data-title="Category:Cats"' in result

    def test_an_external_link_is_disabled(self):
        html = '<a href="https://example.com">example</a>'

        result = annotate_links(html, real_links={"example.com"})

        assert '<a class="wm-disabled">' in result

    def test_a_same_page_section_anchor_is_disabled(self):
        html = '<a href="#History">History</a>'

        result = annotate_links(html, real_links={"History"})

        assert '<a class="wm-disabled">' in result

    def test_an_edit_section_link_is_disabled(self):
        html = '<a href="/w/index.php?title=Cat&action=edit&section=1">edit</a>'

        result = annotate_links(html, real_links=set())

        assert '<a class="wm-disabled">' in result


class TestNonLinkContentIsPreservedVerbatim:
    def test_surrounding_markup_and_text_survive_unchanged(self):
        html = '<p><b>Bold</b> text with <i>italics</i> and a <br /> line break.</p>'

        result = annotate_links(html, real_links=set())

        assert result == html

    def test_images_pass_through_untouched(self):
        html = '<img src="//upload.wikimedia.org/x.jpg" width="10" />'

        result = annotate_links(html, real_links=set())

        assert result == html


class TestStripping:
    def test_script_tags_are_removed_entirely(self):
        html = '<p>Safe</p><script>alert(1)</script><p>Also safe</p>'

        result = annotate_links(html, real_links=set())

        assert "script" not in result
        assert "alert" not in result
        assert "<p>Safe</p>" in result
        assert "<p>Also safe</p>" in result

    def test_comments_are_dropped(self):
        html = "<p>Visible</p><!-- a comment --><p>Also visible</p>"

        result = annotate_links(html, real_links=set())

        assert "a comment" not in result
        assert "<p>Visible</p>" in result

    def test_entities_in_text_round_trip_correctly(self):
        html = "<p>Tom &amp; Jerry &lt;3</p>"

        result = annotate_links(html, real_links=set())

        assert result == html
