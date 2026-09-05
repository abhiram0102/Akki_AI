from collections import Counter
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.services import brain_learn

class _Result:
    def __init__(self, rows): self._rows = rows
    def __aiter__(self):
        async def gen():
            for r in self._rows: yield r
        return gen()

@pytest.mark.asyncio
async def test_apply_to_graph_upserts_and_returns_counts():
    session = MagicMock()
    # 1st run: concept upsert -> rows with word/frequency/total
    # 2nd run: edge upsert -> rows with cause/effect/count
    # 3rd run: g2 writeback -> no rows needed
    session.run = AsyncMock(side_effect=[
        _Result([{"word": "fire", "frequency": 3, "total": 10},
                 {"word": "heat", "frequency": 2, "total": 10}]),
        _Result([{"cause": "fire", "effect": "heat", "count": 2}]),
        _Result([]),
    ])
    out = await brain_learn.apply_to_graph(session, Counter({"fire": 1, "heat": 1}),
                                           Counter({("fire", "heat"): 1}))
    assert out["new_edges"] == 1
    assert session.run.await_count == 3


@pytest.mark.asyncio
async def test_resolve_title_uses_opensearch():
    client = MagicMock()
    resp = MagicMock(); resp.json = MagicMock(return_value=["neuron", ["Neuron"], [""], ["url"]])
    resp.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=resp)
    assert await brain_learn.resolve_wikipedia_title("neurons", client) == "Neuron"


@pytest.mark.asyncio
async def test_resolve_title_falls_back_on_error():
    client = MagicMock(); client.get = AsyncMock(side_effect=Exception("net"))
    assert await brain_learn.resolve_wikipedia_title("quantum tunneling", client) == "Quantum_Tunneling"


@pytest.mark.asyncio
async def test_learn_concept_fetches_extracts_and_applies(monkeypatch):
    client = MagicMock()
    resp = MagicMock()
    resp.json = MagicMock(return_value=["neurons", ["Neuron"], [""], ["url"]])
    resp.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=resp)

    fetch_mock = AsyncMock(return_value=("Fire causes heat. Heat spreads energy.", []))
    monkeypatch.setattr(brain_learn, "fetch_wikipedia", fetch_mock)

    def fake_extract(sentence):
        if sentence.startswith("Fire"):
            return [("fire", "heat")]
        if sentence.startswith("Heat"):
            return [("heat", "energy")]
        return []
    monkeypatch.setattr(brain_learn, "extract_dependencies", fake_extract)

    apply_mock = AsyncMock(return_value={"new_concepts": 3, "new_edges": 2})
    monkeypatch.setattr(brain_learn, "apply_to_graph", apply_mock)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    neo4j_driver = MagicMock()
    neo4j_driver.session = MagicMock(return_value=session_cm)

    out = await brain_learn.learn_concept("neurons", client, neo4j_driver, follow_links=0)

    assert out["term"] == "neurons"
    assert out["resolved_title"] == "Neuron"
    assert out["new_concepts"] == 3
    assert out["new_edges"] == 2
    assert out["sources"] == ["https://en.wikipedia.org/wiki/Neuron"]
    fetch_mock.assert_awaited_once_with("https://en.wikipedia.org/wiki/Neuron", client)
    apply_mock.assert_awaited_once()
