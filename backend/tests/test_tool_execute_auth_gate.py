"""Tests for the authorization gate on active exploit tools in main.py.

Uses FastAPI's TestClient with dependency overrides so no live Postgres
or JWT is needed.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from backend.main import app
from backend.database import get_db
from backend.auth import get_current_user


class _FakeUser:
    id = "11111111-1111-1111-1111-111111111111"


class _FakeDB:
    def add(self, obj):
        self.added = obj

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


@pytest.fixture(autouse=True)
def _override_deps():
    fake_db = _FakeDB()

    async def _get_db_override():
        yield fake_db

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    yield fake_db
    app.dependency_overrides.clear()


async def _client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestActiveToolRequiresAuthorization:
    async def test_active_tool_without_authorization_is_rejected(self):
        async with await _client() as client:
            resp = await client.post(
                "/api/tools/execute",
                json={"toolName": "vuln_scan", "params": {"host": "example.com"}},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["requiresAuthorization"] is True

    async def test_active_tool_with_authorization_runs_and_logs(self, _override_deps):
        fake_db = _override_deps
        with patch("backend.main.run_tool", AsyncMock(return_value={"success": True, "tool": "vuln_scan", "result": {}})):
            async with await _client() as client:
                resp = await client.post(
                    "/api/tools/execute",
                    json={"toolName": "vuln_scan", "params": {"host": "example.com"}, "authorized": True},
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert getattr(fake_db, "added", None) is not None
        assert fake_db.added.tool_name == "vuln_scan"
        assert fake_db.added.user_id == _FakeUser.id

    async def test_passive_tool_does_not_require_authorization(self):
        with patch("backend.main.run_tool", AsyncMock(return_value={"success": True, "tool": "dns_lookup", "result": {}})):
            async with await _client() as client:
                resp = await client.post(
                    "/api/tools/execute",
                    json={"toolName": "dns_lookup", "params": {"domain": "example.com"}},
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_stream_endpoint_rejects_unauthorized_active_tool(self):
        async with await _client() as client:
            async with client.stream(
                "POST", "/api/tools/execute/stream",
                json={"toolName": "sqli_test", "params": {"url": "example.com"}},
            ) as resp:
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
        text = body.decode()
        assert "requiresAuthorization" in text
        assert '"type": "done"' not in text and "'type': 'done'" not in text
