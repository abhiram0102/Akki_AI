"""The observation log: what the brain saw said about what."""
import pytest
from unittest.mock import AsyncMock

from backend.services import brain_relations
from backend.services.brain_nlp import extract_dependencies, extract_relations


class TestTypedExtraction:
    def test_opposite_claims_stop_being_the_same_edge(self):
        """The failure that motivated all of this. Untyped, "produces" and
        "destroys" collapse to one identical pair, so the graph cannot hold
        what a sentence actually said."""
        produces = extract_relations("Photosynthesis produces oxygen.")
        destroys = extract_relations("Photosynthesis destroys oxygen.")
        assert produces != destroys, "opposite claims still record identically"
        assert ("photosynthesis", "produce", "oxygen") in produces
        assert ("photosynthesis", "destroy", "oxygen") in destroys

    def test_existing_callers_are_unaffected(self):
        """`extract_dependencies` still returns pairs. Every caller in the
        graph path depends on that, and this change is meant to add a record,
        not alter what is learned."""
        sentence = "Photosynthesis produces oxygen."
        assert extract_dependencies(sentence) == [("photosynthesis", "oxygen")]

    def test_the_pair_and_the_triple_agree(self):
        """Two implementations of the same parse rules would drift. These share
        one, and this asserts they have not been split apart."""
        sentence = "Chlorophyll absorbs light and the leaf stores energy."
        pairs = extract_dependencies(sentence)
        triples = [(a, b) for a, _, b in extract_relations(sentence)]
        assert pairs == triples

    def test_direction_from_a_backward_connective_is_kept(self):
        """"X requires Y" means Y comes first. The direction flips and the
        relation is still recorded as the verb that decided it."""
        triples = extract_relations("Photosynthesis requires water.")
        assert ("water", "require", "photosynthesis") in triples

    def test_no_verb_is_interpreted_here(self):
        """The lemma is recorded as observed. Nothing in this module decides
        that "produce" means creation -- that is meant to be induced from many
        observations, and writing it down would be the hardcoded knowledge the
        project exists without."""
        import pathlib
        source = pathlib.Path(brain_relations.__file__).read_text(encoding="utf-8")
        body = source.split('"""', 2)[-1]
        for verb in ("produce", "destroy", "cause", "require"):
            assert verb not in body, f"{verb!r} is named in the module body"


class TestRecording:
    async def test_repeats_within_a_page_become_one_observation(self):
        """A term repeated forty times on one page is one thing seen forty
        times, not forty things."""
        session = AsyncMock()
        kept = await brain_relations.record(session, [
            ("a", "produce", "b"), ("a", "produce", "b"), ("a", "destroy", "c"),
        ])
        assert kept == 2
        assert session.execute.await_count == 2

    async def test_incomplete_observations_are_skipped(self):
        session = AsyncMock()
        kept = await brain_relations.record(session, [
            ("a", "", "b"), ("", "produce", "b"), ("a", "produce", ""),
        ])
        assert kept == 0
        session.execute.assert_not_awaited()

    async def test_a_failed_write_cannot_lose_a_page_already_read(self):
        """The page was fetched and the graph was updated. Losing this log is
        not worth losing that."""
        session = AsyncMock()
        session.execute.side_effect = RuntimeError("database gone")
        kept = await brain_relations.record(session, [("a", "produce", "b")])
        assert kept == 0
