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

        # One fetcher for every source now, returning already-discovered
        # structure rather than raw text the caller has to re-split.
        with patch.object(brain_crawler, "fetch_structure", AsyncMock(
            return_value={
                "text": "Fire causes heat. Heat leads to energy.",
                "sentences": ["Fire causes heat.", "Heat leads to energy."],
                "links": ["https://en.wikipedia.org/wiki/Heat"],
                "delimiters": ("<", ">"), "terminators": ["."],
            }
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
        with patch.object(brain_crawler, "fetch_structure", AsyncMock(side_effect=Exception("timeout"))):
            result = await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=_fake_neo4j_driver(), pg_session=_fake_pg_session(),
            )
        # A fetch failure returns None (not raised, not a count).
        assert result is None


class TestAdaptiveReading:
    """How much of a page to read is decided by the page, not by a constant.

    A fixed sentence cap assumes information is front-loaded. Measured on two
    real pages, that is true of one and false of the other: a Wikipedia
    article's relations-per-sentence runs 0.54, 0.44, 0.31, 0.05 by
    hundred-sentence band, while an encyclopedia essay runs 0.26, 0.27, 0.39,
    0.45 -- its two richest bands sit just past where a 200-sentence cap would
    have stopped.
    """

    @staticmethod
    def _extract_from(yields: dict):
        """An extractor whose productivity varies by sentence index, so a test
        can describe a page's shape directly."""
        def extract(sentence):
            index = int(sentence.split()[-1])
            band = index // 100
            return [("a", "b")] * yields.get(band, 0)
        return extract

    @staticmethod
    def _page(count: int):
        return [f"sentence number {i}" for i in range(count)]

    def test_reading_stops_when_a_page_stops_producing(self):
        """The Wikipedia shape: rich opening, then references and see-also,
        which cost NLP time and yield nothing."""
        extract = self._extract_from({0: 5, 1: 4, 2: 3, 3: 0, 4: 0, 5: 0})
        pairs, read = brain_crawler._read_adaptively(self._page(600), extract)
        assert read < 600, "read the whole page including the dead tail"
        assert read >= brain_crawler._MIN_READ

    def test_reading_continues_while_a_page_is_still_producing(self):
        """The essay shape. This is the case a fixed cap gets wrong: the page
        is at its most productive exactly where the old cap stopped."""
        extract = self._extract_from({0: 2, 1: 2, 2: 4, 3: 5, 4: 2, 5: 0})
        pairs, read = brain_crawler._read_adaptively(self._page(600), extract)
        assert read > 200, (
            f"stopped at {read} sentences, discarding the most productive part "
            "of the page"
        )
        assert len(pairs) > 200 * 2, "gathered no more than a 200-sentence cap would"

    def test_a_quiet_opening_does_not_end_the_reading(self):
        """A page whose first block happens to be thin must not be abandoned
        on that evidence -- which is what `_MIN_READ` protects against."""
        extract = self._extract_from({0: 0, 1: 3, 2: 4, 3: 4})
        pairs, read = brain_crawler._read_adaptively(self._page(400), extract)
        assert read >= brain_crawler._MIN_READ
        assert pairs, "abandoned a productive page because it opened quietly"

    def test_a_page_that_never_stops_producing_is_still_bounded(self):
        """One page cannot be allowed to consume the whole crawl."""
        extract = self._extract_from({i: 5 for i in range(40)})
        _, read = brain_crawler._read_adaptively(self._page(4000), extract)
        assert read <= brain_crawler._MAX_READ

    def test_an_extraction_failure_does_not_abort_the_page(self):
        """One unparseable sentence must not cost the rest of the page."""
        def extract(sentence):
            if sentence.endswith("7"):
                raise ValueError("unparseable")
            return [("a", "b")]
        pairs, read = brain_crawler._read_adaptively(self._page(300), extract)
        assert read == 300
        assert len(pairs) == 300 - 30  # every sentence ending in 7
