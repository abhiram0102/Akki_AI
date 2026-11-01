"""Typed causal reasoning over the Brain Engine's knowledge.

The problem this exists to fix, stated by the graph's own measurements
--------------------------------------------------------------------
The `CO_OCCURS` graph throws the verb away, so "X produces Y" and "X destroys
Y" become the same edge. `brain_prediction` measured the consequence directly:
following edge DIRECTION through that graph (a->mid->cand) recovered held-out
facts **0.0%** of the time. The reason is stated in `brain_nlp`: *directions
built from an unnamed relation do not compose.* A co-occurrence edge is an
association, not a relation, and associations cannot be chained into inference.

Reasoning IS composition. If `A causes B` and `B causes C`, then `A` brings
about `C` even though nothing ever wrote that edge down. That only works when
the edges carry a *typed, directed, transitive* relation — which `CO_OCCURS`
never did.

What this module does
---------------------
`brain_relations` has logged 300k+ typed observations `(subject, verb, object)`.
The extractor (`brain_nlp.extract_relations`) already commits to a direction
for every causal verb it recognises: FORWARD_CONNECTIVES (cause/lead/produce/
create/enable/trigger/result) were stored subject->object as cause->effect, and
BACKWARD_CONNECTIVES (require/need/depend/rely/stem) were stored oriented
prerequisite->dependent. That commitment is the highest-precision typing signal
available, and it is FREE — it was made at extraction time and then discarded
by the co-occurrence write. This module recovers it.

It projects those observations into a second, typed edge set in the same Neo4j
graph — `[:CAUSES]`, `[:REQUIRES]`, `[:PART_OF]`, `[:PREVENTS]` — and reasons
OVER them by composition. The projection is high-precision by construction: only
verbs whose causal/structural semantics the extractor already committed to are
projected; everything else is left untyped, exactly where relation induction
would later refine it.

The claim is not taken on faith. `measure_reasoning` runs the SAME held-out
recovery test that scored the untyped graph at 0.0%, over the typed graph, and
reports both side by side. The number is the arbiter, as everywhere else here.
"""
import math

from backend.services.brain_nlp import FORWARD_CONNECTIVES, BACKWARD_CONNECTIVES
from backend.services.neo4j_service import get_driver

# An observation must be seen at least this many times before it is projected
# as a typed relation. The same noise floor `brain_service` puts on CO_OCCURS
# (MIN_EDGE_COUNT = 2): a relation asserted on exactly one page, once, is a
# candidate for an extraction error, not yet evidence of a real relation.
MIN_RELATION_COUNT = 2

# Verb lemma -> typed, transitive relation.
#
# CAUSES and REQUIRES are NOT new interpretation: they are the exact two
# semantic classes `brain_nlp` already committed to when it oriented every
# forward/backward connective at extraction time. They are imported from there,
# not re-listed here, so this map cannot drift from what the extractor did.
#
# The remaining verbs are a deliberately SMALL, high-precision extension: verbs
# whose causal/structural sense is unambiguous in ordinary technical prose. The
# design principle is precision over coverage — a wrong typed edge is worse than
# a missing one, because a wrong edge composes into a wrong chain. Anything not
# listed is left untyped rather than guessed. This is the curated-table class
# the project already accepts for FORWARD_CONNECTIVES/BACKWARD_CONNECTIVES, and
# it exists to be superseded by relation induction over the growing log, not to
# stand forever.
_EXTRA_CAUSES = {
    "generate", "induce", "drive", "spark", "bring", "yield", "spawn",
    "provoke", "elicit", "engender", "precipitate", "prompt",
}
_EXTRA_REQUIRES = {"presuppose", "necessitate", "entail", "demand"}
_PREVENTS = {
    "prevent", "inhibit", "block", "suppress", "stop", "halt", "impede",
    "hinder", "avoid", "counteract", "reduce",
}
_PART_OF = {
    "contain", "include", "comprise", "consist", "compose", "constitute",
    "incorporate", "encompass",
}

# The projection direction for each relation, resolved from the ORDER the
# extractor stored the triple in. For a stored triple (s, verb, o):
#
#   CAUSES    : s caused o          -> (s)-[:CAUSES]->(o)
#   REQUIRES  : s is prerequisite,  -> (o)-[:REQUIRES]->(s)   (dependent -> prereq,
#               o is the dependent     so REQUIRES chains in the dependency
#                                      direction: o requires s, s requires z ...)
#   PART_OF   : s contains o        -> (o)-[:PART_OF]->(s)     (part -> whole)
#   PREVENTS  : s prevents o        -> (s)-[:PREVENTS]->(o)
#
# CAUSES / REQUIRES / PART_OF are transitive and therefore composable. PREVENTS
# is NOT transitive (A prevents B, B prevents C does not make A prevent C) and
# is projected for explanation only, never chained in `reason`.
RELATION_TYPES = ("CAUSES", "REQUIRES", "PART_OF", "PREVENTS")
_TRANSITIVE = {"CAUSES", "REQUIRES", "PART_OF"}


def relation_for(verb: str) -> tuple[str, bool] | None:
    """Map a verb lemma to (relation_type, flip) or None if it is not typed.

    `flip` is True when the typed edge runs opposite to the stored (subject ->
    object) order — REQUIRES and PART_OF both point from the dependent/part back
    to the prerequisite/whole, which is the reverse of how the triple was
    logged.
    """
    v = verb.lower().strip()
    if not v:
        return None
    if v in FORWARD_CONNECTIVES or v in _EXTRA_CAUSES:
        return ("CAUSES", False)
    if v in BACKWARD_CONNECTIVES or v in _EXTRA_REQUIRES:
        return ("REQUIRES", True)
    if v in _PART_OF:
        return ("PART_OF", True)
    if v in _PREVENTS:
        return ("PREVENTS", False)
    return None


def typed_edges_from_triples(triples) -> dict[str, list[dict]]:
    """Convert (subject, verb, object[, count]) rows into typed edge upserts,
    bucketed by relation type. Pure function — no I/O — so it is unit-testable
    against fixed input and reused by both the live crawler projection and the
    bulk backfill.
    """
    buckets: dict[str, dict[tuple[str, str], dict]] = {r: {} for r in RELATION_TYPES}
    for row in triples:
        subject, verb, obj = row[0], row[1], row[2]
        count = row[3] if len(row) > 3 else 1
        if not (subject and verb and obj) or subject == obj:
            continue
        mapped = relation_for(verb)
        if mapped is None:
            continue
        rel, flip = mapped
        a, b = (obj, subject) if flip else (subject, obj)
        if a == b:
            continue
        key = (a, b)
        slot = buckets[rel].setdefault(key, {"src": a, "dst": b, "count": 0, "verbs": set()})
        slot["count"] += count
        slot["verbs"].add(verb.lower().strip())
    return {
        rel: [
            {"src": e["src"], "dst": e["dst"], "count": e["count"],
             "verbs": sorted(e["verbs"])}
            for e in edges.values()
        ]
        for rel, edges in buckets.items()
    }


# One MERGE per relation type. Concepts are MERGEd (not just MATCHed) so a typed
# relation can exist even for a concept the CO_OCCURS pass never created an edge
# for — a relation the brain read is evidence in its own right.
_PROJECT = """
UNWIND $edges AS e
MERGE (a:Concept {word: e.src})
MERGE (b:Concept {word: e.dst})
MERGE (a)-[r:%s]->(b)
ON CREATE SET r.observations = e.count, r.verbs = e.verbs, r.updated = datetime()
ON MATCH  SET r.observations = r.observations + e.count,
              r.verbs = e.verbs, r.updated = datetime()
"""


async def project_typed_edges(session, triples) -> dict[str, int]:
    """Write one batch of triples as typed edges into an open Neo4j session.

    Called by the crawler for every page (keeping the typed graph live) and by
    the backfill for the whole `brain_relations` log. Returns per-type counts of
    distinct edges written.
    """
    buckets = typed_edges_from_triples(triples)
    written: dict[str, int] = {}
    for rel, edges in buckets.items():
        if not edges:
            continue
        await session.run(_PROJECT % rel, edges=edges)
        written[rel] = len(edges)
    return written


async def ensure_indexes() -> None:
    """Range indexes on Concept.word are already covered by the uniqueness
    constraint; typed relationships need no extra schema. Present so callers have
    one place to add relationship indexes if traversal profiling later wants
    them."""
    return None


# ── Reasoning: composition over the typed graph ────────────────────────────────

# Reachable set along ONE transitive relation, with the shortest chain and the
# concepts on it. `%s` is validated against RELATION_TYPES before use, never
# taken from the request directly, so this is not an injection surface.
_REACH = """
MATCH path = (a:Concept {word: $concept})-[:%s*1..%d]->(t:Concept)
WHERE a <> t AND ALL(r IN relationships(path) WHERE r.observations >= $min_count)
WITH t, path
ORDER BY length(path) ASC
WITH t, head(collect(path)) AS best
RETURN t.word AS concept,
       length(best) AS depth,
       [n IN nodes(best) | n.word] AS chain,
       reduce(s = 0, r IN relationships(best) | s + r.observations) AS evidence
ORDER BY depth ASC, evidence DESC
LIMIT $limit
"""


def _check_relation(relation: str) -> str:
    rel = relation.upper().strip()
    if rel not in RELATION_TYPES:
        raise ValueError(f"unknown relation {relation!r}; expected one of {RELATION_TYPES}")
    return rel


async def reason(concept: str, relation: str = "CAUSES", max_depth: int = 3,
                 limit: int = 20, min_count: int = MIN_RELATION_COUNT) -> dict:
    """Follow one typed relation transitively from `concept`.

    "What does inflation CAUSE?" walks `[:CAUSES*1..N]` and returns every
    concept reached, each with the shortest causal chain that reaches it and the
    total observation weight along that chain. Depth 1 results are things the
    brain read directly; depth >= 2 are DERIVED by composition — connections no
    single sentence stated, which is the point.

    Only transitive relations may be chained. Asking to chain PREVENTS is a
    caller error, not silently reinterpreted.
    """
    rel = _check_relation(relation)
    if rel not in _TRANSITIVE:
        return {"concept": concept, "relation": rel, "results": [],
                "error": f"{rel} is not transitive and cannot be reasoned over; "
                         f"use one of {sorted(_TRANSITIVE)}."}
    concept = concept.strip().lower()
    depth = max(1, min(int(max_depth), 5))
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            _REACH % (rel, depth),
            concept=concept, min_count=min_count, limit=limit,
        )
        results = [
            {"concept": r["concept"], "depth": r["depth"],
             "chain": r["chain"], "evidence": r["evidence"],
             "derived": r["depth"] >= 2}
            async for r in result
        ]
    if not results:
        return {"concept": concept, "relation": rel, "results": [],
                "error": f"Nothing reached from '{concept}' along {rel} yet — "
                         "the typed graph may need more crawling on this topic."}
    return {"concept": concept, "relation": rel, "results": results}


_PATH = """
MATCH path = shortestPath(
  (a:Concept {word: $a})-[:%s*1..%d]->(b:Concept {word: $b}))
WHERE ALL(r IN relationships(path) WHERE r.observations >= $min_count)
RETURN [n IN nodes(path) | n.word] AS chain,
       length(path) AS depth,
       reduce(s = 0, r IN relationships(path) | s + r.observations) AS evidence
"""


async def causal_path(a: str, b: str, relation: str = "CAUSES",
                      max_depth: int = 5, min_count: int = MIN_RELATION_COUNT) -> dict:
    """The shortest typed chain explaining how `a` reaches `b`.

    "How does deforestation lead to flooding?" returns the actual chain of
    intermediate concepts the graph strings together, or an honest empty result
    if it cannot connect them along that relation within `max_depth`.
    """
    rel = _check_relation(relation)
    a, b = a.strip().lower(), b.strip().lower()
    depth = max(1, min(int(max_depth), 6))
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            _PATH % (rel, depth), a=a, b=b, min_count=min_count)
        record = await result.single()
    if not record:
        return {"from": a, "to": b, "relation": rel, "chain": [],
                "error": f"No {rel} chain from '{a}' to '{b}' within {depth} hops."}
    return {"from": a, "to": b, "relation": rel,
            "chain": record["chain"], "depth": record["depth"],
            "evidence": record["evidence"]}


# ── Chat: parse-intent -> typed reasoning, one fast graph round-trip ───────────
# The natural-language layer already exists (brain_query.parse turns a question
# into an intent + concepts). This routes that intent to the typed reasoner and
# composes a grounded answer. Deliberately NO network, NO live learning, NO
# curiosity — those are what make /api/brain/ask take 30s. Every path here is a
# pure graph query, so a question is answered in well under a second.
#
# The answer text is composed deterministically from the graph results (no LLM,
# nothing invented): it states exactly the chains the graph holds, or says
# plainly that it holds none.

_INTENT_RELATION = {"effect": "CAUSES", "cause": "REQUIRES"}
_RELATION_VERB = {"CAUSES": "causes", "REQUIRES": "requires", "PART_OF": "is part of"}
_ARROW = "\u2192"  # kept as a name so f-strings never contain a backslash escape


def _summarise(concept: str, results: list[dict], relation: str) -> str:
    if not results:
        return ""
    verb = _RELATION_VERB.get(relation, relation.lower())
    direct = [r["concept"] for r in results if not r.get("derived")]
    derived = [r for r in results if r.get("derived")]
    parts = []
    if direct:
        parts.append(f"{concept} {verb}: {', '.join(direct[:6])}.")
    if derived:
        chains = "; ".join(f" {_ARROW} ".join(r["chain"]) for r in derived[:3])
        parts.append(f"Reasoned (no single source stated these): {chains}.")
    return " ".join(parts)


async def answer_question(intent: str, topics: list[str], max_depth: int = 3,
                          limit: int = 8, min_count: int = MIN_RELATION_COUNT) -> dict:
    """Route a parsed question to the typed reasoner and compose the answer.

    `intent`/`topics` come from `brain_query.parse`. Mapping:
      effect ("what does X lead to")   -> reason(X, CAUSES)
      cause  ("why does X happen")     -> reason(X, REQUIRES)  (what X needs)
      relate ("how do X and Y link")   -> causal_path(X, Y), tried both ways
      define / explore / anything else -> a compact CAUSES+REQUIRES+PART_OF
                                          profile of the primary concept
    """
    topics = [t.strip().lower() for t in topics if t and t.strip()]
    if not topics:
        return {"intent": intent, "topics": [], "results": [],
                "text": "No concept found in the question.", "answered": False}
    primary = topics[0]

    if intent in _INTENT_RELATION:
        rel = _INTENT_RELATION[intent]
        out = await reason(primary, relation=rel, max_depth=max_depth, limit=limit, min_count=min_count)
        results = out.get("results", [])
        return {"intent": intent, "topics": topics, "relation": rel, "results": results,
                "text": _summarise(primary, results, rel) or
                        f"The brain has no {_RELATION_VERB[rel]} links for '{primary}' yet.",
                "answered": bool(results)}

    if intent == "relate" and len(topics) >= 2:
        a, b = topics[0], topics[1]
        arrow = f" {_ARROW} "
        forward = await causal_path(a, b, max_depth=max(max_depth, 4), min_count=min_count)
        if forward.get("chain"):
            chain = arrow.join(forward["chain"])
            return {"intent": intent, "topics": topics, "relation": "CAUSES",
                    "path": forward,
                    "text": f"{a} leads to {b}: {chain}.",
                    "answered": True}
        backward = await causal_path(b, a, max_depth=max(max_depth, 4), min_count=min_count)
        if backward.get("chain"):
            chain = arrow.join(backward["chain"])
            return {"intent": intent, "topics": topics, "relation": "CAUSES",
                    "path": backward,
                    "text": f"{b} leads to {a}: {chain}.",
                    "answered": True}
        return {"intent": intent, "topics": topics, "path": {"chain": []},
                "text": f"No causal chain found between '{a}' and '{b}' within "
                        f"{max(max_depth, 4)} hops.", "answered": False}

    # define / explore / fallback: a compact typed profile of the concept.
    profile: dict[str, list[dict]] = {}
    sentences: list[str] = []
    for rel in ("CAUSES", "REQUIRES", "PART_OF"):
        out = await reason(primary, relation=rel, max_depth=1, limit=5, min_count=min_count)
        results = out.get("results", [])
        profile[rel] = results
        summary = _summarise(primary, results, rel)
        if summary:
            sentences.append(summary)
    return {"intent": intent, "topics": topics, "profile": profile,
            "text": " ".join(sentences) or
                    f"The brain has no typed relations for '{primary}' yet.",
            "answered": bool(sentences)}


# ── Verbalization: the brain reasons, a local LLM speaks (grounded GraphRAG) ───
# The graph decides WHAT is true; the LLM only phrases it. The model is handed
# ONLY the facts the graph produced and told not to go beyond them, so the words
# are fluent but the knowledge is the brain's, not the LLM's. Streamed, because
# CPU generation of a paragraph is ~30s and the chat should type, not block.

_VERBALIZE_SYSTEM = (
    "You are AKKI's brain — a knowledge graph. You speak ONLY what the graph has "
    "learned. You are given a list of facts the graph holds. Rephrase EXACTLY "
    "those facts as fluent, natural prose. Absolute rules, no exceptions:\n"
    "1. Use ONLY the given facts. Never add a cause, effect, mechanism, "
    "definition, example, or detail that is not literally in the list — even if "
    "you personally know more. Your own training knowledge is FORBIDDEN here.\n"
    "2. If the facts are few, your answer must be correspondingly short. One "
    "fact means one short sentence. Do not pad.\n"
    "3. If the facts are empty, reply only: 'The brain hasn't learned enough "
    "about this yet.'\n"
    "4. Weave any chains written a -> b -> c into a single explanatory sentence.\n"
    "Keep it to at most 3 sentences."
)


def facts_for_llm(answer: dict) -> str:
    """The grounded fact list handed to the verbalizer — exactly what the graph
    holds and nothing else, so the LLM cannot range beyond it. `answer` is an
    `answer_question` result, whose `text` already states the direct links and
    the derived (a -> b -> c) chains deterministically."""
    return (answer.get("text") or "").strip()


async def verbalize_stream(query: str, facts: str, num_predict: int = 220):
    """Yield a fluent, grounded answer token-by-token via the local LLM.

    Raises RuntimeError (from ollama_service) if no local model is reachable;
    the caller falls back to the deterministic `facts` text so the chat never
    dead-ends on an LLM outage.
    """
    from backend.services.ollama_service import ollama_service
    prompt = (f"Question: {query}\n\n"
              f"Facts the knowledge graph holds:\n{facts}\n\nAnswer:")
    async for chunk in ollama_service.chat_stream(
        [{"role": "system", "content": _VERBALIZE_SYSTEM},
         {"role": "user", "content": prompt}],
        model="llama3.2:latest", temperature=0.2, num_predict=num_predict,
    ):
        yield chunk


# ── Proof: the held-out recovery test the untyped graph failed ────────────────

# Rank what `concept` should CAUSE, by TYPED transitive composition: concepts
# reached two causal hops away (concept -> mid -> candidate), each weighted by
# how rare the middle concept's causal fan-out is. This is Adamic-Adar's rarity
# weighting applied along typed, directed, composable edges instead of
# undirected co-occurrence — the exact operation that scored 0.0% on the
# untyped graph.
_PREDICT_TYPED = """
MATCH (a:Concept {word: $concept})-[:%s]->(mid)-[:%s]->(cand:Concept)
WHERE cand <> a
  AND cand.word <> $concept
  AND (cand.word = $withheld OR NOT (a)-[:%s]->(cand))
WITH cand, mid, COUNT{ (mid)-[:%s]->() } AS mid_out
RETURN cand.word AS word, sum(1.0 / log(mid_out + 2.0)) AS score
ORDER BY score DESC LIMIT $limit
"""

# The untyped baseline, verbatim from brain_prediction, run on the SAME held-out
# edges so the two numbers are directly comparable.
_PREDICT_BASELINE = """
MATCH (a:Concept {word: $concept})--(shared)--(candidate:Concept)
WHERE candidate <> a AND (candidate.word = $withheld OR NOT (a)--(candidate))
WITH candidate, shared, COUNT{(shared)--()} AS shared_degree
RETURN candidate.word AS word, sum(1.0 / log(shared_degree + 2.0)) AS score
ORDER BY score DESC LIMIT $limit
"""

# Testable CAUSES edges: both endpoints need enough causal structure for a
# prediction to have been POSSIBLE, otherwise the test measures coverage, not
# reasoning. Mirrors brain_prediction._TESTABLE_RELATIONS.
_TESTABLE_TYPED = """
MATCH (a:Concept)-[e:%s]->(b:Concept)
WHERE e.observations >= $min_count
  AND COUNT{ (a)-[:%s]->() } >= $min_source_out
  AND COUNT{ (b)--() } >= $min_target_degree
RETURN a.word AS source, b.word AS target
ORDER BY rand() LIMIT $sample
"""

_CANDIDATE_SPACE = """
MATCH (c:Concept) WHERE COUNT{(c)--()} >= $min_target_degree RETURN count(c) AS size
"""


async def measure_reasoning(relation: str = "CAUSES", sample: int = 150,
                            limit: int = 10, min_count: int = MIN_RELATION_COUNT,
                            min_source_out: int = 3, min_target_degree: int = 3) -> dict:
    """Hide a typed relation and see whether composition rebuilds it.

    The exact methodology `brain_prediction.measure_knowledge` used to score the
    untyped graph — take known edges, hide them one at a time, try to recover the
    hidden target from the rest of the graph, report top-k recovery and mean
    reciprocal rank against chance. Run here over TYPED edges via typed
    composition, AND over the untyped baseline on the identical held-out set, so
    the comparison is like-for-like.

    Returns `typed` and `baseline` blocks plus `improvement` (typed lift over
    baseline). If `improvement` <= 1.0, typing did not help and this says so.
    """
    rel = _check_relation(relation)
    driver = get_driver()
    async with driver.session() as session:
        rows = await session.run(
            _TESTABLE_TYPED % (rel, rel), min_count=min_count,
            min_source_out=min_source_out, min_target_degree=min_target_degree,
            sample=sample)
        relations = [(r["source"], r["target"]) async for r in rows]

        space_rows = await session.run(_CANDIDATE_SPACE, min_target_degree=min_target_degree)
        candidate_space = [r["size"] async for r in space_rows][0]

        if not relations or not candidate_space:
            return {"relation": rel, "tested": 0, "candidateSpace": candidate_space,
                    "typed": _empty_score(), "baseline": _empty_score(),
                    "improvement": 0.0,
                    "note": "no testable typed edges yet — the typed graph needs "
                            "backfilling or more crawling."}

        typed_hits = typed_rr = 0
        base_hits = base_rr = 0
        for source, target in relations:
            typed = await session.run(
                _PREDICT_TYPED % (rel, rel, rel, rel),
                concept=source, withheld=target, limit=limit)
            typed_words = [r["word"] async for r in typed]
            if target in typed_words:
                typed_hits += 1
                typed_rr += 1.0 / (typed_words.index(target) + 1)

            base = await session.run(
                _PREDICT_BASELINE, concept=source, withheld=target, limit=limit)
            base_words = [r["word"] async for r in base]
            if target in base_words:
                base_hits += 1
                base_rr += 1.0 / (base_words.index(target) + 1)

    n = len(relations)
    chance = limit / candidate_space
    typed_block = _score(typed_hits, typed_rr, n, chance)
    base_block = _score(base_hits, base_rr, n, chance)
    improvement = (round(typed_block["recoveryRate"] / base_block["recoveryRate"], 2)
                   if base_block["recoveryRate"] else
                   (float("inf") if typed_block["recoveryRate"] else 0.0))
    return {
        "relation": rel,
        "tested": n,
        "candidateSpace": candidate_space,
        "chanceRate": round(chance, 6),
        "typed": typed_block,
        "baseline": base_block,
        "improvement": improvement,
    }


def _score(hits: int, rr: float, n: int, chance: float) -> dict:
    rate = hits / n if n else 0.0
    return {
        "recovered": hits,
        "recoveryRate": round(rate, 4),
        "lift": round(rate / chance, 1) if chance else 0.0,
        "meanReciprocalRank": round(rr / n, 4) if n else 0.0,
    }


def _empty_score() -> dict:
    return {"recovered": 0, "recoveryRate": 0.0, "lift": 0.0, "meanReciprocalRank": 0.0}


# ── Bulk backfill: build the typed graph from the existing observation log ─────

_READ_RELATIONS = (
    "SELECT subject, relation, object, count FROM brain_relations "
    "WHERE count >= :min_count"
)


async def backfill(min_count: int = MIN_RELATION_COUNT, batch: int = 5000) -> dict:
    """Project every qualifying row of `brain_relations` into typed edges.

    One-time (idempotent — MERGE) build of the typed graph from observations the
    crawler logged before this module existed. Streams the log in batches so a
    300k-row table does not have to be materialised in memory at once. Safe to
    re-run; re-running re-sums observations, so it is meant to be run once on
    cutover and thereafter kept current by the crawler's per-page projection.
    """
    from sqlalchemy import text
    from backend.database import AsyncSessionLocal

    totals: dict[str, int] = {r: 0 for r in RELATION_TYPES}
    rows_read = 0
    driver = get_driver()
    async with AsyncSessionLocal() as pg, driver.session() as graph:
        result = await pg.stream(text(_READ_RELATIONS), {"min_count": min_count})
        pending: list[tuple] = []
        async for row in result:
            pending.append((row.subject, row.relation, row.object, row.count))
            if len(pending) >= batch:
                written = await project_typed_edges(graph, pending)
                for rel, c in written.items():
                    totals[rel] += c
                rows_read += len(pending)
                pending = []
        if pending:
            written = await project_typed_edges(graph, pending)
            for rel, c in written.items():
                totals[rel] += c
            rows_read += len(pending)

    return {"rowsProjected": rows_read, "typedEdgesByRelation": totals}


async def _main() -> None:
    """`python -m backend.services.brain_reasoning` — backfill then self-measure
    against the live graph. This is the cutover runner."""
    import json
    from backend.services.neo4j_service import close_driver

    built = await backfill()
    print("BACKFILL:", json.dumps(built, indent=2))
    for rel in _TRANSITIVE:
        measured = await measure_reasoning(relation=rel)
        print(f"MEASURE[{rel}]:", json.dumps(measured, indent=2))
    await close_driver()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
