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
            return [("a", "verb", "b")] * yields.get(band, 0)
        return extract

    @staticmethod
    def _page(count: int):
        return [f"sentence number {i}" for i in range(count)]

    def test_reading_stops_when_a_page_stops_producing(self):
        """The Wikipedia shape: rich opening, then references and see-also,
        which cost NLP time and yield nothing."""
        extract = self._extract_from({0: 5, 1: 4, 2: 3, 3: 0, 4: 0, 5: 0})
        pairs, read, _ctx = brain_crawler._read_adaptively(self._page(600), extract)
        assert read < 600, "read the whole page including the dead tail"
        assert read >= brain_crawler._MIN_READ

    def test_reading_continues_while_a_page_is_still_producing(self):
        """The essay shape. This is the case a fixed cap gets wrong: the page
        is at its most productive exactly where the old cap stopped."""
        extract = self._extract_from({0: 2, 1: 2, 2: 4, 3: 5, 4: 2, 5: 0})
        pairs, read, _ctx = brain_crawler._read_adaptively(self._page(600), extract)
        assert read > 200, (
            f"stopped at {read} sentences, discarding the most productive part "
            "of the page"
        )
        assert len(pairs) > 200 * 2, "gathered no more than a 200-sentence cap would"

    def test_a_quiet_opening_does_not_end_the_reading(self):
        """A page whose first block happens to be thin must not be abandoned
        on that evidence -- which is what `_MIN_READ` protects against."""
        extract = self._extract_from({0: 0, 1: 3, 2: 4, 3: 4})
        pairs, read, _ctx = brain_crawler._read_adaptively(self._page(400), extract)
        assert read >= brain_crawler._MIN_READ
        assert pairs, "abandoned a productive page because it opened quietly"

    def test_a_page_that_never_stops_producing_is_still_bounded(self):
        """One page cannot be allowed to consume the whole crawl."""
        extract = self._extract_from({i: 5 for i in range(40)})
        _, read, _ctx = brain_crawler._read_adaptively(self._page(4000), extract)
        assert read <= brain_crawler._MAX_READ

    def test_an_extraction_failure_does_not_abort_the_page(self):
        """One unparseable sentence must not cost the rest of the page."""
        def extract(sentence):
            if sentence.endswith("7"):
                raise ValueError("unparseable")
            return [("a", "verb", "b")]
        pairs, read, _ctx = brain_crawler._read_adaptively(self._page(300), extract)
        assert read == 300
        assert len(pairs) == 300 - 30  # every sentence ending in 7


def test_the_crawler_module_can_actually_start():
    """A regression guard for a fault that no test could see and that the
    running container hid for eighteen hours.

    `main()` installed signal handlers referring to `_signal_handler`, which had
    been dropped from the module. The crawler therefore raised NameError on the
    first line of startup and could not run at all from source -- but the
    container had been started from an older image and never restarted, so it
    kept running the code that still had them. The fault only surfaced on a
    restart.

    Nothing here imports `main()`, so nothing caught it. This asserts the names
    startup depends on are present and that the shutdown flag actually flips."""
    assert brain_crawler._running is True or brain_crawler._running is False
    original = brain_crawler._running
    try:
        brain_crawler._signal_handler(15, None)
        assert brain_crawler._running is False, "a termination signal did not stop the loop"
    finally:
        brain_crawler._running = original


def test_the_read_floor_stays_below_the_cap_it_replaced():
    """The floor must leave room for the mechanism to SAVE time, not only spend it.

    It was first set to 200, the same value as the fixed cap it replaced. That
    made adaptive reading purely additive: a page could be read more than
    before but never less, so the extra time spent on productive pages was
    never paid back on pages that die early. Live crawl rate fell from roughly
    1,450-2,000 pages/hour to 810.

    This is the invariant that was violated, stated so it cannot be violated
    again by someone raising the floor to be safe."""
    assert brain_crawler._MIN_READ < 200, (
        "the read floor is at or above the old fixed cap, so adaptive reading "
        "can only ever read more than the cap did and never less"
    )
    assert brain_crawler._MIN_READ >= brain_crawler._BLOCK * 2, (
        "fewer than two blocks is not enough evidence to judge a page"
    )


def test_an_unproductive_page_now_stops_before_the_old_cap():
    """The behaviour the floor change buys: a page that dies early must cost
    less than the fixed cap did, or the mechanism has no upside on the many
    pages that are mostly navigation."""
    def extract(sentence):
        index = int(sentence.split()[-1])
        return [("a", "verb", "b")] * (4 if index < 50 else 0)

    sentences = [f"sentence number {i}" for i in range(600)]
    _, read, _ctx = brain_crawler._read_adaptively(sentences, extract)
    assert read < 200, (
        f"read {read} sentences of a page that stopped producing after 50; "
        "the old fixed cap would have read 200"
    )


# --- Curiosity entries must preempt the bulk frontier -----------------------
#
# The frontier query was `select(BrainFrontier).limit(BATCH_SIZE)` with no
# ORDER BY, so Postgres returned rows in whatever order it liked -- in practice
# heap order, which is insertion order. With 466,850 discovered URLs already
# queued and the crawler reading ~1,200 an hour, anything queued today would
# not be reached for roughly two weeks, and the frontier grows faster than it
# drains, so "roughly two weeks" is optimistic.
#
# That makes curiosity pointless by construction. The entire claim of the
# curiosity loop is that the brain reads what it just discovered it does not
# know; a queue position two weeks out is indistinguishable from never.

class _StubResult:
    def __init__(self, rows): self._rows = rows
    def scalars(self): return self
    def all(self): return self._rows
    def scalar_one_or_none(self): return self._rows[0] if self._rows else None


class _RecordingSession:
    """Stands in for the database, and records the statements it was asked to
    run so a test can assert WHAT was asked for, not merely that something was."""
    def __init__(self, *results):
        self._results = list(results)
        self.statements = []

    async def execute(self, statement, *a, **kw):
        self.statements.append(str(statement.compile(
            compile_kwargs={"literal_binds": True})))
        return self._results.pop(0) if self._results else _StubResult([])


def _entry(url, source_type):
    from backend.models import BrainFrontier
    return BrainFrontier(url=url, concept="c", source_type=source_type)


class TestFrontierPriority:
    async def test_curiosity_entries_are_returned_before_bulk_entries(self):
        """A curiosity entry queued last is still read first.

        The batch is still filled to `limit` from the bulk frontier afterwards.
        Returning the one curious entry alone would cut a 20-page batch to a
        single page and re-query the frontier twenty times as often, which
        trades one starvation problem for another.
        """
        curious = _entry("https://x/curious", "curiosity:unknown")
        bulk = _entry("https://x/bulk", "wikipedia")
        session = _RecordingSession(_StubResult([curious]), _StubResult([bulk]))

        batch = await brain_crawler.select_frontier_batch(session, limit=20)

        assert [e.url for e in batch] == ["https://x/curious", "https://x/bulk"]

    async def test_bulk_frontier_is_read_when_nothing_is_curious(self):
        """Priority must not starve the ordinary crawl."""
        bulk = _entry("https://x/bulk", "wikipedia")
        session = _RecordingSession(_StubResult([]), _StubResult([bulk]))

        batch = await brain_crawler.select_frontier_batch(session, limit=20)

        assert [e.url for e in batch] == ["https://x/bulk"]

    async def test_the_prioritised_query_actually_asks_for_curiosity_entries(self):
        """Pins WHICH kind of entry is prioritised.

        Without this the two tests above pass for an implementation that runs
        two arbitrary queries in a fixed order, which would prioritise nothing.
        """
        from backend.services import brain_curiosity
        session = _RecordingSession(_StubResult([]), _StubResult([]))

        await brain_crawler.select_frontier_batch(session, limit=20)

        assert brain_curiosity.SOURCE_TYPE in session.statements[0]
        assert brain_curiosity.SOURCE_TYPE not in session.statements[1]

    async def test_no_second_query_is_run_when_curiosity_filled_the_batch(self):
        """A full batch of curiosity reading should not also scan the frontier."""
        curious = [_entry(f"https://x/{i}", "curiosity:derived") for i in range(20)]
        session = _RecordingSession(_StubResult(curious))

        batch = await brain_crawler.select_frontier_batch(session, limit=20)

        assert len(batch) == 20
        assert len(session.statements) == 1


class TestFrontierIndex:
    """The prioritised query is a seq scan without help.

    Measured on the live frontier at 466,850 rows: 1,398 ms per batch, a
    parallel sequential scan discarding every row. A batch is twenty pages and
    a page is rate-limited to a second, so that is ~7% of crawl time now and
    grows linearly with a frontier that is growing. A partial index covers only
    curiosity rows, so it stays kilobytes however large the frontier gets.
    """

    async def test_the_index_predicate_matches_the_query_predicate(self):
        """A partial index is only usable if its predicate implies the
        query's. Same LIKE pattern on both sides, from one constant."""
        from backend.services import brain_curiosity
        session = _RecordingSession()

        await brain_crawler.ensure_frontier_index(session)
        ddl = session.statements[0]

        await brain_crawler.select_frontier_batch(session, limit=20)
        query = session.statements[1]

        pattern = f"{brain_curiosity.SOURCE_TYPE}:%"
        assert pattern in ddl and pattern in query

    async def test_creating_the_index_is_idempotent(self):
        """The crawler restarts often; startup must not fail on a second run."""
        session = _RecordingSession()
        await brain_crawler.ensure_frontier_index(session)
        assert "IF NOT EXISTS" in session.statements[0].upper()

    async def test_a_database_that_refuses_the_index_does_not_stop_the_crawl(self):
        """An index is an optimisation. Losing it should cost speed, not the
        brain's ability to read."""
        class _Refuses:
            async def execute(self, *a, **kw): raise RuntimeError("no permission")
            async def commit(self): pass

        await brain_crawler.ensure_frontier_index(_Refuses())  # must not raise


class TestCuriosityDoesNotPropagate:
    """A curiosity marker describes why a page was QUEUED, not where it came from.

    Found in production within minutes of the priority fix going live. The
    crawler stamps every link it discovers with the source_type of the page it
    was discovered on. That was harmless while every page was `wikipedia`.
    Once one page carried `curiosity:derived`, reading it minted 96 more
    `curiosity:derived` frontier entries -- including a long tail of people
    called David Smith -- each of which would mint its own on being read.

    Two failures, either of which alone would be enough:

    - The curiosity lane grows exponentially and swallows the crawl, which is
      precisely the starvation `select_frontier_batch` claims cannot happen.
    - `measure_effectiveness` reads these back as outcomes of the `derived`
      bet. The feedback signal the whole loop turns on would be measuring
      pages curiosity never asked for.
    """

    def test_a_curiosity_read_does_not_mint_curiosity_entries(self):
        from backend.services import brain_curiosity
        inherited = brain_crawler.discovered_source_type("curiosity:derived")
        assert not inherited.startswith(brain_curiosity.SOURCE_TYPE)

    def test_an_ordinary_source_type_is_still_carried_to_its_links(self):
        """Only the priority marker is stripped. Provenance is untouched."""
        assert brain_crawler.discovered_source_type("wikipedia") == "wikipedia"

    def test_every_curiosity_reason_is_stripped_not_just_one(self):
        from backend.services import brain_curiosity
        for reason in (brain_curiosity.REASON_UNKNOWN,
                       brain_curiosity.REASON_DERIVED,
                       brain_curiosity.REASON_THIN):
            out = brain_crawler.discovered_source_type(
                f"{brain_curiosity.SOURCE_TYPE}:{reason}")
            assert not out.startswith(brain_curiosity.SOURCE_TYPE), reason

    def test_the_stripped_marker_is_not_empty(self):
        """A blank source_type would violate the column's NOT NULL intent and
        make the row unattributable."""
        assert brain_crawler.discovered_source_type("curiosity:unknown")


class TestPruningGivesNewKnowledgeProbation:
    """The pruner was deleting what the brain had just learned.

    Every 200 pages -- roughly ten minutes -- it ran:

        MATCH (:Concept)-[r:CO_OCCURS]->() WHERE r.count < 2 DELETE r
        MATCH (c:Concept) WHERE NOT (c)-[:CO_OCCURS]-() DELETE c

    A concept read on exactly ONE page has most of its edges at count 1. They
    were deleted, the concept was orphaned, then the concept was deleted too.
    A single read of something new mostly evaporated within ten minutes unless
    the crawler happened to meet it again first.

    Measured live by running the pruner's own predicates as a count, rather
    than inferring it: the next prune would have deleted 7,751 edges and 6,461
    concepts -- 12% of a 55,225-concept graph -- including 12 of the 27 edges
    `quasicrystal` had just been read to obtain. `quasicrystal` had in fact
    already been deleted once this way, despite its page being read with 200
    sentences forty minutes earlier.

    This is the bottom of the bucket the curiosity loop pours into. Curiosity
    exists to read things the brain does not know, and a thing it does not know
    is by definition one it has seen once.

    The dust the pruner was built to control is real (its comment records 83%
    of the graph going edgeless). So thin edges are still swept -- just not
    before they have had a fair chance to be seen a second time.
    """

    def test_a_thin_edge_is_not_deleted_the_moment_it_is_written(self):
        cypher = brain_crawler.thin_edge_prune_cypher()
        assert "last_updated" in cypher, \
            "sweeping by count alone deletes knowledge written seconds ago"

    def test_a_thin_edge_is_still_swept_once_it_has_had_its_chance(self):
        """Probation, not amnesty. The dust problem was real."""
        cypher = brain_crawler.thin_edge_prune_cypher()
        assert "DELETE" in cypher.upper() and "r.count" in cypher

    def test_a_freshly_learned_concept_is_not_deleted_as_an_orphan(self):
        """Orphan deletion is what actually loses the concept, so it needs the
        same probation -- otherwise a concept survives edge-pruning only to be
        swept by the next statement."""
        cypher = brain_crawler.orphan_prune_cypher()
        assert "first_seen" in cypher, \
            "a concept learned moments ago is not dust"

    def test_both_prunes_use_one_probation_window(self):
        """Two different windows would let a concept lose its edges under one
        rule and survive as an orphan under the other."""
        assert brain_crawler.PROBATION_HOURS > 0
        window = f"{brain_crawler.PROBATION_HOURS}"
        assert window in brain_crawler.thin_edge_prune_cypher()
        assert window in brain_crawler.orphan_prune_cypher()

    async def test_pruning_failure_does_not_stop_the_crawl(self):
        class _Boom:
            def session(self): raise RuntimeError("neo4j unavailable")
        await brain_crawler._prune_low_value_edges(_Boom())  # must not raise


class TestTheCrawlerFeedsTheMeaningLayer:
    """`record_contexts` was reachable only from the learn-on-demand path.

    `brain_learn` records, for every concept it extracts, the sentence it came
    from -- that store is what `brain_meaning` clusters into word senses. The
    CRAWLER never called it. So the meaning layer saw only the handful of
    concepts learned by an `/ask` miss, and none of the 40,000 pages the
    crawler read.

    Combined with two other defects in the same feature -- chromadb absent from
    the image, and the store on an unmounted per-container path -- word senses
    could not have worked in production under any circumstances. That is why
    "what causes inflation" answered with `universe` and
    `thermodynamic equilibrium`: cosmological inflation and economic inflation
    were one undifferentiated node.
    """

    def test_reading_returns_the_sentence_each_concept_came_from(self):
        """Sense discovery clusters CONTEXTS, so a bare concept list is not
        enough -- the sentence has to survive the parse."""
        sentences = ["fire causes heat", "heat causes expansion"]

        def extract(s):
            w = s.split()
            return [(w[0], w[0], w[-1])]

        _triples, _read, contexts = brain_crawler._read_adaptively(sentences, extract)

        assert contexts["fire"] == ["fire causes heat"]
        assert "heat causes expansion" in contexts["heat"]

    def test_a_concept_seen_in_two_sentences_keeps_both(self):
        """One sentence per concept would make every word single-sense by
        construction, which is the bug this exists to fix."""
        sentences = ["fire burns wood", "fire warms house"]

        def extract(s):
            w = s.split()
            return [(w[0], w[1], w[-1])]

        _t, _r, contexts = brain_crawler._read_adaptively(sentences, extract)

        assert len(contexts["fire"]) == 2

    async def test_crawling_a_page_records_those_contexts(self):
        """The end of the wire: what the crawler read reaches the sense store."""
        recorded = {}

        def _record(concept, sentences):
            recorded[concept] = sentences
            return len(sentences)

        with patch.object(brain_crawler.brain_meaning, "record_contexts", _record):
            brain_crawler._record_page_contexts({"fire": ["fire causes heat"]})

        assert recorded == {"fire": ["fire causes heat"]}


class TestReadingJudgesTheBrainsOwnClaims:
    """The falsification loop's crawler end.

    Curiosity queues a derived link -- an inference no source stated -- so the
    brain can go and check it. Reading the page is only half of that: something
    has to look at what came back and decide whether the inference held.
    Without this the brain reads to test itself and then never opens the
    result.
    """

    async def test_reading_a_page_adjudicates_claims_about_its_concept(self):
        judged = {}

        async def _adjudicate(pg, neo, concept):
            judged["concept"] = concept
            return {"confirmed": 1, "unsupported": 0}

        entry = {"url": "https://x/nucleus", "concept": "nucleus",
                 "source_type": "curiosity:derived"}

        with patch.object(brain_crawler, "fetch_structure", AsyncMock(return_value={
            "text": "Nucleus holds chromosomes.",
            "sentences": ["Nucleus holds chromosomes."],
            "links": [], "delimiters": ("<", ">"), "terminators": ["."],
        })), patch.object(brain_crawler.brain_hypothesis, "adjudicate", _adjudicate):
            await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=_fake_neo4j_driver(), pg_session=_fake_pg_session(),
            )

        assert judged["concept"] == "nucleus", \
            "a page was read to test a claim and nothing checked the result"

    async def test_a_page_still_counts_when_adjudication_fails(self):
        """Judging is bookkeeping. Losing it must not lose the reading."""
        async def _boom(pg, neo, concept):
            raise RuntimeError("adjudication exploded")

        entry = {"url": "https://x/n", "concept": "n", "source_type": "wikipedia"}

        with patch.object(brain_crawler, "fetch_structure", AsyncMock(return_value={
            "text": "A causes b.", "sentences": ["A causes b."],
            "links": [], "delimiters": ("<", ">"), "terminators": ["."],
        })), patch.object(brain_crawler.brain_hypothesis, "adjudicate", _boom):
            result = await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=_fake_neo4j_driver(), pg_session=_fake_pg_session(),
            )

        assert result is not None
