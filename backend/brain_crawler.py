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
from sqlalchemy import select, delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import AsyncSessionLocal
from backend.models import BrainFrontier, BrainVisitedPage, BrainDeadLetter, BrainStats
from backend.services import brain_learn
from backend.services import brain_curiosity
from backend.services import brain_meaning
from backend.services import brain_relations
from backend.services.neo4j_service import get_driver, ensure_schema
from backend.services.brain_fetchers import (
    RobotsChecker, RateLimiter, fetch_structure,
)
from backend.services.brain_nlp import extract_relations

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


def _read_adaptively(sentences: list[str], extract) -> tuple[list, int, dict]:
    """Parse blocks of sentences while the page is still producing relations.

    Returns the pairs found, how many sentences were actually read so the
    caller can record what the page cost as well as what it gave, and the
    SENTENCE each concept was found in.

    That third value is what the meaning layer clusters into word senses, and
    the crawler was not collecting it -- `record_contexts` was reachable only
    from the learn-on-demand path, so sense discovery saw a handful of
    `/ask` misses and none of the 40,000 pages the crawler had read. It is
    gathered here rather than by re-walking the sentences afterwards, because
    parsing is the bottleneck and the mapping is free at this point.
    """
    pairs: list = []
    contexts: dict[str, list[str]] = {}
    best = 0.0
    read = 0
    for start in range(0, min(len(sentences), _MAX_READ), _BLOCK):
        block = sentences[start:start + _BLOCK]
        if not block:
            break
        found = []
        for sentence in block:
            try:
                extracted = extract(sentence)
            except Exception:
                continue
            found.extend(extracted)
            for subject, _verb, obj in extracted:
                contexts.setdefault(subject, []).append(sentence)
                contexts.setdefault(obj, []).append(sentence)
        pairs.extend(found)
        read += len(block)

        yield_rate = len(found) / len(block)
        best = max(best, yield_rate)
        if read >= _MIN_READ and yield_rate < best * _YIELD_SHARE:
            break
    return pairs, read, contexts


def _record_page_contexts(contexts: dict) -> None:
    """Hand each concept's sentences to the sense store.

    Wrapped per concept for the same reason `brain_learn` wraps it: recording
    meaning must never be able to break a page that was read successfully.
    """
    for concept, sentences in contexts.items():
        try:
            brain_meaning.record_contexts(concept, sentences)
        except Exception as exc:
            logger.debug("Could not record contexts for %r: %s", concept, exc)


# What a page discovered while READING a curiosity entry was reached by. Not
# the curiosity marker: that says why the brain wanted the page it was just on,
# and it does not transfer to everything that page happens to link to.
_DISCOVERED = "discovered"


def discovered_source_type(source_type: str) -> str:
    """The source_type to stamp on links found while reading `source_type`.

    Links inherit the page's source_type, which was harmless while every page
    was `wikipedia`. Once a page carried `curiosity:derived`, reading it minted
    96 more `curiosity:derived` frontier entries, each of which would mint its
    own -- an exponential priority lane that would swallow the crawl, and a
    feedback signal measuring pages curiosity never asked for.

    The marker is stripped rather than the whole source_type replaced, so
    ordinary provenance still travels to a page's links untouched.
    """
    if source_type.startswith(f"{brain_curiosity.SOURCE_TYPE}:"):
        return _DISCOVERED
    return source_type


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
    # The verb is kept alongside the pair: the graph is unchanged, and the
    # observation log gains what the graph throws away. One parse either way --
    # parsing is the bottleneck, so nothing is read twice.
    triples, sentences_read, contexts = _read_adaptively(sentences, extract_relations)
    _record_page_contexts(contexts)
    pairs = [(subject, obj) for subject, _, obj in triples]

    word_freq: Counter = Counter()
    edge_counts: Counter = Counter()
    for cause, effect in pairs:
        word_freq[cause] += 1
        word_freq[effect] += 1
        edge_counts[(cause, effect)] += 1

    async with neo4j_driver.session() as session:
        await brain_learn.apply_to_graph(session, word_freq, edge_counts)

    await brain_relations.record(pg_session, triples)

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
    link_source_type = discovered_source_type(source_type)
    new_links = [
        {"url": link, "concept": concept, "source_type": link_source_type}
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


# How long a thin edge, or a concept resting only on thin edges, is left alone
# before the pruner may sweep it.
#
# The pruner used to delete every count-1 edge on sight, then delete whatever
# concept that orphaned. A concept read on ONE page has most of its edges at
# count 1, so a single read of something new mostly evaporated within ten
# minutes. Measured on the live graph: one prune would have taken 7,751 edges
# and 6,461 concepts -- 12% of the graph -- including 12 of the 27 edges
# `quasicrystal` had just been read to obtain, having already lost that concept
# the same way once before.
#
# That is the bottom of the bucket the curiosity loop pours into: curiosity
# reads what the brain does not know, and what it does not know it has by
# definition seen once.
#
# 24 hours is roughly 29,000 pages at the current rate -- a real chance to meet
# a concept again -- but it is a reasoned default, NOT calibrated against how
# long edges actually take to reach count 2. That measurement needs history the
# old pruner was deleting. Flagged in the log alongside the curiosity
# thresholds, which are uncalibrated for the same reason.
PROBATION_HOURS = 24


def thin_edge_prune_cypher() -> str:
    """Sweep edges that stayed thin, once they have had a fair chance not to.

    Still `count < 2`, so the dust the pruner exists to control is still
    controlled -- its comment records 83% of the graph going edgeless without
    it. The addition is that an edge written moments ago is not yet evidence of
    anything, and deleting it measures nothing except how recently the crawler
    ran.
    """
    return (
        "MATCH (:Concept)-[r:CO_OCCURS]->() "
        "WHERE r.count < 2 AND r.last_updated IS NOT NULL "
        f"AND r.last_updated < datetime() - duration({{hours: {PROBATION_HOURS}}}) "
        "DELETE r"
    )


def orphan_prune_cypher() -> str:
    """Delete concepts left with no edges -- unless they are still new.

    Orphan deletion is what actually loses the concept, so it needs the same
    probation. Without it a concept survives edge-pruning only to be swept by
    the very next statement, and the protection above buys nothing.
    """
    return (
        "MATCH (c:Concept) WHERE NOT (c)-[:CO_OCCURS]-() "
        "AND (c.first_seen IS NULL OR "
        f"c.first_seen < datetime() - duration({{hours: {PROBATION_HOURS}}})) "
        "DELETE c"
    )


async def _prune_low_value_edges(neo4j_driver) -> None:
    """Never raises: losing a prune costs disk, losing the crawl costs reading."""
    try:
        async with neo4j_driver.session() as session:
            await session.run(thin_edge_prune_cypher())
            await session.run(
                "MATCH (a:Concept)-[r:CO_OCCURS]->() "
                "WITH a, r ORDER BY r.count DESC "
                "WITH a, collect(r) AS rels "
                "UNWIND rels[50..] AS excess "
                "DELETE excess"
            )
            await session.run(orphan_prune_cypher())
    except Exception as exc:
        logger.warning("Pruning failed, crawl continues: %s", exc)
        return
    logger.info("Pruning complete: swept edges and concepts past probation.")


# The one LIKE pattern behind both the prioritised frontier query and the
# partial index that makes it cheap. A partial index is only usable when its
# predicate implies the query's, so these two must never drift apart -- hence
# one constant rather than the same string written twice.
_CURIOSITY_PATTERN = f"{brain_curiosity.SOURCE_TYPE}:%"


async def ensure_frontier_index(pg_session) -> None:
    """Make the curiosity-first lookup cheap, or carry on without it.

    Without an index the prioritised query is a parallel sequential scan:
    measured at 1,398 ms over 466,850 frontier rows, discarding all of them,
    once per twenty-page batch. The frontier grows faster than it drains, so
    that cost grows with it.

    A PARTIAL index solves it for almost nothing. It indexes only rows
    curiosity queued -- a handful at a time, capped per answer -- so it stays
    kilobytes no matter how large the frontier gets, and it does not slow down
    the bulk inserts of discovered links, which do not match the predicate.

    Created here in plain SQL rather than declared on the model. `models.py`
    carries another agent's uncommitted work, so committing a declared index
    would mean committing their unfinished changes alongside it. Session 7 and
    session 22 both took this route for the same reason.

    Never raises. An index is an optimisation; a database that refuses it
    should cost the crawler speed, not its ability to read.
    """
    try:
        await pg_session.execute(text(
            "CREATE INDEX IF NOT EXISTS brain_frontier_curiosity_idx "
            "ON brain_frontier (source_type) "
            f"WHERE source_type LIKE '{_CURIOSITY_PATTERN}'"
        ))
        await pg_session.commit()
    except Exception as exc:
        logger.warning(
            "Could not create the curiosity frontier index; the prioritised "
            "query will sequential-scan: %s", exc)


async def select_frontier_batch(pg_session, limit: int = BATCH_SIZE):
    """The next entries to read, curiosity first.

    The frontier used to be read with a bare `select(BrainFrontier).limit(n)`.
    With no ORDER BY, Postgres returns heap order, which is effectively
    insertion order -- so an entry queued now waits behind everything already
    discovered. That is 466,850 URLs against a read rate near 1,200 an hour,
    and the frontier grows faster than it drains. Anything the brain became
    curious about today would be reached in about two weeks at best.

    Curiosity is worth nothing on that schedule. Its whole claim is that the
    brain goes and reads what an answer just revealed it does not know, so it
    has to preempt the bulk crawl rather than join the back of it.

    Two queries rather than one ORDER BY. The bulk query stays exactly as it
    was -- unordered, so no sort over a half-million rows every twenty pages --
    and the prioritised query is a narrow lookup over the handful of entries
    curiosity has queued. Ordering the whole table instead would make every
    batch pay a full sort to move at most three rows.

    Curiosity cannot starve the ordinary crawl: `brain_curiosity` caps what any
    one answer may queue, so the prioritised query empties and the fallback
    runs. The fallback is skipped only when curiosity genuinely filled a batch.
    """
    result = await pg_session.execute(
        select(BrainFrontier)
        .where(BrainFrontier.source_type.like(_CURIOSITY_PATTERN))
        .limit(limit)
    )
    batch = list(result.scalars().all())
    if len(batch) >= limit:
        return batch

    result = await pg_session.execute(
        select(BrainFrontier).limit(limit - len(batch))
    )
    return batch + list(result.scalars().all())


async def main() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    neo4j_driver = get_driver()
    await ensure_schema()
    async with AsyncSessionLocal() as schema_session:
        await brain_relations.ensure_schema(schema_session)

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
            await ensure_frontier_index(pg_session)

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
                batch = await select_frontier_batch(pg_session, BATCH_SIZE)

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
