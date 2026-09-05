"""Tests for the brain reasoning step — deriving 2-hop links that the graph
never stored directly. Mocks the Cypher helper (_top_associations); no live
Neo4j required."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.services import brain_service


def _neighbours_side_effect(graph):
    """Build a side_effect for _top_associations keyed by concept word, so
    the mock returns the concept's direct neighbours on the first call and
    each visited neighbour's neighbours on subsequent calls."""
    async def _side_effect(word, *args, **kwargs):
        return graph.get(word, [])
    return _side_effect


@pytest.mark.asyncio
async def test_infer_links_surfaces_genuine_two_hop_concept():
    # a -> b (direct), b -> c (2-hop derived, c is not a direct neighbour of a)
    graph = {
        "a": [{"word": "b", "g2": 9.0, "count": 3}],
        "b": [{"word": "c", "g2": 5.0, "count": 3}],
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a")
    words = [d["concept"] for d in out]
    assert "c" in words
    assert "b" not in words  # direct neighbour must not appear as derived


@pytest.mark.asyncio
async def test_infer_links_orders_by_descending_strength():
    # a -> b (g2=10), a -> d (g2=2)
    # b -> c (g2=4) => strength(c via b) = 10*4 = 40
    # d -> e (g2=9) => strength(e via d) = 2*9 = 18
    graph = {
        "a": [{"word": "b", "g2": 10.0, "count": 3}, {"word": "d", "g2": 2.0, "count": 3}],
        "b": [{"word": "c", "g2": 4.0, "count": 3}],
        "d": [{"word": "e", "g2": 9.0, "count": 3}],
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a")
    words = [d["concept"] for d in out]
    assert words == ["c", "e"]
    assert out[0]["strength"] > out[1]["strength"]


@pytest.mark.asyncio
async def test_infer_links_sets_via_and_derived():
    graph = {
        "a": [{"word": "b", "g2": 9.0, "count": 3}],
        "b": [{"word": "c", "g2": 5.0, "count": 3}],
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a")
    assert out == [{"concept": "c", "via": "b", "strength": 45.0, "derived": True}]


@pytest.mark.asyncio
async def test_infer_links_excludes_the_concept_itself():
    graph = {
        "a": [{"word": "b", "g2": 9.0, "count": 3}],
        "b": [{"word": "a", "g2": 5.0, "count": 3}, {"word": "c", "g2": 3.0, "count": 3}],
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a")
    words = [d["concept"] for d in out]
    assert "a" not in words
    assert "c" in words


@pytest.mark.asyncio
async def test_infer_links_takes_best_strength_across_multiple_paths():
    # c is reachable both via b (weak) and via d (strong) — best (max) wins.
    graph = {
        "a": [{"word": "b", "g2": 2.0, "count": 3}, {"word": "d", "g2": 10.0, "count": 3}],
        "b": [{"word": "c", "g2": 3.0, "count": 3}],   # strength via b = 6
        "d": [{"word": "c", "g2": 8.0, "count": 3}],   # strength via d = 80
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a")
    assert len(out) == 1
    assert out[0] == {"concept": "c", "via": "d", "strength": 80.0, "derived": True}


@pytest.mark.asyncio
async def test_infer_links_respects_limit():
    graph = {
        "a": [{"word": "b", "g2": 10.0, "count": 3}],
        "b": [
            {"word": "c1", "g2": 9.0, "count": 3},
            {"word": "c2", "g2": 8.0, "count": 3},
            {"word": "c3", "g2": 7.0, "count": 3},
        ],
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a", limit=2)
    assert len(out) == 2
    words = [d["concept"] for d in out]
    assert words == ["c1", "c2"]


@pytest.mark.asyncio
async def test_infer_links_returns_empty_when_no_derived_candidates():
    graph = {
        "a": [{"word": "b", "g2": 9.0, "count": 3}],
        "b": [],
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a")
    assert out == []


@pytest.mark.asyncio
async def test_infer_links_forwards_min_count_to_top_associations():
    """/ask needs to relax the edge-count floor to 1 for freshly-learned
    concepts; infer_links must thread a passed min_count through to
    _top_associations for both direct and second-hop lookups."""
    graph = {
        "a": [{"word": "b", "g2": 9.0, "count": 1}],
        "b": [{"word": "c", "g2": 5.0, "count": 1}],
    }
    mock_top = AsyncMock(side_effect=_neighbours_side_effect(graph))
    with patch.object(brain_service, "_top_associations", mock_top):
        await brain_service.infer_links("a", min_count=1)
    mock_top.assert_any_await("a", min_count=1)
    mock_top.assert_any_await("b", min_count=1)


@pytest.mark.asyncio
async def test_infer_links_default_min_count_matches_module_floor():
    mock_top = AsyncMock(return_value=[])
    with patch.object(brain_service, "_top_associations", mock_top):
        await brain_service.infer_links("a")
    mock_top.assert_awaited_once_with("a", min_count=brain_service.MIN_EDGE_COUNT)


@pytest.mark.asyncio
async def test_infer_links_result_shape():
    graph = {
        "a": [{"word": "b", "g2": 9.0, "count": 3}],
        "b": [{"word": "c", "g2": 5.0, "count": 3}],
    }
    with patch.object(brain_service, "_top_associations", AsyncMock(side_effect=_neighbours_side_effect(graph))):
        out = await brain_service.infer_links("a")
    assert set(out[0].keys()) == {"concept", "via", "strength", "derived"}
    assert out[0]["derived"] is True
