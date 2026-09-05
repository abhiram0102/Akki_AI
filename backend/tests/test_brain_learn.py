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
