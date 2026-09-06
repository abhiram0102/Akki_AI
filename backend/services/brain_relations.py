"""An observation log of what the brain has seen said about what.

Every relation the extractor finds is recorded here as (subject, relation,
object) with a count, alongside the graph rather than inside it. The graph
keeps its `CO_OCCURS` edges exactly as they are.

Why alongside, and not as an edge property
-------------------------------------------
This exists to answer a question that cannot be answered yet. Typing edges by
verb was tried and changed nothing -- but that was over 1,324 triples yielding
380 distinct verbs, roughly three examples each, which is far too sparse to
induce relation types from. The methods that do induce them work at millions.
The crawler reads about 1,200 pages an hour, so the only thing standing between
here and a usable corpus is time, and time only counts if the observations are
being kept.

So this is deliberately a LOG, not a schema change:

  * The live 55,000-concept graph is not touched, and needs no migration.
  * `backend/models.py` is not touched either -- it carries another agent's
    uncommitted work, so the table is created with plain SQL from here instead
    of being declared as a model. That is unusual and is the reason why.
  * Aggregating raw observations later is easy; recovering observations that
    were never written down is impossible.

Nothing here interprets a verb. `produce` and `destroy` are recorded as they
were found, with no list saying what either means -- what relations exist is
meant to be induced from enough of these, which is the whole point of keeping
them.
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("akki.brain_relations")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_relations (
    subject   TEXT NOT NULL,
    relation  TEXT NOT NULL,
    object    TEXT NOT NULL,
    count     INTEGER NOT NULL DEFAULT 1,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (subject, relation, object)
)
"""

# Finding every relation a concept takes part in, and every subject/object a
# verb takes, are the two queries relation induction needs. Without these it
# scans the whole table for each one.
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS brain_relations_subject ON brain_relations (subject)",
    "CREATE INDEX IF NOT EXISTS brain_relations_relation ON brain_relations (relation)",
    "CREATE INDEX IF NOT EXISTS brain_relations_object ON brain_relations (object)",
)

_UPSERT = """
INSERT INTO brain_relations (subject, relation, object, count)
VALUES (:subject, :relation, :object, :count)
ON CONFLICT (subject, relation, object) DO UPDATE
SET count = brain_relations.count + EXCLUDED.count,
    last_seen = now()
"""


async def ensure_schema(session) -> None:
    """Create the log if it is not there. Safe to call on every crawler start."""
    await session.execute(text(_SCHEMA))
    for statement in _INDEXES:
        await session.execute(text(statement))
    await session.commit()


async def record(session, triples) -> int:
    """Write one page's observations. Returns how many distinct ones were kept.

    Repeats within a page are folded into a count first, so a term repeated
    forty times on one page arrives as one observation seen forty times rather
    than forty separate writes.

    Recording an observation must never be able to break a read that already
    succeeded -- the page was fetched and the graph was updated, and losing
    this log is not worth losing that.
    """
    counts: dict[tuple[str, str, str], int] = {}
    for subject, relation, obj in triples:
        if not (subject and relation and obj):
            continue
        counts[(subject, relation, obj)] = counts.get((subject, relation, obj), 0) + 1
    if not counts:
        return 0

    try:
        for (subject, relation, obj), count in counts.items():
            await session.execute(text(_UPSERT), {
                "subject": subject, "relation": relation,
                "object": obj, "count": count,
            })
        return len(counts)
    except Exception as exc:
        logger.warning("Could not record relations: %s", exc)
        return 0
