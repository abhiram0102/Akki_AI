"""Tests for the meaning layer (backend/services/brain_meaning.py).

These run against a real ChromaDB store with real embeddings, in a temporary
directory. That is deliberate: the thing being tested is whether senses emerge
from what the contexts actually mean, and a mocked embedding would test only
the clustering arithmetic while assuming away the part that matters.

The decisive test feeds one word used two genuinely different ways and asks
whether the split is found. Nothing in the module names any word, any sense, or
how many senses to expect.
"""
import pytest

from backend.services import brain_meaning


# Two unmistakably different uses of one word. Nothing labels them; if the
# senses come back separated, the separation came from the sentences.
_PHYSICAL = [
    "Fire consumes oxygen and releases heat into the surrounding air.",
    "The fire burned through dry timber and spread across the forest floor.",
    "Firefighters contained the fire before it reached the fuel storage tanks.",
    "A fire requires fuel, oxygen and a source of ignition to start burning.",
    "The heat of the fire melted the metal frame of the building.",
    "Smoke from the fire rose above the burning woodland.",
]
_EMOTIONAL = [
    "She spoke with fire about the injustice her community had suffered.",
    "His fire and passion inspired the whole team to keep going.",
    "There was a fire in her ambition that no setback could put out.",
    "The poet wrote of the fire of longing that consumed his heart.",
    "He argued with such fire that the audience rose to applaud him.",
    "Her fire of conviction never dimmed throughout the long campaign.",
]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A real, empty meaning store per test."""
    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path / "meaning"))
    collection = client.get_or_create_collection(
        name="test_contexts", metadata={"hnsw:space": "cosine"}
    )
    brain_meaning.reset_for_tests(collection)
    yield collection
    brain_meaning.reset_for_tests(None)


def test_records_contexts_and_counts_them(store):
    assert brain_meaning.record_contexts("fire", _PHYSICAL) == len(_PHYSICAL)


def test_rereading_the_same_sentence_does_not_invent_a_second_use(store):
    """A page crawled twice must not make one mention look like two independent
    uses, or repetition alone would manufacture a sense."""
    brain_meaning.record_contexts("fire", _PHYSICAL)
    brain_meaning.record_contexts("fire", _PHYSICAL)
    found = brain_meaning.senses("fire")
    assert sum(s["contextCount"] for s in found) == len(_PHYSICAL)


def test_fragments_are_not_recorded_as_contexts(store):
    assert brain_meaning.record_contexts("fire", ["ok", "a b"]) == 0


def test_one_way_of_using_a_word_yields_one_sense(store):
    """The answer that matters most. Inventing senses for an unambiguous word
    would fragment the graph for nothing, so a single use must stay single."""
    brain_meaning.record_contexts("fire", _PHYSICAL)
    assert len(brain_meaning.senses("fire")) == 1


def test_two_unrelated_uses_are_discovered_as_separate_senses(store):
    """The decisive test. One word, two genuinely different uses, no labels
    anywhere. If the senses separate, the separation came from meaning."""
    brain_meaning.record_contexts("fire", _PHYSICAL + _EMOTIONAL)
    found = brain_meaning.senses("fire")
    assert len(found) >= 2
    # Neither sense may be a stray outlier; both must rest on real support.
    assert all(s["contextCount"] >= 2 for s in found)


def test_senses_are_labelled_by_what_distinguishes_them(store):
    """A sense is named by what its contexts say that the others do not, so the
    labels must actually differ."""
    brain_meaning.record_contexts("fire", _PHYSICAL + _EMOTIONAL)
    found = brain_meaning.senses("fire")
    labels = [set(s["label"]) for s in found]
    assert len(labels) >= 2
    assert labels[0] != labels[1]


def test_each_sense_carries_a_real_example_not_a_summary(store):
    brain_meaning.record_contexts("fire", _PHYSICAL + _EMOTIONAL)
    everything = _PHYSICAL + _EMOTIONAL
    for sense in brain_meaning.senses("fire"):
        assert sense["example"] in everything


def test_a_question_reaches_the_sense_it_is_asking_about(store):
    """Function 7 step 3. Asking about fire alongside fuel and heat must reach
    a different sense than asking about it alongside passion, with neither
    sense defined anywhere."""
    brain_meaning.record_contexts("fire", _PHYSICAL + _EMOTIONAL)
    physical = brain_meaning.disambiguate("fire", "what fuel and oxygen does burning need")
    emotional = brain_meaning.disambiguate("fire", "her passion and conviction when speaking")
    assert physical is not None and emotional is not None
    assert physical["sense"] != emotional["sense"]


def test_an_unambiguous_concept_reports_no_sense_to_choose(store):
    """With one sense there is nothing to disambiguate, and saying so lets a
    caller skip the distinction rather than handle a meaningless answer."""
    brain_meaning.record_contexts("fire", _PHYSICAL)
    assert brain_meaning.disambiguate("fire", "what does burning need") is None


def test_unknown_concept_has_no_senses_rather_than_an_error(store):
    assert brain_meaning.senses("neverseen") == []
    assert brain_meaning.disambiguate("neverseen", "anything") is None


def test_empty_input_is_handled(store):
    assert brain_meaning.record_contexts("", ["some sentence here"]) == 0
    assert brain_meaning.senses("") == []
    assert brain_meaning.disambiguate("fire", "") is None
