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
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import AsyncSessionLocal
from backend.models import BrainFrontier, BrainVisitedPage, BrainDeadLetter, BrainStats
from backend.services.neo4j_service import get_driver, ensure_schema
from backend.services.brain_fetchers import (
    RobotsChecker, RateLimiter, fetch_wikipedia, fetch_arxiv,
    fetch_generic_article, fetch_rss_news,
)
from backend.services.brain_nlp import extract_dependencies
from backend.services.brain_stats_math import log_likelihood_ratio

logger = logging.getLogger("akki.brain_crawler")

SEEDS = [
    ("https://en.wikipedia.org/wiki/Fire", "fire", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Energy", "energy", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Evolution", "evolution", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Consciousness", "consciousness", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Mathematics", "mathematics", "wikipedia"),
]
NEWS_FEED_URL = os.environ.get("BRAIN_NEWS_FEED_URL", "https://feeds.bbci.co.uk/news/rss.xml")

MAX_ATTEMPTS = 3
PRUNE_EVERY_N_PAGES = 200
BATCH_SIZE = 20

# Map source_type -> fetcher *name*, resolved dynamically via globals() at
# call time (rather than capturing function objects directly at import time)
# so that tests can patch module-level names (e.g. patch.object(brain_crawler,
# "fetch_wikipedia", ...)) and have crawl_one_page actually pick up the mock.
_FETCHER_NAMES = {"wikipedia": "fetch_wikipedia", "arxiv": "fetch_arxiv", "news": "fetch_generic_article"}
_running = True


def _signal_handler(sig, frame):
    global _running
    logger.info("Signal %s received — finishing current page, then stopping.", sig)
    _running = False


async def crawl_one_page(entry: dict, client, robots: RobotsChecker, limiter: RateLimiter,
                          neo4j_driver, pg_session) -> bool:
    """Fetch, extract, and persist one frontier entry. Returns True on success."""
    url, concept, source_type = entry["url"], entry["concept"], entry["source_type"]

    if not await robots.allowed(url, client):
        logger.info("Skipping (robots.txt disallows): %s", url)
        return False

    await limiter.wait(url)

    fetcher_name = _FETCHER_NAMES.get(source_type, "fetch_generic_article")
    fetcher = globals()[fetcher_name]
    try:
        text, links = await fetcher(url, client)
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        return False

    # Minimum 3 words: the grammatical floor for extract_dependencies to find
    # a subject-verb-object triple (e.g. "Fire causes heat" == 3 words).
    sentences = [s for s in text.split(". ") if len(s.split()) >= 3]
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
        updated_freq: dict[str, int] = {}
        updated_total = 0

        if word_freq:
            # Upsert word frequencies AND the running global total-occurrence
            # counter in one call, returning post-update values so G2 can be
            # computed below without a second full read.
            result = await session.run(
                "UNWIND $words AS w "
                "MERGE (c:Concept {word: w.word}) "
                "ON CREATE SET c.frequency = w.count, c.first_seen = datetime() "
                "ON MATCH SET c.frequency = c.frequency + w.count "
                "WITH c, w "
                "MERGE (m:Meta {id: 'singleton'}) "
                "ON CREATE SET m.totalWordOccurrences = w.count "
                "ON MATCH SET m.totalWordOccurrences = m.totalWordOccurrences + w.count "
                "RETURN c.word AS word, c.frequency AS frequency, m.totalWordOccurrences AS total",
                words=[{"word": w, "count": c} for w, c in word_freq.items()],
            )
            async for record in result:
                updated_freq[record["word"]] = record["frequency"]
                updated_total = record["total"]  # same value every row — last write wins, all consistent

        if edge_counts:
            # Upsert edge counts, returning the post-update count per edge.
            result = await session.run(
                "UNWIND $edges AS e "
                "MATCH (a:Concept {word: e.cause}) "
                "MATCH (b:Concept {word: e.effect}) "
                "MERGE (a)-[r:CO_OCCURS]->(b) "
                "ON CREATE SET r.count = e.count, r.last_updated = datetime() "
                "ON MATCH SET r.count = r.count + e.count, r.last_updated = datetime() "
                "RETURN e.cause AS cause, e.effect AS effect, r.count AS count",
                edges=[{"cause": c, "effect": eff, "count": n} for (c, eff), n in edge_counts.items()],
            )
            updated_counts: dict[tuple[str, str], int] = {}
            async for record in result:
                updated_counts[(record["cause"], record["effect"])] = record["count"]

            # Recompute G2 for every edge touched this page, using the
            # post-update frequencies/total from above, then write it back —
            # a third small batched call, not one per edge.
            g2_updates = []
            for (cause, effect), count in updated_counts.items():
                freq_a = updated_freq.get(cause, count)
                freq_b = updated_freq.get(effect, count)
                if updated_total > 0:
                    g2 = log_likelihood_ratio(count, freq_a, freq_b, updated_total)
                    g2_updates.append({"cause": cause, "effect": effect, "g2": g2})

            if g2_updates:
                await session.run(
                    "UNWIND $updates AS u "
                    "MATCH (a:Concept {word: u.cause})-[r:CO_OCCURS]->(b:Concept {word: u.effect}) "
                    "SET r.g2 = u.g2",
                    updates=g2_updates,
                )

    await pg_session.execute(
        pg_insert(BrainVisitedPage).values(
            url=url, concept=concept, source_type=source_type,
            sentences_learned=len(sentences),
        ).on_conflict_do_nothing()
    )
    await pg_session.execute(delete(BrainFrontier).where(BrainFrontier.url == url))

    new_links = [
        {"url": link, "concept": link.rsplit("/", 1)[-1].replace("_", " "), "source_type": source_type}
        for link in links
    ]
    if new_links:
        await pg_session.execute(
            pg_insert(BrainFrontier).values(new_links).on_conflict_do_nothing()
        )

    await pg_session.commit()
    return True


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
    logger.info("Pruning complete: dropped low-count and long-tail edges.")


async def main() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    neo4j_driver = get_driver()
    await ensure_schema()

    robots = RobotsChecker()
    limiter = RateLimiter(min_interval_seconds=1.0)
    pages_since_prune = 0

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        async with AsyncSessionLocal() as pg_session:
            # Seed the frontier if empty
            result = await pg_session.execute(select(BrainFrontier).limit(1))
            if result.scalar_one_or_none() is None:
                for url, concept, source_type in SEEDS:
                    await pg_session.execute(
                        pg_insert(BrainFrontier).values(
                            url=url, concept=concept, source_type=source_type,
                        ).on_conflict_do_nothing()
                    )
                try:
                    news_items = await fetch_rss_news(NEWS_FEED_URL, client)
                    for url, title in news_items[:20]:
                        await pg_session.execute(
                            pg_insert(BrainFrontier).values(
                                url=url, concept=title[:200], source_type="news",
                            ).on_conflict_do_nothing()
                        )
                except Exception as e:
                    logger.warning("Initial RSS seed failed (non-fatal): %s", e)
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
                        ok = await crawl_one_page(entry_dict, client, robots, limiter, neo4j_driver, pg_session)
                    except Exception as e:
                        logger.error("Unhandled error crawling %s: %s", entry.url, e, exc_info=True)
                        ok = False

                    if ok:
                        stats_result = await pg_session.execute(select(BrainStats).where(BrainStats.id == "singleton"))
                        stats = stats_result.scalar_one_or_none()
                        if stats is None:
                            stats = BrainStats(id="singleton", total_pages=0, total_sentences=0)
                            pg_session.add(stats)
                        stats.total_pages += 1
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
