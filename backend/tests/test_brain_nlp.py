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


def test_general_verb_relations_are_extracted():
    # Density: an ordinary transitive verb (not in the causal connective sets)
    # still yields a subject→object edge, so normal prose feeds the graph.
    assert ("encryption", "data") in extract_dependencies("Encryption protects data.")
    assert ("firewall", "malicious traffic") in extract_dependencies("Firewalls block malicious traffic.")


def test_copula_and_light_verbs_produce_no_edge():
    # "is"/"has"/"uses" carry no real relationship — must stay out of the graph.
    assert extract_dependencies("The sky is blue.") == []
    assert extract_dependencies("The system has a database.") == []
    assert extract_dependencies("The app uses a library.") == []


# ── Irregular morphology: plurals and verbs (Task B regression) ────────────
#
# spaCy's lemmatiser is a real morphological analyzer, not naive
# suffix-stripping, and it gets the vast majority of irregular forms right
# (children -> child, mice -> mouse, went -> go, ran -> run). The defect this
# guards is narrower: a handful of Latin/Greek loanword plurals whose
# etymologically "correct" singular is rare/archaic or names a different
# sense in ordinary technical prose ("data" -> "datum", "media" -> "medium").
# `_IRREGULAR_PLURAL_SURFACE` in brain_nlp overrides exactly those, keyed on
# the surface word so a genuine singular use is untouched.

def test_irregular_plural_data_stays_data_not_datum():
    result = extract_dependencies("Encryption protects data.")
    assert ("encryption", "data") in result
    assert not any("datum" in pair for pair in result)


def test_irregular_plural_media_stays_media_not_medium():
    result = extract_dependencies("Advertisers target media.")
    assert ("advertiser", "media") in result
    assert not any("medium" in pair for pair in result)


def test_genuine_singular_medium_is_not_rewritten_to_media():
    # The override is keyed on the surface word the writer used, not on the
    # lemma, so an actual singular use of "medium" must be left alone.
    result = extract_dependencies("The lab prepares a growth medium.")
    assert ("lab", "growth medium") in result or ("lab", "medium") in result
    assert not any("media" in pair for pair in result)


def test_ordinary_loanword_plurals_still_consolidate_to_singular():
    # Contrast case: matrix/matrices, thesis/theses etc. are NOT false
    # friends — spaCy already lemmatises them correctly, and collapsing a
    # plural mention onto the singular node is the desired behaviour, not a
    # bug. The exception list must stay narrow rather than blanket "keep
    # every plural as-is".
    result = extract_dependencies("Engineers multiply matrices.")
    assert ("engineer", "matrix") in result


def test_irregular_english_plural_nouns_lemmatise_correctly():
    # Native irregular plurals (not loanwords) are already handled correctly
    # by spaCy's lemmatiser in real sentence context — no override needed.
    assert ("antibiotic", "bacteria") in extract_dependencies("Antibiotics kill bacteria.")
    assert ("school", "child") in extract_dependencies("Schools educate children.")
    # "field mice" is kept as one multi-word concept ("field mouse"), same as
    # "machine learning" — the irregular plural inside it still lemmatises
    # correctly (mice -> mouse, not left as "mice").
    assert ("cat", "field mouse") in extract_dependencies("Cats hunt field mice.")


def test_irregular_past_tense_verbs_still_match_connectives():
    # Irregular verb morphology (unlike loanword noun plurals) is not broken:
    # "led" must still lemmatise to "lead" to match FORWARD_CONNECTIVES.
    assert ("deforestation", "soil erosion") in extract_dependencies(
        "Deforestation led to soil erosion."
    )
    # "arose" -> "arise" is a general (non-connective) verb; still yields a
    # subject/object edge like any other transitive verb.
    result = extract_dependencies("The crisis arose from mismanagement.")
    assert result  # some edge is produced; the point is the verb is not skipped


# ── Negation (found via Task C real-text sampling) ──────────────────────────
#
# A negated verb was being extracted as if the sentence asserted the
# opposite: "the cyanobacteria did not generate oxygen" produced
# (cyanobacteria, oxygen). spaCy already labels this `neg` on the verb, so
# the fix reads an existing parser output rather than adding a lexicon.

def test_negated_verb_produces_no_edge():
    assert extract_dependencies("The firewall does not block traffic.") == []
    assert extract_dependencies("Vaccines never cause autism.") == []
    assert extract_dependencies("The cyanobacteria did not generate oxygen.") == []


def test_unnegated_verb_is_unaffected_by_the_negation_check():
    assert ("encryption", "data") in extract_dependencies("Encryption protects data.")
    assert ("friction", "heat") in extract_dependencies("Friction causes heat.")


# ── Passive voice with an expressed agent (found via Task C real-text
# sampling) ──────────────────────────────────────────────────────────────────
#
# "Y is caused by X" has Y as spaCy's `nsubjpass` and X as the object of an
# `agent`-labelled by-phrase (not a plain `prep`, which is why it was
# previously invisible to extraction). X is still the cause regardless of
# which voice the sentence is in, so the pair must come out the same as the
# active-voice phrasing -- treating `nsubjpass` as an ordinary subject would
# silently invert it.

def test_passive_forward_connective_matches_active_direction():
    active = extract_dependencies("Friction causes heat.")
    passive = extract_dependencies("Heat is caused by friction.")
    assert active == passive == [("friction", "heat")]


def test_passive_backward_connective_matches_active_direction():
    active = extract_dependencies("Photosynthesis requires sunlight.")
    passive = extract_dependencies("Sunlight is required by photosynthesis.")
    assert active == passive == [("sunlight", "photosynthesis")]


def test_passive_general_verb_with_agent_is_reversed_from_nsubjpass():
    # "protects" is a general (non-connective) verb; the same inversion
    # still applies to it, not just the two typed connective sets.
    result = extract_dependencies("Data is protected by encryption.")
    assert ("encryption", "data") in result


def test_passive_without_an_expressed_agent_is_unaffected():
    # No by-phrase to invert against, so the existing nsubjpass-as-subject
    # reading (unchanged since before this session) still applies.
    result = extract_dependencies("The membrane may be tightly folded into cylindrical sheets.")
    assert ("membrane", "cylindrical sheet") in result
