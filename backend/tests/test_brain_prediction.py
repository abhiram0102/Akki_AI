"""The brain's first falsifiable test, tested itself.

These use a fake driver, so they check the measurement is honest rather than
that the live graph scores well. A metric that cannot report failure is worse
than no metric, because it looks like evidence.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.services import brain_prediction


def _result(records):
    class R:
        def __aiter__(self):
            async def gen():
                for rec in records:
                    yield rec
            return gen()
    return R()


def _driver(ranked_by_concept, relations, space):
    driver = MagicMock()

    async def run(query, **params):
        if "count(c) AS size" in query:
            return _result([{"size": space}])
        if "ORDER BY rand()" in query:
            return _result([{"source": s, "target": t} for s, t in relations])
        words = ranked_by_concept.get(params.get("concept"), [])
        return _result([{"word": w, "score": 1.0} for w in words])

    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    session.run = run
    driver.session.return_value = session
    return driver


class TestKnowledgeMeasurement:
    async def test_a_graph_that_rebuilds_hidden_relations_scores_high(self, monkeypatch):
        """The point of the measure: a relation the rest of the graph implies
        is one the brain understood, not merely stored."""
        monkeypatch.setattr(brain_prediction, "get_driver", lambda: _driver(
            {"fire": ["heat", "smoke"], "rain": ["flood", "cloud"]},
            [("fire", "heat"), ("rain", "flood")], space=1000))
        result = await brain_prediction.measure_knowledge(sample=2, limit=10)
        assert result["recovered"] == 2
        assert result["recoveryRate"] == 1.0
        assert result["meanReciprocalRank"] == 1.0

    async def test_a_graph_that_memorised_without_understanding_scores_zero(self, monkeypatch):
        """The failure this exists to catch. Every volume metric -- pages,
        concepts, relations -- looks identical here to the passing case above.
        This one does not, which is the entire reason it was built."""
        monkeypatch.setattr(brain_prediction, "get_driver", lambda: _driver(
            {"fire": ["unrelated", "noise"], "rain": ["nothing", "random"]},
            [("fire", "heat"), ("rain", "flood")], space=1000))
        result = await brain_prediction.measure_knowledge(sample=2, limit=10)
        assert result["recovered"] == 0
        assert result["recoveryRate"] == 0.0
        assert result["lift"] == 0.0

    async def test_rank_position_is_not_thrown_away(self, monkeypatch):
        """Finding the answer tenth is not the same as finding it first, and a
        hit rate alone cannot tell the two apart."""
        monkeypatch.setattr(brain_prediction, "get_driver", lambda: _driver(
            {"fire": ["a", "b", "c", "heat"]}, [("fire", "heat")], space=1000))
        result = await brain_prediction.measure_knowledge(sample=1, limit=10)
        assert result["recovered"] == 1
        assert result["meanReciprocalRank"] == 0.25  # found fourth

    async def test_lift_is_measured_against_the_real_candidate_space(self, monkeypatch):
        """A hit rate means nothing without knowing how many wrong answers were
        available. Ten of ten in a field of ten is not knowledge."""
        monkeypatch.setattr(brain_prediction, "get_driver", lambda: _driver(
            {"fire": ["heat"]}, [("fire", "heat")], space=10))
        result = await brain_prediction.measure_knowledge(sample=1, limit=10)
        assert result["recoveryRate"] == 1.0
        assert result["lift"] == 1.0, "scoring at chance was reported as knowledge"

    async def test_an_empty_graph_reports_nothing_rather_than_failing(self, monkeypatch):
        monkeypatch.setattr(brain_prediction, "get_driver",
                            lambda: _driver({}, [], space=0))
        result = await brain_prediction.measure_knowledge()
        assert result["tested"] == 0
