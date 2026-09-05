"""Tests for query understanding (backend/services/brain_query.py).

The point these tests have to prove is not "the router works" but that the
DIRECTION of the graph traversal is derived from the grammatical role the
user's concept plays in the sentence, rather than from matching question words.
The decisive cases are the pairs below that use the SAME verb and the SAME two
nouns and differ only in who is the subject — a word-list classifier cannot
tell those apart, so passing them is evidence the structure came from the
parse. Requires the spaCy model the graph writer already uses; no Neo4j.
"""
import pytest

from backend.services import brain_query


def test_bare_concept_is_unchanged_define():
    """Back-compat: the old API posted a bare concept and got a lookup. That
    must still parse to a single-topic DEFINE."""
    plan = brain_query.parse("inflation")
    assert plan.intent == brain_query.DEFINE
    assert plan.primary == "inflation"


def test_full_question_is_not_treated_as_a_node_key():
    """The original defect: the whole sentence was used as a Neo4j node key.
    Parsing must reduce it to the concept actually being asked about."""
    plan = brain_query.parse("why does inflation happen")
    assert plan.primary == "inflation"
    assert plan.raw != plan.primary


# ── Direction from grammatical role, not from vocabulary ─────────────────────

def test_object_of_causal_verb_asks_for_incoming_edges():
    """"what causes inflation" — inflation is the OBJECT, so the unknown is
    upstream of it: read what it depends on."""
    plan = brain_query.parse("what causes inflation")
    assert plan.intent == brain_query.CAUSE


def test_subject_of_same_verb_asks_for_outgoing_edges():
    """Same verb, same noun, opposite role. "what does inflation cause" puts
    inflation in the SUBJECT slot, so the unknown is downstream.

    This is the test a hardcoded question-word map cannot pass: both sentences
    contain "what" and "cause", so only the dependency parse separates them.
    """
    plan = brain_query.parse("what does inflation cause")
    assert plan.intent == brain_query.EFFECT


def test_causal_pair_disagree_on_direction():
    """State the invariant directly: identical vocabulary, opposite traversal."""
    forward = brain_query.parse("what does inflation cause")
    backward = brain_query.parse("what causes inflation")
    assert forward.intent != backward.intent
    assert forward.primary == backward.primary == "inflation"


def test_backward_connective_flips_direction_again():
    """"require" is a BACKWARD connective in brain_nlp: its subject is the
    dependent, so its subject's prerequisites are upstream. Asking what X
    requires must therefore read incoming edges, the opposite of what the
    subject role gives for a forward verb."""
    plan = brain_query.parse("what does encryption require")
    assert plan.intent == brain_query.CAUSE


# ── Concept count drives multi-topic intents ─────────────────────────────────

def test_two_concepts_route_to_pairwise_convergence():
    plan = brain_query.parse("how are inflation and unemployment connected")
    assert plan.intent == brain_query.RELATE
    assert len(plan.topics) >= 2


def test_three_concepts_route_to_multi_origin_convergence():
    plan = brain_query.parse("inflation, unemployment and taxation")
    assert plan.intent == brain_query.EXPLORE
    assert len(plan.topics) >= 3


def test_how_with_one_concept_is_a_description_not_a_relation():
    """The word "how" alone does not decide the intent — concept count does.
    "how does X work" describes one thing; it must not route to a two-endpoint
    convergence query that has no second endpoint."""
    plan = brain_query.parse("how does photosynthesis work")
    assert plan.intent == brain_query.DEFINE


def test_relate_never_emitted_without_two_endpoints():
    """Guard the invariant rather than one phrasing: whatever the wording, a
    RELATE plan always carries the two concepts its graph query requires."""
    for text in ["how does photosynthesis work", "why does inflation happen", "inflation"]:
        plan = brain_query.parse(text)
        if plan.intent == brain_query.RELATE:
            assert plan.secondary is not None


# ── Normalization must match the graph writer ────────────────────────────────

def test_topics_use_the_graph_writers_own_normalizer():
    """A term extracted from a question has to be spelled exactly like the node
    key written when that concept was learned, or a concept the brain genuinely
    knows is unreachable. Both sides go through brain_nlp._concept_from_token,
    so a multi-word phrase must survive as one concept rather than fragmenting.
    """
    plan = brain_query.parse("what is machine learning")
    assert "machine learning" in plan.topics


def test_interrogatives_are_never_concepts():
    """spaCy will hand back "what" as a pronoun; it must not become a node key."""
    plan = brain_query.parse("what is inflation")
    assert "what" not in plan.topics


def test_empty_query_does_not_crash():
    plan = brain_query.parse("")
    assert plan.topics == []
    assert plan.intent == brain_query.DEFINE


def test_unrecognised_word_still_becomes_the_concept():
    """Regression: spaCy does not tag rare technical words as nouns, so the
    noun-phrase normalizer returned nothing and the whole question stood in as
    the concept — the brain answered "I don't know what is quasicrystal".
    Grammar words must be stripped and the remainder used as the subject."""
    plan = brain_query.parse("what is quasicrystal")
    assert plan.topics == ["quasicrystal"]
    assert plan.primary == "quasicrystal"


def test_fallback_never_keeps_grammar_words_as_concepts():
    """The fallback must strip auxiliaries and interrogatives, not just splice
    the sentence back together."""
    plan = brain_query.parse("what is quasicrystal")
    assert not {"what", "be", "is"} & set(plan.topics)


def test_modifier_survives_when_the_chunker_fails_on_a_question():
    """Regression: spaCy chunks "what is dark matter" as just "what", so the
    head noun alone came back and the query looked up "matter" while the
    article that taught it stored "dark matter" — a guaranteed miss on a
    concept the brain actually knows. The modifier is recovered from the parse."""
    assert brain_query.parse("what is dark matter").primary == "dark matter"


def test_question_and_bare_phrase_agree_on_the_concept():
    """However it is asked, the same phrase must normalize to the same node key."""
    assert brain_query.parse("what is dark matter").primary == brain_query.parse("dark matter").primary
