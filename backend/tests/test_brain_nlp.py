"""Tests for spaCy-based dependency extraction. Requires en_core_web_sm
(installed via `python -m spacy download en_core_web_sm`) — these are
integration tests against the real parser, not mocks, since the whole point
is real dependency structure.

Expected values below were derived from the actual dependency parse observed
by running spaCy on each fixture sentence (token/dep_/head_/lemma_), not
guessed. See task-4-report.md for the full recorded parse output.
"""
from backend.services.brain_nlp import extract_dependencies


def test_forward_connective_cause_effect():
    # "Fire causes heat" -> fire is the cause, heat is the effect
    # Parse: Fire/nsubj->causes, causes/ROOT (lemma=cause), heat/dobj->causes
    result = extract_dependencies("Fire causes heat.")
    assert ("fire", "heat") in result


def test_forward_connective_leads_to():
    # "Heat leads to energy" -> heat is the cause, energy is the effect
    # Parse: Heat/nsubj->leads, leads/ROOT (lemma=lead), to/prep->leads,
    # energy/pobj->to
    result = extract_dependencies("Heat leads to energy.")
    assert ("heat", "energy") in result


def test_backward_connective_requires():
    # "The engine requires fuel" -> fuel is the cause (prerequisite), engine
    # is the effect (dependent)
    # Parse: engine/nsubj->requires, requires/ROOT (lemma=require),
    # fuel/dobj->requires
    result = extract_dependencies("The engine requires fuel.")
    assert ("fuel", "engine") in result


def test_backward_connective_depends_on():
    # "Rust depends on moisture" -> moisture is the cause, rust is the effect
    # Parse: Rust/nsubj->depends (lemma_="Rust", lowercased to "rust"),
    # depends/ROOT (lemma=depend), on/prep->depends, moisture/pobj->on
    result = extract_dependencies("Rust depends on moisture.")
    assert ("moisture", "rust") in result


def test_no_connective_returns_empty():
    # Parse: sky/nsubj->is, is/ROOT (lemma=be), blue/acomp->is
    # No token lemma is in FORWARD_CONNECTIVES or BACKWARD_CONNECTIVES.
    result = extract_dependencies("The sky is blue.")
    assert result == []


def test_pronoun_object_is_filtered_out():
    # "The licence requires you" — "you" is a pronoun (PRON, stop word), not a
    # content-word concept, so no pair should be emitted even though the
    # dependency structure (requires/BACKWARD, nsubj=licence, dobj=you) matches.
    # This is the association-quality filter: function words never become concepts.
    result = extract_dependencies("The licence requires you.")
    assert result == []


def test_pronoun_subject_is_filtered_out():
    # "It causes damage" — "It" is a pronoun subject; with the subject filtered
    # to None, no (cause, effect) pair is emitted.
    result = extract_dependencies("It causes damage.")
    assert result == []


def test_content_words_still_extracted_after_filter():
    # Sanity: the filter must not reject legitimate noun concepts.
    result = extract_dependencies("Deforestation causes erosion.")
    assert ("deforestation", "erosion") in result


def test_multiword_concept_kept_as_one_phrase():
    # "machine learning" must be a single concept, not "machine" + "learning".
    result = extract_dependencies("Machine learning enables automation.")
    causes = [c for c, _ in result]
    assert "machine learning" in causes
    # And it should NOT have fragmented into the bare head noun.
    assert "learning" not in causes


def test_multiword_security_term_captured():
    # A real security term stays intact as the cause concept.
    result = extract_dependencies("SQL injection causes data breaches.")
    assert any(c == "sql injection" for c, _ in result)


def test_single_word_concepts_unchanged_by_phrase_logic():
    # Existing single-token behaviour must be preserved.
    assert ("fire", "heat") in extract_dependencies("Fire causes heat.")
    assert ("fuel", "engine") in extract_dependencies("The engine requires fuel.")
