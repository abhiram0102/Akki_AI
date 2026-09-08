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
