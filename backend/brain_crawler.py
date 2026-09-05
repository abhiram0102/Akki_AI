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
    pairs: list[tuple[str, str]] = []
    for sentence in sentences[:200]:  # cap per-page NLP cost
        try:
            pairs.extend(extract_dependencies(sentence))
        except Exception:
            continue

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
            sentences_learned=len(sentences),
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
    return len(sentences)


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
    _headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AKKI-Brain/1.0; +knowledge-graph research crawler)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
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
