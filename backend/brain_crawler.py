"""AKKI Brain Engine — production crawler.

Runs continuously (python -m backend.brain_crawler). Fetches from
Wikipedia, arXiv, and one configured RSS news feed; extracts relationships
via spaCy dependency parsing; writes concepts/edges to Neo4j and crawl
state to Postgres. Replaces the original brain/run.py prototype's
single-threaded, pickle-persisted, regex-extraction design.
"""
import asyncio
import logging
import os
import signal
from collections import Counter
from urllib.parse import urlparse
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import AsyncSessionLocal
from backend.models import BrainFrontier, BrainVisitedPage, BrainDeadLetter, BrainStats
from backend.services import brain_learn
from backend.services.neo4j_service import get_driver, ensure_schema
from backend.services.brain_fetchers import (
    RobotsChecker, RateLimiter, fetch_structure,
)
from backend.services.brain_nlp import extract_dependencies

logger = logging.getLogger("akki.brain_crawler")

# A SINGLE starting signal, not a curated seed list.
#
# This was fifteen hardcoded Wikipedia URLs, each with a hand-written concept
# name and a source type. That is exactly the hardcoded seeding the project's
# constraint forbids: it decides in advance what the brain is allowed to know
# about and which site it must learn it from.
#
# The brain now starts from one address and finds everything else by following
# what the documents themselves point at, with structure discovered per page.
# Point it anywhere; the crawl is no longer tied to one site's conventions.
BRAIN_START_URL = os.getenv(
    "BRAIN_START_URL", "https://en.wikipedia.org/wiki/Knowledge"
)

MAX_ATTEMPTS = 3
PRUNE_EVERY_N_PAGES = 200
BATCH_SIZE = 20


# Set false by a termination signal so the loop finishes the page it is on and
# stops cleanly, rather than being killed mid-write and leaving a frontier
# entry claimed but unrecorded.
#
# This and `_signal_handler` were referenced by `main()` but had been lost from
# the module, so the crawler raised NameError on the first line of startup and
# could not run at all from source. It went unnoticed because the container was
# started from an older image and never restarted; the fault only appears on a
# restart. Restored rather than removed: `while _running` in the main loop is
# the graceful-shutdown path, and without it a SIGTERM kills the process
# mid-page.
_running = True


def _signal_handler(sig, frame):
    global _running
    logger.info("Signal %s received - finishing current page, then stopping.", sig)
    _running = False


# How much of a page to read. Sentences are parsed in blocks, and reading stops
# when a block stops producing -- the page itself says when it is finished,
# rather than a fixed count deciding for it.
#
# A fixed cap was measured against two real pages and is wrong on one of them,
# because it assumes information is front-loaded, which is an assumption about
# document layout and not a property of documents. Relations per sentence, by
# hundred-sentence band:
#
#   Wikipedia article:  0.54  0.44  0.31  0.05  0.02  0.09
#   Encyclopedia essay: 0.26  0.27  0.39  0.45  0.26  0.01  0.00
#
# The article is front-loaded and a cap at 200 costs it almost nothing. The
# essay's two RICHEST bands are the two immediately after 200, so the same cap
# discards the best part of it. Both collapse to near zero eventually -- at
# different places -- which is the signal worth acting on.
_BLOCK = int(os.getenv("BRAIN_READ_BLOCK", "50"))

# Read this much before judging, because the opening of a page is not always
# representative and a quiet first block should not end a good page.
#
# This MUST stay below the fixed cap it replaced, and that was learned in
# production rather than reasoned. It was first set to 200 -- the same value as
# the old cap -- which meant a page could only ever be read MORE than before
# and never less: the mechanism spent extra time on productive pages and never
# once paid any of it back on pages that die early. That is half the idea. Live
# crawl rate fell from ~1,450-2,000 pages/hour to ~810 as a result, with a
# 500-sentence page taking 27 seconds.
#
# At 100 an unproductive page stops after two blocks instead of four. Sweeping
# 50/100/150/200 over the stored corpus changes nothing on either page there,
# because both stay productive well past 200 -- which is precisely why the
# corpus cannot calibrate this and the live read-distribution has to.
_MIN_READ = int(os.getenv("BRAIN_READ_MIN", "100"))

# A hard ceiling, so a pathological page cannot consume the whole crawl. At
# roughly 10ms a sentence this bounds one page at about 12 seconds of parsing,
# against a 1.0s politeness interval -- deliberately generous, because
# truncating a genuinely rich page is the fault this whole mechanism exists to
# fix. Live pages have not exceeded ~700.
_MAX_READ = int(os.getenv("BRAIN_READ_MAX", "1200"))

# Stop when a block yields less than this share of the best block seen so far.
# The same share-of-best rule already used to pick sentence terminators.
_YIELD_SHARE = float(os.getenv("BRAIN_READ_SHARE", "0.2"))


def _read_adaptively(sentences: list[str], extract) -> tuple[list, int]:
    """Parse blocks of sentences while the page is still producing relations.

    Returns the pairs found and how many sentences were actually read, so the
    caller can record what the page cost as well as what it gave.
    """
    pairs: list = []
    best = 0.0
    read = 0
    for start in range(0, min(len(sentences), _MAX_READ), _BLOCK):
        block = sentences[start:start + _BLOCK]
        if not block:
            break
        found = []
        for sentence in block:
            try:
                found.extend(extract(sentence))
            except Exception:
                continue
        pairs.extend(found)
        read += len(block)

        yield_rate = len(found) / len(block)
        best = max(best, yield_rate)
        if read >= _MIN_READ and yield_rate < best * _YIELD_SHARE:
            break
    return pairs, read


async def crawl_one_page(entry: dict, client, robots: RobotsChecker, limiter: RateLimiter,
                          neo4j_driver, pg_session) -> int | None:
    """Fetch, extract, and persist one frontier entry.

    Returns the number of sentences learned from the page on success (an int
    >= 0), or None if the page was skipped (robots.txt disallow) or failed to
    fetch. Callers treat `None` as failure and any int as success.
    """
    url, concept, source_type = entry["url"], entry["concept"], entry["source_type"]

    if not await robots.allowed(url, client):
        logger.info("Skipping (robots.txt disallows): %s", url)
        return None

    await limiter.wait(url)

    # One fetcher for every source. There is no source_type dispatch any more
    # because there is nothing site-specific left to dispatch to: structure is
    # discovered per document. `source_type` survives only as a label recording
    # where a frontier entry came from.
    try:
        structure = await fetch_structure(url, client)
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        return None
    sentences = structure["sentences"]
    links = structure["links"]

    # Sentences arrive already split at boundaries discovered from this
    # document, rather than cut on a hardcoded ". ". Minimum 3 words is the
    # grammatical floor for extract_dependencies to find a subject-verb-object
    # triple ("Fire causes heat" is exactly 3).
    sentences = [s for s in sentences if len(s.split()) >= 3]
    pairs, sentences_read = _read_adaptively(sentences, extract_dependencies)

    word_freq: Counter = Counter()
    edge_counts: Counter = Counter()
    for cause, effect in pairs:
        word_freq[cause] += 1
        word_freq[effect] += 1
        edge_counts[(cause, effect)] += 1

    async with neo4j_driver.session() as session:
        await brain_learn.apply_to_graph(session, word_freq, edge_counts)

    await pg_session.execute(
        pg_insert(BrainVisitedPage).values(
            url=url, concept=concept, source_type=source_type,
            sentences_learned=sentences_read,
        ).on_conflict_do_nothing()
    )
    await pg_session.execute(delete(BrainFrontier).where(BrainFrontier.url == url))

    # A frontier entry's `concept` is a label for logging and for grouping, not
    # knowledge. Deriving it used to assume a site's URL convention (last path
    # segment, underscores as spaces) — Wikipedia's convention, applied to
    # every site. It now carries the referring page's concept instead, which
    # assumes nothing about how any site builds its addresses. What the page is
    # actually about is decided by reading it.
    new_links = [
        {"url": link, "concept": concept, "source_type": source_type}
        for link in links
    ]
    if new_links:
        await pg_session.execute(
            pg_insert(BrainFrontier).values(new_links).on_conflict_do_nothing()
        )

    await pg_session.commit()
    return sentences_read


async def _record_failure(pg_session, url: str, source_type: str, error: str) -> None:
    result = await pg_session.execute(select(BrainDeadLetter).where(BrainDeadLetter.url == url))
    existing = result.scalar_one_or_none()
    if existing:
        existing.attempts += 1
        existing.error = error
        existing.last_attempt_at = datetime.now(timezone.utc)
        if existing.attempts >= MAX_ATTEMPTS:
            await pg_session.execute(delete(BrainFrontier).where(BrainFrontier.url == url))
    else:
        pg_session.add(BrainDeadLetter(url=url, source_type=source_type, error=error, attempts=1))
    await pg_session.commit()


async def _prune_low_value_edges(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (:Concept)-[r:CO_OCCURS]->() WHERE r.count < 2 DELETE r"
        )
        await session.run(
            "MATCH (a:Concept)-[r:CO_OCCURS]->() "
            "WITH a, r ORDER BY r.count DESC "
            "WITH a, collect(r) AS rels "
            "UNWIND rels[50..] AS excess "
            "DELETE excess"
        )
        # Delete concepts left with no edges after pruning. Previously these
        # orphans accumulated (83% of the graph became edgeless dust); a concept
        # with no connections is not knowledge, so remove it.
        await session.run(
            "MATCH (c:Concept) WHERE NOT (c)-[:CO_OCCURS]-() DELETE c"
        )
    logger.info("Pruning complete: dropped low-count/long-tail edges and orphaned concepts.")


async def main() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    neo4j_driver = get_driver()
    await ensure_schema()

    robots = RobotsChecker()
    limiter = RateLimiter(min_interval_seconds=1.0)
    pages_since_prune = 0

    # Wikipedia (and many sites) return 403 to the default httpx User-Agent;
    # a descriptive browser-like UA is required to fetch article content.
    # Shared with brain_learn so both paths identify the crawler the same way,
    # including the contact a site's robot policy requires.
    _headers = brain_learn.UA_HEADERS
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_headers) as client:
        async with AsyncSessionLocal() as pg_session:
            # Seed the frontier if empty
            result = await pg_session.execute(select(BrainFrontier).limit(1))
            if result.scalar_one_or_none() is None:
                # One address in. Everything else is discovered by following
                # what the documents point at.
                await pg_session.execute(
                    pg_insert(BrainFrontier).values(
                        url=BRAIN_START_URL,
                        concept=urlparse(BRAIN_START_URL).path.rsplit("/", 1)[-1] or "start",
                        source_type="discovered",
                    ).on_conflict_do_nothing()
                )
                await pg_session.commit()

            logger.info("Brain crawler starting.")

            while _running:
                result = await pg_session.execute(select(BrainFrontier).limit(BATCH_SIZE))
                batch = result.scalars().all()

                if not batch:
                    logger.info("Frontier empty — sleeping 30s before re-checking.")
                    await asyncio.sleep(30)
                    continue

                for entry in batch:
                    if not _running:
                        break
                    entry_dict = {"url": entry.url, "concept": entry.concept, "source_type": entry.source_type}
                    try:
                        sentences_learned = await crawl_one_page(entry_dict, client, robots, limiter, neo4j_driver, pg_session)
                    except Exception as e:
                        logger.error("Unhandled error crawling %s: %s", entry.url, e, exc_info=True)
                        sentences_learned = None

                    if sentences_learned is not None:
                        stats_result = await pg_session.execute(select(BrainStats).where(BrainStats.id == "singleton"))
                        stats = stats_result.scalar_one_or_none()
                        if stats is None:
                            stats = BrainStats(id="singleton", total_pages=0, total_sentences=0)
                            pg_session.add(stats)
                        stats.total_pages += 1
                        stats.total_sentences += sentences_learned
                        await pg_session.commit()
                        pages_since_prune += 1
                    else:
                        await _record_failure(pg_session, entry.url, entry.source_type, "fetch or robots check failed")

                    if pages_since_prune >= PRUNE_EVERY_N_PAGES:
                        await _prune_low_value_edges(neo4j_driver)
                        pages_since_prune = 0

    logger.info("Brain crawler stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
