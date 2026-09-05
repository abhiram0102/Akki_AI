"""Tests for the crawler's per-page processing logic — mocked fetchers,
Neo4j driver, and Postgres session, so no live services are needed."""
from unittest.mock import AsyncMock, MagicMock, patch

from backend import brain_crawler


def _fake_pg_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


class _FakeNeo4jResult:
    """An async-iterable fake Neo4j result yielding no records by default —
    enough for the crawler's `async for record in result:` loops to run
    without error while asserting call counts, not record content."""
    def __aiter__(self):
        async def _empty():
            return
            yield
        return _empty()


def _fake_neo4j_driver():
    driver = MagicMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = AsyncMock(return_value=_FakeNeo4jResult())
    driver.session.return_value = session_cm
    return driver


class TestCrawlOnePage:
    async def test_successful_page_writes_to_both_stores(self):
        entry = {"url": "https://en.wikipedia.org/wiki/Fire", "concept": "fire", "source_type": "wikipedia"}
        neo4j_driver = _fake_neo4j_driver()
        pg_session = _fake_pg_session()

        with patch.object(brain_crawler, "fetch_wikipedia", AsyncMock(
            return_value=("Fire causes heat. Heat leads to energy.", ["https://en.wikipedia.org/wiki/Heat"])
        )):
            result = await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=neo4j_driver, pg_session=pg_session,
            )

        # Success returns the sentence count (an int >= 0), not None.
        assert result is not None
        assert isinstance(result, int) and result >= 1  # "Fire causes heat. Heat leads to energy." -> 2 sentences
        assert neo4j_driver.session.return_value.run.await_count >= 1
        assert pg_session.execute.await_count >= 1  # visited page + frontier insert
        pg_session.commit.assert_awaited()

    async def test_robots_disallowed_page_is_skipped_not_failed(self):
        entry = {"url": "https://en.wikipedia.org/wiki/Special:Random", "concept": "random", "source_type": "wikipedia"}
        result = await brain_crawler.crawl_one_page(
            entry, client=AsyncMock(),
            robots=AsyncMock(allowed=AsyncMock(return_value=False)),
            limiter=AsyncMock(wait=AsyncMock()),
            neo4j_driver=_fake_neo4j_driver(), pg_session=_fake_pg_session(),
        )
        # A skipped (robots-disallowed) page returns None, not a count.
        assert result is None

    async def test_fetch_failure_returns_none_without_raising(self):
        entry = {"url": "https://en.wikipedia.org/wiki/Broken", "concept": "broken", "source_type": "wikipedia"}
        with patch.object(brain_crawler, "fetch_wikipedia", AsyncMock(side_effect=Exception("timeout"))):
            result = await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=_fake_neo4j_driver(), pg_session=_fake_pg_session(),
            )
        # A fetch failure returns None (not raised, not a count).
        assert result is None
