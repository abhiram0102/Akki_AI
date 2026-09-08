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


# ---------------------------------------------------------------------------
# The substrate: capture what the pipeline was throwing away
# ---------------------------------------------------------------------------
#
# explain() above reads what already existed. But brain_relations kept the verb
# and a count and lost WHERE it was read, the exact SPAN, and HOW it was
# extracted. Without those a belief can never answer where/how/when, so the
# self-correction and reasoning layers built on top would have nothing to trace
# to. This table keeps them, one row per observation.
#
# Predicate-agnostic on purpose: `predicate` is whatever verb the extractor
# found, stored verbatim, with no mapping to CAUSES/IS_A/REQUIRES. Those types
# are what the corpus is meant to INDUCE later; imposing them here would be the
# hardcoded schema the charter forbids, and the substrate would then have to
# change the day induction succeeds. It does not: a claim is (subject,
# predicate, object) and stays that shape whatever the predicates turn out to
# mean.
#
# Plain SQL beside the graph, not a declared model -- models.py carries another
# agent's uncommitted work (sessions 7, 22, 24, 25 all took this route).

_EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_claim_evidence (
    subject     TEXT NOT NULL,
    predicate   TEXT NOT NULL,
    object      TEXT NOT NULL,
    source      TEXT NOT NULL,
    span        TEXT,
    method      TEXT,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (subject, predicate, object, source)
)
"""

_EVIDENCE_INDEXES = (
    # The trace queries every observation of a pair regardless of direction.
    "CREATE INDEX IF NOT EXISTS brain_claim_evidence_pair "
    "ON brain_claim_evidence (subject, object)",
)

_EVIDENCE_UPSERT = """
INSERT INTO brain_claim_evidence (subject, predicate, object, source, span, method)
VALUES (:subject, :predicate, :object, :source, :span, :method)
ON CONFLICT (subject, predicate, object, source) DO UPDATE
SET span = EXCLUDED.span, method = EXCLUDED.method, observed_at = now()
"""

_EVIDENCE_FOR_PAIR = """
SELECT subject, predicate, object, source, span, method, observed_at::text
FROM brain_claim_evidence
WHERE (subject = :a AND object = :b) OR (subject = :b AND object = :a)
ORDER BY observed_at
"""

# Conclusions reasoned THROUGH this concept: a derived claim records its
# intermediate hop in `via`, so anything inferred via X depends on X.
_DEPENDENTS = """
SELECT subject, object FROM brain_hypotheses WHERE via = :concept
"""


async def ensure_evidence_schema(session) -> None:
    """Create the evidence table if absent. Safe on every crawler start."""
    await session.execute(text(_EVIDENCE_SCHEMA))
    for statement in _EVIDENCE_INDEXES:
        await session.execute(text(statement))
    await session.commit()


async def record_evidence(session, evidences) -> int:
    """Store observations with their provenance: source, span, method.

    An observation with no `source` is dropped -- evidence without provenance
    is not evidence, and keeping it would defeat the substrate. `span` and
    `method` may be absent (a source alone is still traceable), but the source
    is the floor.

    Never raises: this rides the hot crawl path, and losing a provenance row is
    never worth losing a page that was read.
    """
    written = 0
    try:
        for e in evidences:
            subject = (e.get("subject") or "").strip()
            predicate = (e.get("predicate") or "").strip()
            obj = (e.get("object") or "").strip()
            source = (e.get("source") or "").strip()
            if not (subject and predicate and obj and source):
                continue
            await session.execute(text(_EVIDENCE_UPSERT), {
                "subject": subject, "predicate": predicate, "object": obj,
                "source": source, "span": e.get("span"), "method": e.get("method"),
            })
            written += 1
        await session.commit()
    except Exception as exc:
        logger.warning("Could not record claim evidence: %s", exc)
        return 0
    return written


async def trace(pg_session, neo4j_session, subject: str, obj: str) -> dict:
    """The full provenance of a belief, answering nine questions and collapsing
    none of them into a single confidence number.

      what          -- the claim: subject / (predicates observed) / object
      why           -- basis: observed / inferred / none
      where         -- the sources it was read from
      how           -- the extraction methods that produced it
      when          -- first and last time it was observed
      supporting    -- every observation, with source and span
      contradicting -- DEFERRED (see below), competing predicates surfaced raw
      derivation    -- premises + method, when the belief is an inference
      dependents    -- conclusions reasoned through this belief

    On `contradicting`: two observations contradict only if their predicates are
    opposites, and detecting opposition needs predicate polarity the project
    cannot yet induce (distributional vectors place antonyms together -- a
    measured failure, see the architecture log). So competing predicates are
    surfaced as data, and `contradicting.status` is "deferred" rather than
    faked -- the same discipline as refusing a "refuted" verdict.

    This is provenance, NOT self-correction. It exposes everything a revision
    would need to trace; it revises nothing. Belief revision is a later layer.

    Never raises: an untraceable belief reports basis NONE.
    """
    observations: list[dict] = []
    sources: list[str] = []
    methods: list[str] = []
    first_at = last_at = None

    try:
        rows = (await pg_session.execute(
            text(_EVIDENCE_FOR_PAIR), {"a": subject, "b": obj})).fetchall()
        for s, predicate, o, source, span, method, observed_at in rows:
            observations.append({
                "subject": s, "predicate": predicate, "object": o,
                "source": source, "span": span, "method": method,
                "observed_at": observed_at,
            })
            if source and source not in sources:
                sources.append(source)
            if method and method not in methods:
                methods.append(method)
            if first_at is None:
                first_at = observed_at
            last_at = observed_at
    except Exception as exc:
        logger.warning("Could not read evidence for %r/%r: %s", subject, obj, exc)

    edge = None
    try:
        record = await (await neo4j_session.run(
            _EDGE, a=subject, b=obj)).single()
        if record and record.get("strength") is not None:
            edge = {"strength": record["strength"], "g2": record.get("g2")}
    except Exception as exc:
        logger.debug("Could not read edge for %r/%r: %s", subject, obj, exc)

    derivation = None
    if not observations:
        try:
            row = (await pg_session.execute(
                text(_INFERENCE), {"a": subject, "b": obj})).fetchall()
            if row:
                via, verdict = row[0]
                derivation = {
                    "premises": [via] if via else [],
                    # The method is named, not a black box: a 2-hop associative
                    # walk over co-occurrence edges. NOT proof -- S25 showed
                    # these produce unsupported claims -- which is why the
                    # verdict travels with it.
                    "method": "2-hop associative inference (infer_links)",
                    "verdict": verdict,
                }
        except Exception as exc:
            logger.debug("Could not read inference for %r/%r: %s",
                         subject, obj, exc)

    dependents: list[dict] = []
    try:
        for dep_subject, dep_object in (await pg_session.execute(
                text(_DEPENDENTS), {"concept": obj})).fetchall():
            dependents.append({"subject": dep_subject, "object": dep_object})
    except Exception as exc:
        logger.debug("Could not read dependents for %r: %s", obj, exc)

    if observations:
        basis = OBSERVED
    elif derivation:
        basis = INFERRED
    else:
        basis = NONE

    predicates = sorted({o["predicate"] for o in observations})
    return {
        "what": {"subject": subject, "predicates": predicates, "object": obj},
        "why": {"basis": basis, "edge": edge},
        "where": sources,
        "how": methods,
        "when": {"first": first_at, "last": last_at},
        "supporting": observations,
        "contradicting": {"status": "deferred",
                          "competingPredicates": predicates if len(predicates) > 1 else []},
        "derivation": derivation,
        "dependents": dependents,
    }
