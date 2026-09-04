"""Tests for the Neo4j connection service. Uses a fake driver/session so no
live Neo4j instance is required for this test — connectivity itself is
verified manually in Task 8's Docker smoke test."""
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services import neo4j_service


class _FakeRecord(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    def __init__(self, result):
        self._result = result

    async def run(self, *args, **kwargs):
        return self._result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _fake_driver(result):
    driver = MagicMock()
    driver.session.return_value = _FakeSession(result)
    return driver


async def test_health_check_true_when_driver_returns_ok():
    neo4j_service._driver = _fake_driver(_FakeResult(_FakeRecord(ok=1)))
    assert await neo4j_service.health_check() is True
    neo4j_service._driver = None


async def test_health_check_false_on_exception():
    driver = MagicMock()
    driver.session.side_effect = Exception("connection refused")
    neo4j_service._driver = driver
    assert await neo4j_service.health_check() is False
    neo4j_service._driver = None


async def test_get_driver_reuses_existing_instance():
    with patch.object(neo4j_service, "AsyncGraphDatabase") as mock_gdb:
        mock_gdb.driver.return_value = "driver-instance"
        neo4j_service._driver = None
        d1 = neo4j_service.get_driver()
        d2 = neo4j_service.get_driver()
        assert d1 == d2 == "driver-instance"
        mock_gdb.driver.assert_called_once()
    neo4j_service._driver = None
