"""Why does AKKI believe this?

The roadmap's fifth pillar: every belief should answer that question with an
evidence chain, not "the model gave it a high probability". You cannot revise a
belief you cannot trace, and you cannot trust a reasoning step whose grounds you
cannot see -- so provenance sits under both self-correction and reasoning.

The evidence already exists, scattered across three stores this only reads:

  * The Neo4j graph -- the edge's strength (how many times the pair co-occurred)
    and g2 (how surprising that co-occurrence is against chance).
  * brain_relations -- the verbs actually observed between the two, with counts.
    This is the "what was actually said" layer: `fire produce heat`, seen 4
    times, is direct testimony, not an inference.
  * brain_hypotheses -- whether this link was ever the brain's OWN 2-hop
    inference rather than something read, and how it fared when checked.

`explain` assembles them into one answer and narrates it without overclaiming:
a link the reading never bore out is reported as inferred-and-unsupported, never
as fact. Nothing here writes; a trace that mutated state would corrupt the very
belief it claims to explain.

No hardcoded relation ontology. The verbs reported are whatever was observed --
`produce`, `destroy`, `require` -- with no table saying what any of them means.
That induction is a separate, data-gated step (see the architecture log); this
layer just surfaces the raw testimony behind a belief.
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("akki.brain_provenance")

# What a belief rests on, strongest first.
OBSERVED = "observed"   # a source, once read, stated it directly
INFERRED = "inferred"   # the brain's own 2-hop reasoning, no source said it
NONE = "none"           # nothing on record either way

# Both verbs are surfaced regardless of direction, because provenance answers
# "why do you connect these two", which is symmetric even though the stored
# edge is directed.
_OBSERVATIONS = """
SELECT subject, relation, object, count FROM brain_relations
WHERE (subject = :a AND object = :b) OR (subject = :b AND object = :a)
ORDER BY count DESC
"""

_INFERENCE = """
SELECT via, verdict FROM brain_hypotheses
WHERE (subject = :a AND object = :b) OR (subject = :b AND object = :a)
LIMIT 1
"""

# Read-only edge lookup: strength is the co-occurrence count, g2 the surprise.
_EDGE = """
MATCH (x:Concept {word: $a})-[r:CO_OCCURS]-(y:Concept {word: $b})
RETURN r.count AS strength, r.g2 AS g2
ORDER BY r.count DESC LIMIT 1
"""


async def explain(pg_session, neo4j_session, subject: str, obj: str) -> dict:
    """Assemble the evidence chain behind a belief that `subject` relates to `obj`.

    Returns `basis` (OBSERVED / INFERRED / NONE), the raw `observations` (verbs
    seen, with counts), the graph `edge` if one exists, any `inference` on
    record, and a plain-language `why` that states the grounds without claiming
    more than they support.

    Never raises: an unexplainable belief should report NONE, not break the
    caller asking about it.
    """
    observations: list[dict] = []
    edge: dict | None = None
    inference: dict | None = None

    try:
        rows = (await pg_session.execute(
            text(_OBSERVATIONS), {"a": subject, "b": obj})).fetchall()
        for _s, relation, _o, count in rows:
            observations.append({"relation": relation, "count": int(count)})
    except Exception as exc:
        logger.warning("Could not read observations for %r/%r: %s",
                       subject, obj, exc)

    try:
        record = await (await neo4j_session.run(
            _EDGE, a=subject, b=obj)).single()
        if record and record.get("strength") is not None:
            edge = {"strength": record["strength"], "g2": record.get("g2")}
    except Exception as exc:
        logger.debug("Could not read edge for %r/%r: %s", subject, obj, exc)

    # Only look for an inference when there is no direct testimony -- a link the
    # brain both read AND inferred is grounded by the reading, and reporting the
    # inference alongside would understate how well it is supported.
    if not observations:
        try:
            row = (await pg_session.execute(
                text(_INFERENCE), {"a": subject, "b": obj})).fetchall()
            if row:
                via, verdict = row[0]
                inference = {"via": via, "verdict": verdict}
        except Exception as exc:
            logger.debug("Could not read inference for %r/%r: %s",
                         subject, obj, exc)

    if observations:
        basis = OBSERVED
    elif inference:
        basis = INFERRED
    else:
        basis = NONE

    return {
        "pair": [subject, obj],
        "basis": basis,
        "observations": observations,
        "edge": edge,
        "inference": inference,
        "why": _why(subject, obj, basis, observations, edge, inference),
    }


def _why(subject, obj, basis, observations, edge, inference) -> str:
    """One honest sentence. Never claims more than the evidence carries."""
    if basis == OBSERVED:
        verbs = ", ".join(f"'{subject} {o['relation']} {obj}'"
                          for o in observations[:3])
        seen = sum(o["count"] for o in observations)
        line = f"Read directly: {verbs} (observed {seen}x)."
        if edge and edge.get("g2") is not None:
            line += f" Co-occurrence surprise g2={edge['g2']}."
        return line
    if basis == INFERRED:
        via = inference.get("via")
        verdict = inference.get("verdict")
        line = (f"No source stated this; I inferred it, reaching {obj} "
                f"through {via}." if via else
                f"No source stated this; I inferred it.")
        if verdict == "unsupported":
            line += " Reading has not yet borne it out."
        elif verdict == "confirmed":
            line += " Later reading bore it out."
        return line
    return f"I have nothing on record connecting {subject} and {obj}."
