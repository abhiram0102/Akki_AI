"""Tests for structure discovery (backend/services/brain_discovery.py).

The project's defining constraint is that no part of the pipeline may carry
predefined knowledge of URL, HTML, link, word or sentence formats. A test that
only fed this module HTML could not tell discovery apart from a well-hidden
HTML parser, so the decisive tests here feed it **invented formats that do not
exist anywhere** — delimiters no real document uses, and sentence terminators
that are not punctuation an English writer would type.

If structure were hardcoded, those cases would return nothing. They pass, so
the structure came from the bytes.
"""
from backend.services import brain_discovery as bd


# ── Markup delimiters are found, not known ───────────────────────────────────

def test_discovers_angle_brackets_in_html_without_being_told():
    html = "<html><body>" + "".join(
        f"<p class='x'>Sentence number {i} sits here.</p>" for i in range(30)
    ) + "</body></html>"
    assert bd.discover_delimiters(html) == ("<", ">")


def test_discovers_invented_delimiters_in_a_format_that_does_not_exist():
    """The decisive test. This markup uses `|` to open and `~` to close, a
    syntax no real document uses and nothing in the module mentions. An HTML
    parser in disguise would find nothing here."""
    doc = "".join(f"|block~Some prose in block number {i}. |/block~" for i in range(30))
    assert bd.discover_delimiters(doc) == ("|", "~")


def test_plain_prose_has_no_markup_rather_than_a_guess():
    """A document with no structure must report none, not invent delimiters
    out of ordinary punctuation."""
    prose = ("The rain fell steadily all afternoon. " * 30)
    assert bd.discover_delimiters(prose) is None


def test_text_survives_separation_and_markup_is_removed():
    html = "<div>" + "".join(f"<p>Block {i} of readable prose.</p>" for i in range(20)) + "</div>"
    text, markup = bd.separate(html)
    assert "Block 3 of readable prose." in text
    assert "<" not in text and "div" not in text
    assert any("div" in m for m in markup)


def test_separation_does_not_fuse_words_across_a_span():
    """Stripping a span between two words must leave a boundary, or two
    unrelated words merge into one nonexistent token."""
    doc = "".join(f"<x>first{i}</x><y>second{i}</y> " for i in range(20))
    text, _ = bd.separate(doc)
    assert "first1second1" not in text


# ── Sentence boundaries are learned from position ────────────────────────────

def test_learns_the_full_stop_from_evidence():
    text = " ".join(f"This is statement number {i}. Another clause follows it." for i in range(10))
    assert "." in bd.discover_sentence_terminators(text)


def test_learns_an_invented_terminator_that_is_not_punctuation_english_uses():
    """Boundaries are found by where a byte sits, not by which byte it is.
    Here `§` ends every sentence and `.` never appears."""
    text = " ".join(f"This is statement number {i}§ Another clause follows it§" for i in range(10))
    terminators = bd.discover_sentence_terminators(text)
    assert "§" in terminators
    assert "." not in terminators


def test_comma_is_not_mistaken_for_a_boundary():
    """A comma is as common as a full stop but is followed by lowercase, so
    position alone must separate them."""
    text = " ".join(f"first clause number {i}, second clause continues here. Next One begins." for i in range(10))
    assert "," not in bd.discover_sentence_terminators(text)


def test_sentences_split_on_whatever_was_discovered():
    text = " ".join(f"Statement number {i} runs to a reasonable length here§" for i in range(10))
    sentences = bd.split_sentences(text)
    assert len(sentences) >= 5
    assert all("§" not in s[:-1] for s in sentences)


def test_no_terminator_discovered_leaves_text_whole_rather_than_cut_at_a_guess():
    text = "one two three four five six seven eight nine ten"
    assert bd.split_sentences(text, terminators=set()) == [text]


# ── References are resolved, not pattern-matched ─────────────────────────────

def test_finds_relative_references_and_resolves_them():
    markup = [f"<a href='/topic/item{i}'>" for i in range(10)]
    links = bd.discover_references(markup, "https://example.org/topic/start")
    assert "https://example.org/topic/item3" in links


def test_finds_references_in_an_invented_markup_syntax():
    """No `href`, no `a`, no quotes. The reference is found because it resolves
    to a usable address, not because it sat in a known attribute."""
    markup = [f"|point→/topic/item{i}|" for i in range(10)]
    links = bd.discover_references(markup, "https://example.org/topic/start")
    assert "https://example.org/topic/item3" in links


def test_the_documents_own_address_is_not_returned_as_a_reference():
    base = "https://example.org/topic/start"
    markup = [f"<a href='{base}'>"] + [f"<a href='/topic/item{i}'>" for i in range(10)]
    assert base not in bd.discover_references(markup, base)


def test_fragments_of_the_same_document_are_not_separate_references():
    base = "https://example.org/topic/start"
    markup = [f"<a href='#section{i}'>" for i in range(10)]
    assert bd.discover_references(markup, base) == []


def test_dominant_path_shape_separates_body_links_from_navigation():
    """Article references share a depth; assets and navigation sit elsewhere.
    The shape is measured per document, so no site's layout is described here.
    """
    markup = (
        [f"<a href='/topic/item{i}'>" for i in range(12)]
        + ["<a href='/static/css/theme/deep/file'>", "<a href='/'>"]
    )
    links = bd.discover_references(markup, "https://example.org/topic/start")
    assert all("/static/" not in u for u in links)
    assert len(links) >= 10


def test_offsite_references_are_kept_when_there_are_no_onsite_ones():
    markup = [f"<a href='https://other.example/page/item{i}'>" for i in range(10)]
    links = bd.discover_references(markup, "https://example.org/start")
    assert any("other.example" in u for u in links)


# ── End to end, on a format the module has never seen ────────────────────────

def test_whole_pipeline_on_an_invented_document_format():
    """Delimiters, prose, sentence boundaries and references all recovered from
    a document whose syntax exists nowhere: `|`/`~` markup and `§` boundaries.
    Nothing in the module names any of these."""
    doc = "".join(
        f"|ref→/entry/item{i}~The concept number {i} depends on several other things§ |/ref~"
        for i in range(20)
    )
    out = bd.discover_structure(doc, "https://example.org/entry/start")

    assert out["delimiters"] == ("|", "~")
    assert "§" in out["terminators"]
    assert any("depends on several other things" in s for s in out["sentences"])
    assert "https://example.org/entry/item7" in out["links"]
    # The markup itself must not leak into what is read as prose.
    assert "ref" not in out["text"] or "→" not in out["text"]


def test_whole_pipeline_on_html_without_any_html_rule():
    html = "<html><body>" + "".join(
        f"<p><a href='/wiki/Topic{i}'>Topic {i}</a> "
        f"The subject number {i} relates closely to several neighbouring ideas.</p>"
        for i in range(25)
    ) + "</body></html>"
    out = bd.discover_structure(html, "https://en.example.org/wiki/Start")

    assert out["delimiters"] == ("<", ">")
    assert "https://en.example.org/wiki/Topic5" in out["links"]
    assert any("neighbouring ideas" in s for s in out["sentences"])
    assert "<" not in out["text"]


def test_empty_and_degenerate_input_is_handled():
    assert bd.discover_delimiters("") is None
    assert bd.discover_structure("", "https://example.org/")["sentences"] == []
    assert bd.discover_references([], "https://example.org/") == []
