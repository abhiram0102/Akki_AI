"""Tests for the brain reasoning step — deriving 2-hop links that the graph
never stored directly. Mocks the two Cypher helpers (_top_associations,
_reachable_with_depth); no live Neo4j required."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.services import brain_service


@pytest.mark.asyncio
async def test_infer_links_excludes_direct_neighbours():
    with patch.object(brain_service, "_top_associations", AsyncMock(return_value=[{"word": "b", "g2": 9, "count": 3}])), \
         patch.object(brain_service, "_reachable_with_depth", AsyncMock(return_value={"b": 1, "c": 2})):
        out = await brain_service.infer_links("a")
    words = [d["concept"] for d in out]
    assert "c" in words and "b" not in words
    assert all(d["derived"] for d in out)


@pytest.mark.asyncio
async def test_infer_links_excludes_the_concept_itself():
    with patch.object(brain_service, "_top_associations", AsyncMock(return_value=[])), \
         patch.object(brain_service, "_reachable_with_depth", AsyncMock(return_value={"a": 0, "c": 2})):
        out = await brain_service.infer_links("a")
    words = [d["concept"] for d in out]
    assert "a" not in words
    assert words == ["c"]


@pytest.mark.asyncio
async def test_infer_links_respects_limit_and_alphabetical_tiebreak():
    with patch.object(brain_service, "_top_associations", AsyncMock(return_value=[])), \
         patch.object(brain_service, "_reachable_with_depth",
                       AsyncMock(return_value={"z": 2, "y": 2, "x": 2, "w": 2})):
        out = await brain_service.infer_links("a", limit=2)
    words = [d["concept"] for d in out]
    assert words == ["w", "x"]


@pytest.mark.asyncio
async def test_infer_links_returns_empty_when_no_derived_candidates():
    with patch.object(brain_service, "_top_associations", AsyncMock(return_value=[{"word": "b", "g2": 9, "count": 3}])), \
         patch.object(brain_service, "_reachable_with_depth", AsyncMock(return_value={"b": 1})):
        out = await brain_service.infer_links("a")
    assert out == []


@pytest.mark.asyncio
async def test_infer_links_forwards_min_count_to_both_helpers():
    """/ask needs to relax the edge-count floor to 1 for freshly-learned
    concepts; infer_links must thread a passed min_count through to both
    of its internal Cypher helpers (default behaviour for discover/converge
    callers, who never pass min_count, must stay unchanged)."""
    mock_top = AsyncMock(return_value=[])
    mock_reach = AsyncMock(return_value={})
    with patch.object(brain_service, "_top_associations", mock_top), \
         patch.object(brain_service, "_reachable_with_depth", mock_reach):
        await brain_service.infer_links("a", min_count=1)
    mock_top.assert_awaited_once_with("a", min_count=1)
    mock_reach.assert_awaited_once_with("a", max_depth=2, min_count=1)


@pytest.mark.asyncio
async def test_infer_links_default_min_count_matches_module_floor():
    mock_top = AsyncMock(return_value=[])
    mock_reach = AsyncMock(return_value={})
    with patch.object(brain_service, "_top_associations", mock_top), \
         patch.object(brain_service, "_reachable_with_depth", mock_reach):
        await brain_service.infer_links("a")
    mock_top.assert_awaited_once_with("a", min_count=brain_service.MIN_EDGE_COUNT)
    mock_reach.assert_awaited_once_with("a", max_depth=2, min_count=brain_service.MIN_EDGE_COUNT)


@pytest.mark.asyncio
async def test_infer_links_result_shape():
    with patch.object(brain_service, "_top_associations", AsyncMock(return_value=[])), \
         patch.object(brain_service, "_reachable_with_depth", AsyncMock(return_value={"c": 2})):
        out = await brain_service.infer_links("a")
    assert out == [{"concept": "c", "via": None, "strength": out[0]["strength"], "derived": True}]
    assert set(out[0].keys()) == {"concept", "via", "strength", "derived"}
