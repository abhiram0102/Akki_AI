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
