"""Tests for the falsification loop (backend/services/brain_hypothesis.py).

The brain derives links no source stated -- "photosynthesis leads to nucleus,
reached through electron" -- and already queues them for reading, which session
3 called making the loop "self-correcting rather than self-confirming".

It never found out whether it was right. `measure_effectiveness` scored a read
by how many SENTENCES came back, so a page returning 300 sentences about
something irrelevant counted as a success. The brain could go on making the
same wrong inference forever and its own scoreboard would applaud.

This module records each derived link as a claim, then checks after the reading
whether the graph gained direct support for it.

Most of these tests are about the VERDICT VOCABULARY, because that is where
this design can most easily lie.
"""
from unittest.mock import MagicMock, patch

import pytest

from backend.services import brain_hypothesis


class _Session:
    """A database that answers what it was handed, and records what it was asked."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self.statements = []
        self.params = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        self.params.append(params)
        result = MagicMock()
        result.fetchall.return_value = self.rows
        result.rowcount = len(self.rows)
        return result

    async def commit(self):
        return None


class TestTheVerdictVocabularyDoesNotOverclaim:
    """Reading a page and not finding a link does NOT make the link false.

    This is the failure mode the whole idea is most likely to die of. The
    tempting design has two outcomes, confirmed and refuted, and it is wrong:
    a source can be silent about a true thing for a hundred reasons -- the
    extractor missed it, the page covered a different aspect, the relation is
    stated somewhere this page links to rather than on the page itself.

    Calling that "refuted" would manufacture negative knowledge out of silence,
    and negative knowledge asserted on no evidence is worse than none, because
    the loop then acts on it.
    """

    def test_there_is_no_refuted_verdict(self):
        assert "refuted" not in brain_hypothesis.VERDICTS
        assert "false" not in brain_hypothesis.VERDICTS

    def test_the_three_verdicts_are_confirmed_unsupported_and_pending(self):
        assert set(brain_hypothesis.VERDICTS) == {
            brain_hypothesis.CONFIRMED,
            brain_hypothesis.UNSUPPORTED,
            brain_hypothesis.PENDING,
        }

    def test_unsupported_is_documented_as_weaker_than_refutation(self):
        """If someone later reads this field as 'proven false', the loop starts
        asserting things it never established. The docstring is load-bearing."""
        doc = (brain_hypothesis.__doc__ or "") + (brain_hypothesis.adjudicate.__doc__ or "")
        assert "absence of evidence" in doc.lower()


class TestRecordingAClaim:
    async def test_a_derived_link_is_recorded_as_a_pending_claim(self):
        session = _Session()

        n = await brain_hypothesis.record(session, [
            {"subject": "photosynthesis", "object": "nucleus", "via": "electron"},
        ])

        assert n == 1
        assert session.params[-1]["verdict"] == brain_hypothesis.PENDING

    async def test_the_intermediate_concept_is_kept(self):
        """`via` is what makes a confirmation interpretable later: it says which
        2-hop path the brain reasoned along, so a confirmed claim can be traced
        back to the inference that produced it rather than being a bare pair."""
        session = _Session()

        await brain_hypothesis.record(session, [
            {"subject": "photosynthesis", "object": "nucleus", "via": "electron"},
        ])

        assert session.params[-1]["via"] == "electron"

    async def test_a_claim_with_no_object_is_not_recorded(self):
        session = _Session()
        n = await brain_hypothesis.record(session, [{"subject": "x", "object": ""}])
        assert n == 0

    async def test_recording_failure_never_propagates(self):
        """A bookkeeping table must not be able to break a request that has
        already been answered."""
        class _Broken:
            async def execute(self, *a, **kw): raise RuntimeError("db down")
            async def commit(self): pass

        assert await brain_hypothesis.record(_Broken(), [
            {"subject": "a", "object": "b", "via": "c"}]) == 0


class TestAdjudication:
    """The graph itself is the judge: did reading produce a DIRECT edge for
    what was only ever inferred?"""

    @staticmethod
    def _graph(direct_edge_exists: bool):
        """A Neo4j session that reports whether a direct edge was found."""
        session = MagicMock()

        async def run(query, **params):
            result = MagicMock()

            async def single():
                return {"found": 1 if direct_edge_exists else 0}

            result.single = single
            return result

        session.run = run
        return session

    async def test_a_claim_the_reading_bore_out_is_confirmed(self):
        pg = _Session(rows=[("photosynthesis", "nucleus")])

        verdicts = await brain_hypothesis.adjudicate(
            pg, self._graph(True), "nucleus")

        assert verdicts == {brain_hypothesis.CONFIRMED: 1,
                            brain_hypothesis.UNSUPPORTED: 0}

    async def test_a_claim_the_reading_did_not_bear_out_is_unsupported(self):
        pg = _Session(rows=[("photosynthesis", "nucleus")])

        verdicts = await brain_hypothesis.adjudicate(
            pg, self._graph(False), "nucleus")

        assert verdicts == {brain_hypothesis.CONFIRMED: 0,
                            brain_hypothesis.UNSUPPORTED: 1}

    async def test_only_claims_about_what_was_just_read_are_judged(self):
        """A claim is testable only once the brain has actually gone and read
        the thing it was about. Judging the rest would score them on silence
        the reading never addressed."""
        pg = _Session(rows=[])
        await brain_hypothesis.adjudicate(pg, self._graph(True), "nucleus")
        assert any("nucleus" in str(p) for p in pg.params if p)

    async def test_adjudication_failure_never_stops_the_crawl(self):
        class _Broken:
            async def execute(self, *a, **kw): raise RuntimeError("db down")
            async def commit(self): pass

        assert await brain_hypothesis.adjudicate(
            _Broken(), self._graph(True), "nucleus") == {}


class TestTheScoreboard:
    """The number this whole thing exists to produce: how often was the brain
    right about something no source had told it?"""

    async def test_it_reports_how_often_inference_was_borne_out(self):
        session = _Session(rows=[
            (brain_hypothesis.CONFIRMED, 31),
            (brain_hypothesis.UNSUPPORTED, 69),
        ])

        board = await brain_hypothesis.scoreboard(session)

        assert board["confirmed"] == 31
        assert board["unsupported"] == 69
        assert board["confirmationRate"] == pytest.approx(0.31)

    async def test_pending_claims_are_excluded_from_the_rate(self):
        """A claim not yet tested is not a claim that failed. Counting it as
        one would make the rate fall every time curiosity queued anything."""
        session = _Session(rows=[
            (brain_hypothesis.CONFIRMED, 10),
            (brain_hypothesis.UNSUPPORTED, 10),
            (brain_hypothesis.PENDING, 980),
        ])

        board = await brain_hypothesis.scoreboard(session)

        assert board["confirmationRate"] == pytest.approx(0.5)
        assert board["pending"] == 980

    async def test_no_judged_claims_yields_no_rate_rather_than_zero(self):
        """Zero would read as 'the brain is always wrong'. It means 'nothing
        has been tested yet', which is a different statement."""
        board = await brain_hypothesis.scoreboard(_Session(rows=[]))
        assert board["confirmationRate"] is None

    async def test_an_unreadable_scoreboard_is_empty_not_an_error(self):
        class _Broken:
            async def execute(self, *a, **kw): raise RuntimeError("db down")
            async def commit(self): pass

        assert await brain_hypothesis.scoreboard(_Broken()) == {}


class TestClaimsAreTakenFromTheAnswerTheBrainGave:
    """The claim under test must be the one the brain actually made out loud.

    If the recorded claim were reconstructed later from the graph, it could
    drift from what the answer said, and the scoreboard would be grading a
    different statement than the one the user was told.
    """

    @staticmethod
    def _answer(**kw):
        base = {"topics": ["photosynthesis"], "derived": [], "produces": []}
        base.update(kw)
        return base

    def test_a_derived_link_becomes_a_claim_about_the_topic(self):
        claims = brain_hypothesis.claims_from_answer(self._answer(
            derived=[{"concept": "nucleus", "via": "electron"}]))

        assert claims == [{"subject": "photosynthesis",
                           "object": "nucleus", "via": "electron"}]

    def test_direct_associations_are_not_claims(self):
        """Only what NO source stated is a hypothesis. An edge the brain read
        somewhere is already evidence, and grading it would inflate the
        confirmation rate with things that were never in doubt."""
        claims = brain_hypothesis.claims_from_answer(self._answer(
            produces=[{"word": "plant", "count": 10}]))

        assert claims == []

    def test_an_answer_with_no_topic_yields_nothing(self):
        assert brain_hypothesis.claims_from_answer({"derived": [{"concept": "x"}]}) == []

    def test_an_empty_answer_yields_nothing(self):
        assert brain_hypothesis.claims_from_answer({}) == []
