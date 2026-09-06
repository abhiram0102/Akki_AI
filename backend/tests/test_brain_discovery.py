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
from collections import Counter
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


# ── Boundary discovery has to survive a noisy real page ──────────────────────

def test_a_frequent_terminator_beats_a_rare_but_consistent_artifact():
    """Measured on a real article: the full stop preceded 681 boundaries at a
    29% rate, while a navigation arrow appearing 105 times preceded one 91% of
    the time. Judging by rate alone picks the arrow and discards the full stop,
    which is exactly backwards, so evidence has to count too."""
    prose = " ".join(
        f"This is statement number {i} and it runs on. Another clause follows it."
        for i in range(40)
    )
    # A rare artifact that is almost always followed by a capitalised word.
    artifact = " ".join(f"^ Jump up{i} ^ Back{i}" for i in range(8))
    terminators = bd.discover_sentence_terminators(prose + " " + artifact)
    assert "." in terminators
    assert "^" not in terminators


def test_code_and_data_are_not_read_as_statements():
    """Script and data embedded in a page sit OUTSIDE the markup delimiters,
    so they survive separation and would otherwise be learned from as prose."""
    subjects = ["leaf", "stem", "root", "frond", "thallus", "blade"]
    text = (
        'var className="client-js vector-feature-enabled", wgPageAssessments={"Algae":'
        '{"class":"B","importance":"Top"}}, x=0. '
        + " ".join(f"Photosynthesis converts light into chemical energy in the {s}."
                   for s in subjects)
    )
    sentences = bd.split_sentences(text)
    assert any("Photosynthesis converts light" in s for s in sentences)
    assert not any("wgPageAssessments" in s or "className" in s for s in sentences)


def test_a_sentence_ending_in_a_single_digit_is_missed():
    """A known and deliberate cost of `_MIN_CLOSING_WORD`, pinned here so it
    stays visible.

    A statement ending on a one-digit number is indistinguishable, by anything
    local to the boundary, from a numbered heading like "History of the issue
    2." -- both are a lone digit, a full stop, a space and a capital. Admitting
    one admits the other, and on the stored corpus admitting both put two dozen
    heading fragments back into the encyclopedia page. Headings are far more
    common in crawled pages than sentences ending in a bare digit, so the
    trade is made deliberately in that direction.

    This test asserts the CURRENT behaviour, not the desired one. If a later
    change makes both cases separable -- by looking at the document's structure
    rather than at the boundary alone -- this test should start failing, and
    the right response is to delete it, not to restore the limitation."""
    text = " ".join(f"The reaction releases oxygen at stage {i}." for i in range(6))
    sentences = bd.split_sentences(text)
    assert sentences == [] or all("stage" not in s for s in sentences)


def test_headings_numbered_in_sequence_are_not_read_as_statements():
    """The other side of the same trade: a run of numbered headings must not
    arrive at the extractor as sentences, because a parser will invent
    subject-verb structure from any noun phrase handed to it."""
    text = (
        "Concepts of Consciousness 2. History of the issue 3. "
        "Consciousness as an entity 4. The descriptive question 5."
    )
    sentences = bd.split_sentences(text, terminators={"."})
    assert not any("History of the issue" == s.strip(" .") for s in sentences)


def test_an_abbreviation_does_not_end_a_statement():
    """The byte that ends sentences also sits inside "e.g." and "U.S.".
    Splitting on the byte alone cuts those in half and hands the extractor a
    fragment ending in a stray letter, which is where two of the corpus's
    false positives came from."""
    text = (
        "Perception counts as a conscious state because it involves qualia, "
        "e.g. the taste of wine. The U.S. Congress met later that year. "
        "Consciousness remains difficult to define precisely."
    )
    sentences = bd.split_sentences(text)
    assert not any(s.rstrip(".").endswith(" e") for s in sentences)
    assert not any(s.rstrip(".").endswith(" U.S") for s in sentences)
    assert any("taste of wine" in s for s in sentences)


def test_a_bracketing_pair_is_not_mistaken_for_a_terminator():
    """A bracket is half of a pair: something else occurs about as often and
    nests with it. A terminator has no such partner. That difference is what
    tells them apart here -- no byte is named, so a document that brackets with
    some other pair of symbols is judged the same way.

    Without this, a page carrying little prose lets its brackets outscore the
    real terminator, and the reader gets navigation fragments instead of the
    one paragraph on the page worth reading."""
    prose = " ".join(
        f"The system converts light into chemical energy in the {part} "
        f"(as reported in {1990 + i}). "
        for i, part in enumerate(["leaf", "stem", "root", "frond", "blade", "thallus"])
    )
    terminators = bd.discover_sentence_terminators(prose)
    openers = {t for t in terminators if bd._bracket_partner(
        prose, t, Counter(c for c in prose if not c.isalnum() and not c.isspace()))}
    assert not openers, f"a bracketing byte was taken for a terminator: {openers}"


def test_a_standalone_glyph_is_not_a_terminator_however_well_it_behaves():
    """The measured failure this guards against: on a real Wikipedia page a
    jump-back arrow precedes a capital letter in 95 out of 95 appearances,
    which is better boundary behaviour than the full stop manages on the same
    page. Position statistics alone therefore prefer the arrow.

    What separates them is that punctuation is written against the word it
    follows and a standalone glyph never is. The arrow here is not named; it is
    excluded because it is attached to a word in none of its appearances."""
    glyph = "\u2191"
    text = " ".join(
        f"Light is absorbed by the reaction centre in the {part}. {glyph} "
        f"Energy then moves through the chain of carriers."
        for part in ["leaf", "stem", "root", "frond", "blade", "thallus"]
    )
    terminators = bd.discover_sentence_terminators(text)
    assert glyph not in terminators
    assert "." in terminators


def test_the_split_uses_the_same_test_that_found_the_terminator():
    """The bug this closes: terminators were found by looking at context and
    then applied to every occurrence of the byte, context discarded. The two
    have to agree, or the split cuts in places the search would never have
    called boundaries."""
    text = (
        "Photosynthesis converts light into chemical energy in the leaf. "
        "Version 2.5 of the model was released. The reaction then continues."
    )
    sentences = bd.split_sentences(text, terminators={"."})
    # The period inside "2.5" is the same byte as the one ending the sentence
    # before it. Only the context tells them apart, so the version number must
    # arrive whole.
    assert any("Version 2.5 of the model was released" in s for s in sentences)
    assert not any(s.endswith("Version 2.") for s in sentences)
