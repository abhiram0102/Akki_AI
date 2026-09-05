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

from sqlalchemy import Integer, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import AsyncSessionLocal
from backend.models import BrainFrontier, BrainDeadLetter, BrainVisitedPage

logger = logging.getLogger(__name__)

# Marks frontier rows the brain queued for itself, so curiosity-driven reading
# is distinguishable from seeded and link-discovered crawling in the data. The
# REASON is appended after the colon, and that is what makes the loop
# measurable: the crawler already carries a frontier entry's `source_type`
# through to the visited-page record, so every completed read stays on file
# with the reason the brain wanted it.
SOURCE_TYPE = "curiosity"

# Why a concept was queued. These are the three judgements `select_gaps` makes,
# and keeping them apart is the point: "I knew nothing about this" and "I
# inferred this and want to check it" are different bets, and only measuring
# them separately can show that one pays off while the other does not.
REASON_UNKNOWN = "unknown"    # the graph had nothing solid on the concept
REASON_DERIVED = "derived"    # the brain's own 2-hop inference, worth verifying
REASON_THIN = "thin"          # named in the answer but resting on few observations

# A read that produced at least this many sentences taught the brain something.
# Below it the page was navigation, a stub, or a redirect.
_USEFUL_SENTENCES = 3

# How many completed reads a reason needs before its record is worth acting on.
# Below this the rate is noise, and every reason keeps its turn.
_MIN_SAMPLES = 8

# A reason whose reads pay off less often than this stops being acted on, once
# there is enough evidence to say so.
_MIN_SUCCESS_RATE = 0.25

# An edge seen this few times is a guess worth checking rather than knowledge.
_WEAK_COUNT = 3

# Cap per answer. Curiosity should trickle, not flood the frontier and starve
# the crawler of everything else — the seed comment in brain_crawler notes that
# a flood already drowned the knowledge sources once.
_MAX_PER_ANSWER = 3


def select_gaps(answer: dict, limit: int = _MAX_PER_ANSWER,
                effectiveness: dict | None = None) -> list[tuple[str, str]]:
    """Choose what the brain should go and read, most valuable first.

    Priority reflects what the answer was least able to stand behind:

    1. The concept asked about, when the graph had nothing solid on it.
    2. Derived links. These are the brain's own 2-hop inferences that no source
       stated, so they are precisely the claims it has reason to verify by
       reading. Queueing these is what makes the loop self-correcting rather
       than self-confirming.
    3. Concepts named in the answer resting on very few observations.

    `effectiveness`, from `measure_effectiveness`, is the loop closing on
    itself: a reason whose reads have reliably taught the brain nothing stops
    being acted on. Without it curiosity would keep making the same bet forever
    however it turned out. A reason with too little history is always kept, so a
    new one gets a chance to prove itself rather than being judged on one bad
    read.

    Returns (concept, reason) pairs. Pure and synchronous: it reads the
    already-composed answer and touches nothing.
    """
    picks: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(concept, reason):
        if not concept or concept in seen:
            return
        if not _reason_is_worth_it(reason, effectiveness):
            return
        seen.add(concept)
        picks.append((concept, reason))

    topics = answer.get("topics") or []
    primary = topics[0] if topics else None

    if answer.get("confidence") in ("none", "thin") and primary:
        add(primary, REASON_UNKNOWN)

    for item in answer.get("derived") or []:
        add(item.get("concept"), REASON_DERIVED)

    for item in (answer.get("dependsOn") or []) + (answer.get("produces") or []):
        if (item.get("count") or 0) < _WEAK_COUNT:
            add(item.get("word"), REASON_THIN)

    return picks[:limit]


def _reason_is_worth_it(reason: str, effectiveness: dict | None) -> bool:
    """Whether this kind of bet has earned another turn."""
    if not effectiveness:
        return True
    record = effectiveness.get(reason)
    if not record or record.get("reads", 0) < _MIN_SAMPLES:
        return True
    return record.get("successRate", 1.0) >= _MIN_SUCCESS_RATE


async def measure_effectiveness() -> dict:
    """Did reading what the brain was curious about actually teach it anything?

    Without this the loop is open: gaps are detected, reading is queued, and
    nothing ever checks whether it helped, so the brain would go on making a
    losing bet indefinitely.

    The answer is already in the data. The crawler carries a frontier entry's
    `source_type` through to its visited-page record, so every completed
    curiosity read is on file with the reason it was queued and how many
    sentences it yielded. No new table and no migration: the measurement is a
    read over history the pipeline was already keeping.

    Returns, per reason: how many reads completed, how many taught the brain
    something, the resulting rate, and the average sentences learned. Never
    raises — an unmeasurable loop should fall back to acting on every reason
    rather than stopping.
    """
    out: dict = {}
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    BrainVisitedPage.source_type,
                    func.count().label("reads"),
                    func.sum(
                        func.cast(
                            BrainVisitedPage.sentences_learned >= _USEFUL_SENTENCES,
                            Integer,
                        )
                    ).label("useful"),
                    func.avg(BrainVisitedPage.sentences_learned).label("avg_sentences"),
                )
                .where(BrainVisitedPage.source_type.like(f"{SOURCE_TYPE}:%"))
                .group_by(BrainVisitedPage.source_type)
            )
            for source_type, reads, useful, avg_sentences in result:
                reason = source_type.split(":", 1)[1]
                reads = int(reads or 0)
                useful = int(useful or 0)
                out[reason] = {
                    "reads": reads,
                    "useful": useful,
                    "successRate": (useful / reads) if reads else 0.0,
                    "avgSentences": float(avg_sentences or 0.0),
                }
    except Exception as exc:
        logger.warning("Could not measure curiosity effectiveness: %s", exc)
        return {}
    return out


async def queue_reading(picks: list[tuple[str, str]], client, resolver) -> int:
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
    if not picks:
        return 0

    queued = 0
    try:
        async with AsyncSessionLocal() as session:
            for concept, reason in picks:
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
                    # The reason travels with the entry so the completed read
                    # can be attributed back to the bet that caused it.
                    .values(url=url, concept=concept,
                            source_type=f"{SOURCE_TYPE}:{reason}")
                    .on_conflict_do_nothing()
                )
                queued += result.rowcount or 0
            await session.commit()
    except Exception as exc:
        logger.warning("Curiosity queueing failed, answer unaffected: %s", exc)
        return queued
    if queued:
        logger.info("Curiosity queued %d concept(s) to read: %s", queued, picks)
    return queued
