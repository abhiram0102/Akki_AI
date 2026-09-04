"""Tests for the brain query service — mocked Neo4j session/driver, no live
graph required."""
from unittest.mock import AsyncMock, MagicMock

from backend.services import brain_service


def _make_result(records: list[dict]):
    """An async-iterable fake Neo4j result yielding the given record dicts,
    each accessed by dict-style key lookup (e.g. record["word"])."""
    async def _iter():
        for r in records:
            yield r
    result = MagicMock()
    result.__aiter__ = lambda self=result: _iter()
    return result


def _fake_driver_with_sequential_results(results_in_call_order: list[list[dict]]):
    """Each successive call to session.run() returns the next list of fake
    records in sequence — used because this service issues multiple
    structurally-identical-looking queries (e.g. the same Cypher shape
    called once per concept in convergence mode) that a query-text-based
    fake couldn't distinguish, but which must return different fake data
    per call."""
    driver = MagicMock()
    call_queue = [_make_result(r) for r in results_in_call_order]

    async def run(query, **params):
        return call_queue.pop(0)

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = run
    driver.session.return_value = session_cm
    return driver


class TestDiscoverSingleConcept:
    async def test_returns_ranked_associations(self, monkeypatch):
        driver = _fake_driver_with_sequential_results([
            [{"word": "heat", "g2": 42.5, "count": 10}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)
        result = await brain_service.discover("fire", None)
        assert result["concept"] == "fire"
        assert result["associations"][0]["word"] == "heat"
        assert result["associations"][0]["g2"] == 42.5


class TestDiscoverConvergence:
    async def test_returns_convergence_points(self, monkeypatch):
        # First call = _reachable_with_depth("fire"), second = _reachable_with_depth("music")
        driver = _fake_driver_with_sequential_results([
            [{"word": "transformation", "depth": 2}],
            [{"word": "transformation", "depth": 3}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)
        result = await brain_service.discover("fire", "music")
        assert any(c["concept"] == "transformation" for c in result["convergencePoints"])


class TestGetStatus:
    async def test_reads_pg_stats_and_neo4j_counts(self, monkeypatch):
        # First call = concept count query, second call = edge count query
        driver = _fake_driver_with_sequential_results([
            [{"count": 500}],
            [{"count": 1200}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)

        pg_session = AsyncMock()
        stats_row = MagicMock(total_pages=42, total_sentences=1000, updated_at=None)
        frontier_count = MagicMock(scalar=MagicMock(return_value=17))
        pg_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=stats_row)),
            frontier_count,
        ])

        result = await brain_service.get_status(pg_session)
        assert result["totalPages"] == 42
        assert result["frontierSize"] == 17
