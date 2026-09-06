"""Did the brain turn out to be right about the things nobody told it?

`brain_service.infer_links` produces 2-hop links no source ever stated --
"photosynthesis leads to nucleus, reached through electron". The answer says
so out loud: *"one I worked out myself. Nothing I read said that directly."*

Those are not facts. They are **claims**, and they are testable: go and read
about the concept, then look at whether the graph gained a DIRECT edge for what
had only ever been inferred.

Session 3 already had the instinct -- it queues derived links for reading and
called that making the loop "self-correcting rather than self-confirming". But
the loop then scored the outcome by how many SENTENCES the page returned. A
page yielding 300 sentences about something unrelated counted as a success, so
the brain could repeat the same wrong inference indefinitely while its own
scoreboard applauded. It measured whether it had READ, never whether it had
been RIGHT.

Absence of evidence is not evidence of absence
----------------------------------------------
This is where the design would most easily lie, so it is worth being explicit.

The tempting vocabulary has two outcomes -- confirmed and refuted -- and the
second one is not earned. A source can be silent about a true thing for many
reasons: the extractor missed it (precision on real crawled text is measured at
0.50, so this is common, not hypothetical), the page covered a different
aspect, or the relation is stated on a page this one merely links to.

So a claim that reading did not bear out is **unsupported**, never *refuted*.
`VERDICTS` deliberately contains no word meaning "false", and a test asserts
that it never gains one. Manufacturing negative knowledge out of silence would
be worse than keeping none, because the loop acts on what it records.

Turning `unsupported` into genuine refutation needs a model of where a fact
WOULD be stated if it were true. That is a real open problem and is not
attempted here.

Kept as a log beside the graph, in plain SQL, for the reason sessions 7, 22 and
24 all record: `backend/models.py` carries another agent's uncommitted work,
and committing a declared model would mean committing their unfinished changes
alongside it.
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("akki.brain_hypothesis")

CONFIRMED = "confirmed"      # reading produced a direct edge for the inference
UNSUPPORTED = "unsupported"  # reading did not -- which is NOT the same as false
PENDING = "pending"          # not yet tested, so not yet anything

VERDICTS = (CONFIRMED, UNSUPPORTED, PENDING)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_hypotheses (
    subject   TEXT NOT NULL,
    object    TEXT NOT NULL,
    via       TEXT,
    verdict   TEXT NOT NULL DEFAULT 'pending',
    claimed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    adjudicated_at TIMESTAMPTZ,
    PRIMARY KEY (subject, object)
)
"""

# Adjudication looks up every pending claim ABOUT a concept the crawler has
# just read, so that is the access path that has to be cheap.
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS brain_hypotheses_pending_object "
    "ON brain_hypotheses (object) WHERE verdict = 'pending'",
)

# A claim already judged is not re-opened by being inferred again: the first
# reading that tested it is the evidence, and letting a later re-derivation
# reset it to pending would erase outcomes rather than accumulate them.
_INSERT = """
INSERT INTO brain_hypotheses (subject, object, via, verdict)
VALUES (:subject, :object, :via, :verdict)
ON CONFLICT (subject, object) DO NOTHING
"""

_PENDING_FOR_OBJECT = """
SELECT subject, object FROM brain_hypotheses
WHERE object = :object AND verdict = 'pending'
"""

_SET_VERDICT = """
UPDATE brain_hypotheses SET verdict = :verdict, adjudicated_at = now()
WHERE subject = :subject AND object = :object
"""

_TALLY = "SELECT verdict, count(*) FROM brain_hypotheses GROUP BY verdict"

# The claim was that these two are connected. The test is whether any source,
# once read, says so DIRECTLY -- the inference travelled two hops, so a direct
# edge is exactly the thing that was not there when the claim was made.
_DIRECT_EDGE = """
MATCH (a:Concept {word: $subject})-[r:CO_OCCURS]-(b:Concept {word: $object})
RETURN count(r) AS found
"""


def claims_from_answer(answer: dict) -> list[dict]:
    """The claims an answer actually made, in the words it made them.

    Only `derived` links. Those are the 2-hop inferences the answer itself
    labels as "one I worked out myself -- nothing I read said that directly",
    so they are exactly the statements standing on the brain's own reasoning
    rather than on a source.

    Direct associations are excluded on purpose: an edge the brain read
    somewhere is already evidence, and grading it would pad the confirmation
    rate with things that were never in doubt.

    Taken from the composed answer rather than re-derived later, so the claim
    on the scoreboard is the claim the user was told.
    """
    topics = answer.get("topics") or []
    if not topics:
        return []
    subject = topics[0]
    return [
        {"subject": subject,
         "object": item.get("concept"),
         "via": item.get("via")}
        for item in (answer.get("derived") or [])
        if item.get("concept")
    ]


async def ensure_schema(session) -> None:
    """Create the log if absent. Safe on every start."""
    await session.execute(text(_SCHEMA))
    for statement in _INDEXES:
        await session.execute(text(statement))
    await session.commit()


async def record(session, claims) -> int:
    """Write down what the brain inferred, before it goes to check.

    Recording BEFORE reading is what makes this a test rather than a story told
    afterwards: the claim is fixed in advance, so it cannot be quietly adjusted
    to match whatever the page turned out to say.

    Never raises. This is bookkeeping attached to a request that has already
    been answered.
    """
    written = 0
    try:
        for claim in claims:
            subject = (claim.get("subject") or "").strip()
            obj = (claim.get("object") or "").strip()
            if not subject or not obj or subject == obj:
                continue
            await session.execute(text(_INSERT), {
                "subject": subject,
                "object": obj,
                "via": claim.get("via"),
                "verdict": PENDING,
            })
            written += 1
        await session.commit()
    except Exception as exc:
        logger.warning("Could not record hypotheses: %s", exc)
        return 0
    return written


async def adjudicate(pg_session, neo4j_session, concept: str) -> dict:
    """Judge the claims about `concept`, now that it has actually been read.

    Only claims about what was just read are judged. Judging the rest would
    score them on a silence the reading never addressed.

    A claim the reading bore out is `CONFIRMED`. One it did not is
    `UNSUPPORTED` -- **absence of evidence is not evidence of absence**, so
    that verdict says the brain has not established the link, never that the
    link is false. See this module's docstring for why that distinction is
    load-bearing rather than pedantic.

    Never raises: a crawl must not fail because bookkeeping did.
    """
    tally = {CONFIRMED: 0, UNSUPPORTED: 0}
    try:
        result = await pg_session.execute(
            text(_PENDING_FOR_OBJECT), {"object": concept})
        pending = result.fetchall()

        for subject, obj in pending:
            found = await neo4j_session.run(
                _DIRECT_EDGE, subject=subject, object=obj)
            record_ = await found.single()
            verdict = CONFIRMED if (record_ and record_["found"]) else UNSUPPORTED
            await pg_session.execute(text(_SET_VERDICT), {
                "verdict": verdict, "subject": subject, "object": obj})
            tally[verdict] += 1

        await pg_session.commit()
    except Exception as exc:
        logger.warning("Could not adjudicate hypotheses for %r: %s", concept, exc)
        return {}
    if any(tally.values()):
        logger.info("Adjudicated %r: %d confirmed, %d unsupported",
                    concept, tally[CONFIRMED], tally[UNSUPPORTED])
    return tally


async def scoreboard(session) -> dict:
    """How often the brain was right about something no source had told it.

    `confirmationRate` counts only claims that have actually been tested.
    Pending ones are excluded deliberately: a claim not yet checked is not a
    claim that failed, and counting it as one would make the rate collapse
    every time curiosity queued anything.

    With nothing judged the rate is `None`, not 0.0 -- "nothing has been tested"
    and "the brain is always wrong" are different statements and should not
    render as the same number.
    """
    try:
        result = await session.execute(text(_TALLY))
        counts = {verdict: int(n) for verdict, n in result.fetchall()}
    except Exception as exc:
        logger.warning("Could not read the hypothesis scoreboard: %s", exc)
        return {}

    confirmed = counts.get(CONFIRMED, 0)
    unsupported = counts.get(UNSUPPORTED, 0)
    judged = confirmed + unsupported
    return {
        "confirmed": confirmed,
        "unsupported": unsupported,
        "pending": counts.get(PENDING, 0),
        "judged": judged,
        "confirmationRate": (confirmed / judged) if judged else None,
    }
