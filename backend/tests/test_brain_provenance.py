"""Tests for the provenance layer (backend/services/brain_provenance.py).

The roadmap's fifth pillar asks that AKKI answer "why do you believe this?"
with an evidence chain, never "because the model gave it a high probability".

Nothing did that yet. The graph stored an edge's strength; brain_relations
stored the verbs actually observed; brain_hypothesis stored whether a link was
the brain's own inference and how it fared. Three separate stores, no single
place that assembles them into "here is why AKKI holds this belief".

This module reads those three -- it writes nothing and invents nothing. Every
line of an explanation traces to a row that already exists, which is the whole
point: a belief you cannot trace is a belief you cannot revise (pillar 5) or
trust in a reasoning step (pillar 2).
"""
from unittest.mock import MagicMock

import pytest

from backend.services import brain_provenance


class _PG:
    """A Postgres session that returns queued result-sets in order."""

    def __init__(self, *result_sets):
        self._results = list(result_sets)
        self.queries = []

    async def execute(self, statement, params=None):
        self.queries.append((str(statement), params))
        result = MagicMock()
        rows = self._results.pop(0) if self._results else []
        result.fetchall.return_value = rows
        return result

    async def commit(self):
        return None


def _graph(strength=None, g2=None):
    """A Neo4j session reporting one edge, or none when strength is None."""
    session = MagicMock()

    async def run(query, **params):
        result = MagicMock()

        async def single():
            if strength is None:
                return None
            return {"strength": strength, "g2": g2}

        result.single = single
        return result

    session.run = run
    return session


class TestABeliefBackedByObservation:
    async def test_it_reports_the_verbs_actually_seen(self):
        pg = _PG([("fire", "produce", "heat", 4)])  # brain_relations rows

        exp = await brain_provenance.explain(
            pg, _graph(strength=4, g2=12.3), "fire", "heat")

        assert exp["basis"] == brain_provenance.OBSERVED
        assert {"relation": "produce", "count": 4} in exp["observations"]

    async def test_a_direct_edge_carries_its_strength_and_surprise(self):
        pg = _PG([("fire", "produce", "heat", 4)])

        exp = await brain_provenance.explain(
            pg, _graph(strength=4, g2=12.3), "fire", "heat")

        assert exp["edge"]["strength"] == 4
        assert exp["edge"]["g2"] == 12.3


class TestABeliefThatIsOnlyAnInference:
    async def test_an_unsupported_inference_says_so_plainly(self):
        # no relations rows, no direct edge, but a hypothesis row
        pg = _PG([], [("electron", "unsupported")])

        exp = await brain_provenance.explain(
            pg, _graph(strength=None), "photosynthesis", "nucleus")

        assert exp["basis"] == brain_provenance.INFERRED
        assert exp["inference"]["via"] == "electron"
        assert exp["inference"]["verdict"] == "unsupported"

    async def test_the_why_sentence_does_not_overclaim_an_unsupported_link(self):
        """A belief the reading never bore out must not be narrated as fact."""
        pg = _PG([], [("electron", "unsupported")])

        exp = await brain_provenance.explain(
            pg, _graph(strength=None), "photosynthesis", "nucleus")

        why = exp["why"].lower()
        assert "inferred" in why or "worked out" in why
        assert "confirmed" not in why  # it was not


class TestABeliefWithNoSupportAtAll:
    async def test_an_unknown_pair_is_honest_about_having_nothing(self):
        pg = _PG([], [])

        exp = await brain_provenance.explain(
            pg, _graph(strength=None), "aardvark", "quasar")

        assert exp["basis"] == brain_provenance.NONE
        assert exp["observations"] == []
        assert exp["inference"] is None


class TestItNeverInvents:
    async def test_provenance_reads_and_does_not_write(self):
        """A trace that mutated state would corrupt the very thing it explains."""
        pg = _PG([("a", "cause", "b", 2)])
        await brain_provenance.explain(pg, _graph(strength=2, g2=1.0), "a", "b")

        for query, _ in pg.queries:
            upper = query.upper()
            assert "INSERT" not in upper
            assert "UPDATE" not in upper
            assert "DELETE" not in upper

    async def test_an_unreadable_store_yields_unknown_not_an_error(self):
        class _Broken:
            async def execute(self, *a, **kw): raise RuntimeError("db down")

        exp = await brain_provenance.explain(
            _Broken(), _graph(strength=None), "a", "b")

        assert exp["basis"] == brain_provenance.NONE


# --- The provenance SUBSTRATE (Sanju's spec) --------------------------------
#
# explain() above reads the three existing stores. The substrate adds the layer
# the pipeline was throwing away: for each observation of a claim, WHERE it came
# from (source), the exact EVIDENCE SPAN, HOW it was extracted (method), and
# WHEN. Predicate-agnostic throughout -- the predicate is whatever verb was
# found, never a CAUSES/IS_A type, because those are what the corpus is meant to
# induce later.

class TestRecordingEvidence:
    async def test_an_observation_is_stored_with_its_source_and_span(self):
        pg = _PG()
        n = await brain_provenance.record_evidence(pg, [{
            "subject": "fire", "predicate": "produce", "object": "heat",
            "source": "https://x/Fire", "span": "Fire produces heat.",
            "method": "dep-parse",
        }])
        assert n == 1
        params = pg.queries[-1][1]
        assert params["source"] == "https://x/Fire"
        assert params["span"] == "Fire produces heat."
        assert params["method"] == "dep-parse"

    async def test_the_predicate_is_stored_verbatim_not_typed(self):
        """No mapping to CAUSES/IS_A/etc -- that ontology is deliberately absent
        until the corpus can induce it."""
        pg = _PG()
        await brain_provenance.record_evidence(pg, [{
            "subject": "a", "predicate": "destroy", "object": "b",
            "source": "s", "span": "a destroys b", "method": "m"}])
        assert pg.queries[-1][1]["predicate"] == "destroy"

    async def test_an_observation_missing_its_source_is_not_stored(self):
        """Evidence with no provenance is not evidence -- storing it would
        defeat the point of the substrate."""
        pg = _PG()
        n = await brain_provenance.record_evidence(pg, [{
            "subject": "a", "predicate": "p", "object": "b",
            "span": "a p b", "method": "m"}])  # no source
        assert n == 0

    async def test_recording_never_breaks_the_crawl(self):
        class _Broken:
            async def execute(self, *a, **kw): raise RuntimeError("db down")
        assert await brain_provenance.record_evidence(_Broken(), [{
            "subject": "a", "predicate": "p", "object": "b",
            "source": "s", "span": "x", "method": "m"}]) == 0


class TestTheFullTraceAnswersTheNineQuestions:
    """WHAT / WHY / WHERE / HOW / WHEN / supports / contradicts / derivation /
    dependents -- never collapsed into one confidence number."""

    async def test_an_observed_belief_traces_to_source_span_and_method(self):
        evidence_rows = [
            ("fire", "produce", "heat", "https://x/Fire",
             "Fire produces heat.", "dep-parse", "2026-09-06T00:00:00Z"),
        ]
        dependents_rows = []
        # _PG serves: evidence, (inference lookup skipped: has evidence), dependents
        pg = _PG(evidence_rows, dependents_rows)

        trace = await brain_provenance.trace(
            pg, _graph(strength=4, g2=9.0), "fire", "heat")

        assert trace["what"]["subject"] == "fire"
        assert trace["why"]["basis"] == brain_provenance.OBSERVED
        assert "https://x/Fire" in trace["where"]
        assert "dep-parse" in trace["how"]
        assert trace["when"]["first"] == "2026-09-06T00:00:00Z"
        assert trace["supporting"]  # the observation is here

    async def test_competing_predicates_are_surfaced_but_not_called_contradictions(self):
        """produce vs require are not opposites; asserting contradiction needs
        predicate polarity the project cannot yet induce. So competing
        predicates are shown as data, and contradiction detection is declared
        deferred rather than faked."""
        evidence_rows = [
            ("fire", "produce", "heat", "s1", "fire produces heat", "m", "t1"),
            ("fire", "require", "heat", "s2", "fire requires heat", "m", "t2"),
        ]
        pg = _PG(evidence_rows, [])

        trace = await brain_provenance.trace(
            pg, _graph(strength=2, g2=1.0), "fire", "heat")

        preds = {o["predicate"] for o in trace["supporting"]}
        assert preds == {"produce", "require"}
        assert trace["contradicting"]["status"] == "deferred"

    async def test_a_derived_belief_shows_its_derivation(self):
        # no evidence rows -> falls back to inference lookup, then dependents
        pg = _PG([], [("electron", "unsupported")], [])

        trace = await brain_provenance.trace(
            pg, _graph(strength=None), "photosynthesis", "nucleus")

        assert trace["why"]["basis"] == brain_provenance.INFERRED
        assert trace["derivation"]["premises"] == ["electron"]
        assert trace["derivation"]["method"]  # some method named
        assert trace["derivation"]["verdict"] == "unsupported"

    async def test_it_reports_what_depends_on_the_belief(self):
        evidence_rows = [("a", "p", "b", "s", "a p b", "m", "t")]
        dependents_rows = [("photosynthesis", "nucleus")]  # inferred THROUGH b
        pg = _PG(evidence_rows, dependents_rows)

        trace = await brain_provenance.trace(
            pg, _graph(strength=1, g2=1.0), "a", "b")

        assert {"subject": "photosynthesis", "object": "nucleus"} in trace["dependents"]

    async def test_provenance_is_not_self_correction(self):
        """The honest boundary Sanju insisted on: the substrate exposes what
        would be needed to revise a belief; it does not itself revise anything."""
        assert not hasattr(brain_provenance, "revise")
        assert not hasattr(brain_provenance, "correct")
