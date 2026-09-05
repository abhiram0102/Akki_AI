"""Tests for the streaming POST /api/brain/ask endpoint.

Uses FastAPI's TestClient with a dependency override for auth so no live
Postgres/JWT is needed, and patches the brain_service/brain_learn calls so
no live Neo4j or network access happens.
"""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.auth import get_current_user


class _FakeUser:
    id = "11111111-1111-1111-1111-111111111111"


def _override_auth():
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()


def _clear_auth():
    app.dependency_overrides.pop(get_current_user, None)


class TestBrainAskAuth:
    def test_unauthenticated_returns_401(self):
        _clear_auth()
        client = TestClient(app)
        resp = client.post("/api/brain/ask", json={"concept": "fire"})
        assert resp.status_code == 401


class TestBrainAskKnownConcept:
    def test_known_concept_skips_learning(self):
        """_top_associations already returns enough associations -> no
        learning stage should be emitted, only thinking + answer + done."""
        _override_auth()
        try:
            assoc = [
                {"word": "heat", "g2": 42.5, "count": 10},
                {"word": "smoke", "g2": 30.1, "count": 8},
                {"word": "ash", "g2": 20.0, "count": 5},
            ]
            with patch(
                "backend.services.brain_service._top_associations",
                AsyncMock(return_value=assoc),
            ), patch(
                "backend.services.brain_service.infer_links",
                AsyncMock(return_value=[{"concept": "smoke", "via": "heat", "strength": 1.0, "derived": True}]),
            ), patch(
                "backend.services.brain_learn.learn_concept",
                AsyncMock(),
            ) as mock_learn:
                client = TestClient(app)
                with client.stream("POST", "/api/brain/ask", json={"concept": "fire"}) as resp:
                    body = "".join(resp.iter_text())
                assert resp.status_code == 200

            mock_learn.assert_not_called()
            assert '"stage": "thinking"' in body
            assert '"stage": "answer"' in body
            assert '"stage": "done"' in body
            assert '"stage": "gap"' not in body
            assert '"stage": "learning"' not in body
            assert '"stage": "grew"' not in body
        finally:
            _clear_auth()


class TestBrainAskUnknownConcept:
    def test_unknown_concept_learns_then_answers(self):
        """_top_associations returns [] first (not enough known), so the
        endpoint must learn the concept live, then re-query associations."""
        _override_auth()
        try:
            with patch(
                "backend.services.brain_service._top_associations",
                AsyncMock(side_effect=[[], [{"word": "gravity", "g2": 12.0, "count": 4}]]),
            ), patch(
                "backend.services.brain_service.infer_links",
                AsyncMock(return_value=[]),
            ), patch(
                "backend.services.brain_learn.learn_concept",
                AsyncMock(return_value={
                    "term": "quantum entanglement",
                    "resolved_title": "Quantum_entanglement",
                    "new_concepts": 12,
                    "new_edges": 20,
                    "sources": ["https://en.wikipedia.org/wiki/Quantum_entanglement"],
                }),
            ):
                client = TestClient(app)
                with client.stream(
                    "POST", "/api/brain/ask", json={"concept": "quantum entanglement"}
                ) as resp:
                    body = "".join(resp.iter_text())
                assert resp.status_code == 200

            assert '"stage": "thinking"' in body
            assert '"stage": "gap"' in body
            assert '"stage": "learning"' in body
            assert '"stage": "grew"' in body
            assert '"stage": "answer"' in body
            assert '"stage": "done"' in body
            assert '"new_concepts": 12' in body
            assert '"new_edges": 20' in body
        finally:
            _clear_auth()


class TestBrainAskLearnFailure:
    def test_learn_concept_failure_is_caught_and_streams_note(self):
        """learn_concept can raise (e.g. bad/nonexistent Wikipedia title via
        fetch_wikipedia) — the endpoint must catch this and still complete
        the stream with a fallback answer instead of breaking."""
        _override_auth()
        try:
            with patch(
                "backend.services.brain_service._top_associations",
                AsyncMock(return_value=[]),
            ), patch(
                "backend.services.brain_service.infer_links",
                AsyncMock(return_value=[]),
            ), patch(
                "backend.services.brain_learn.learn_concept",
                AsyncMock(side_effect=Exception("boom")),
            ):
                client = TestClient(app)
                with client.stream(
                    "POST", "/api/brain/ask", json={"concept": "asdkjhasdkjh"}
                ) as resp:
                    body = "".join(resp.iter_text())
                assert resp.status_code == 200

            assert '"stage": "gap"' in body
            assert '"stage": "learning"' in body
            assert '"stage": "answer"' in body
            assert '"stage": "done"' in body
            assert "couldn't learn that one" in body
        finally:
            _clear_auth()
