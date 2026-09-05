"""Self-directed curiosity — Function 8 (Continuous Self-Improvement), fed by
the gaps Function 7 detects while answering.

AKKI_FULL_ARCHITECTURE.md describes the loop as:

    Question -> Answer -> Gap -> Read -> Better Answer -> Better Gap Detection

Everything except the third arrow already existed. `/ask` detected gaps and
then dropped them on the floor, so the brain could say "my picture of this is
thin" and never do anything about it. This module closes the loop: it turns
what an answer was least sure about into entries on the crawl frontier the
background crawler already drains, so the next time the same question is asked
the answer is genuinely better.

Two properties worth stating plainly:

**The answer itself still touches no network.** Selection (`select_gaps`) is
pure: it reads only the answer that was already composed from the graph.
Queueing runs after the response has been streamed, so the project's "zero
live internet at answer time" constraint holds.

**Nothing is fabricated into the queue.** Only concepts the answer actually
named are queued, ranked by how weakly the graph supports them.
"""
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import AsyncSessionLocal
from backend.models import BrainFrontier, BrainDeadLetter, BrainVisitedPage

logger = logging.getLogger(__name__)

# Marks frontier rows the brain queued for itself, so curiosity-driven reading
# is distinguishable from seeded and link-discovered crawling in the data.
SOURCE_TYPE = "curiosity"

# An edge seen this few times is a guess worth checking rather than knowledge.
_WEAK_COUNT = 3

# Cap per answer. Curiosity should trickle, not flood the frontier and starve
# the crawler of everything else — the seed comment in brain_crawler notes that
# a flood already drowned the knowledge sources once.
_MAX_PER_ANSWER = 3


def select_gaps(answer: dict, limit: int = _MAX_PER_ANSWER) -> list[str]:
    """Choose what the brain should go and read, most valuable first.

    Priority reflects what the answer was least able to stand behind:

    1. The concept asked about, when the graph had nothing solid on it.
    2. Derived links. These are the brain's own 2-hop inferences that no source
       stated, so they are precisely the claims it has reason to verify by
       reading. Queueing these is what makes the loop self-correcting rather
       than self-confirming.
    3. Concepts named in the answer resting on very few observations.

    Pure and synchronous: takes the already-composed answer, touches nothing.
    """
    picks: list[str] = []

    def add(concept):
        if concept and concept not in picks:
            picks.append(concept)

    topics = answer.get("topics") or []
    primary = topics[0] if topics else None

    if answer.get("confidence") in ("none", "thin") and primary:
        add(primary)

    for item in answer.get("derived") or []:
        add(item.get("concept"))

    for item in (answer.get("dependsOn") or []) + (answer.get("produces") or []):
        if (item.get("count") or 0) < _WEAK_COUNT:
            add(item.get("word"))

    return picks[:limit]


async def queue_reading(concepts: list[str], client, resolver) -> int:
    """Resolve each concept to a source URL and add it to the crawl frontier.

    `resolver` is injected rather than imported so the source of knowledge is a
    caller's choice and this module stays free of any one site's conventions.
    It is handed a term and returns an address, or None.

    This used to build the address itself by joining a resolved title onto a
    fixed prefix — a hardcoded URL convention. The resolver now returns a real
    address it found by reading, so no address is constructed here at all.

    Returns how many rows were newly queued. Never raises: curiosity failing is
    not a reason for a request to fail, since the answer has already been sent.
    """
    if not concepts:
        return 0

    queued = 0
    try:
        async with AsyncSessionLocal() as session:
            for concept in concepts:
                try:
                    url = await resolver(concept, client)
                except Exception:
                    continue
                if not url:
                    continue

                # Don't re-queue somewhere already read, or a URL that has
                # already failed enough times to be dead-lettered.
                if await session.get(BrainVisitedPage, url) is not None:
                    continue
                if await session.get(BrainDeadLetter, url) is not None:
                    continue

                result = await session.execute(
                    pg_insert(BrainFrontier)
                    .values(url=url, concept=concept, source_type=SOURCE_TYPE)
                    .on_conflict_do_nothing()
                )
                queued += result.rowcount or 0
            await session.commit()
    except Exception as exc:
        logger.warning("Curiosity queueing failed, answer unaffected: %s", exc)
        return queued
    if queued:
        logger.info("Curiosity queued %d concept(s) to read: %s", queued, concepts)
    return queued
