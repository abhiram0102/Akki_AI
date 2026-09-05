"""Regression test: crawl_one_page must delegate graph writes to the shared
brain_learn.apply_to_graph engine instead of owning its own Cypher upserts —
guards against the crawler and on-demand learn path drifting apart again."""
from collections import Counter
from unittest.mock import AsyncMock, MagicMock, patch

from backend import brain_crawler
from backend.services import brain_learn


def _fake_pg_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def _fake_neo4j_driver():
    driver = MagicMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    driver.session.return_value = session_cm
    return driver


class TestCrawlerUsesLearnEngine:
    async def test_crawl_one_page_delegates_graph_writes_to_apply_to_graph(self):
        entry = {"url": "https://en.wikipedia.org/wiki/Fire", "concept": "fire", "source_type": "wikipedia"}
        neo4j_driver = _fake_neo4j_driver()
        pg_session = _fake_pg_session()

        # extract_dependencies is mocked here (not the real spaCy model) —
        # its own behaviour is covered by backend/tests/test_brain_nlp.py;
        # this test only needs to verify crawl_one_page wires the resulting
        # Counters into apply_to_graph, so we don't want it flaking on
        # whatever NLP model happens to be installed in a given environment.
        with patch.object(brain_crawler, "fetch_structure", AsyncMock(
            return_value={"text": "Fire causes heat.", "sentences": ["Fire causes heat."],
                          "links": [], "delimiters": ("<", ">"), "terminators": ["."]}
        )), patch.object(brain_crawler, "extract_dependencies", MagicMock(
            return_value=[("fire", "heat")]
        )), patch.object(brain_learn, "apply_to_graph", AsyncMock(
            return_value={"new_concepts": 2, "new_edges": 1}
        )) as mock_apply:
            result = await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=neo4j_driver, pg_session=pg_session,
            )

        # Success returns the sentence count, unchanged by the refactor.
        assert result == 1  # "Fire causes heat." -> 1 sentence

        mock_apply.assert_awaited_once()
        session_arg, word_freq_arg, edge_counts_arg = mock_apply.await_args.args
        assert session_arg is neo4j_driver.session.return_value

        assert isinstance(word_freq_arg, Counter)
        assert isinstance(edge_counts_arg, Counter)
        assert edge_counts_arg[("fire", "heat")] == 1
        assert word_freq_arg["fire"] == 1
        assert word_freq_arg["heat"] == 1

        # The crawler must no longer issue Cypher itself — all graph writes
        # go through the shared engine, which is mocked here.
        neo4j_driver.session.return_value.run.assert_not_called()
