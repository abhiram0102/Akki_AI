"""Query layer for the Brain Engine — reads from Neo4j (the knowledge
graph) and Postgres (crawl state)."""
import math
import os
from collections import Counter

from sqlalchemy import select, func

from backend.models import BrainStats, BrainFrontier, BrainDeadLetter
from backend.services.neo4j_service import get_driver, health_check as neo4j_health_check

# Ignore one-off co-occurrences: an edge must be seen at least this many times
# before it counts as a real dependency, in both association ranking and
# convergence traversal. This is the main noise floor on the graph.
MIN_EDGE_COUNT = 2


async def health() -> dict:
    neo4j_ok = await neo4j_health_check()
    return {"neo4j": neo4j_ok, "healthy": neo4j_ok}


async def get_status(pg_session) -> dict:
    stats_result = await pg_session.execute(select(BrainStats).where(BrainStats.id == "singleton"))
    stats = stats_result.scalar_one_or_none()

    frontier_result = await pg_session.execute(select(func.count()).select_from(BrainFrontier))
    frontier_size = frontier_result.scalar() or 0

    driver = get_driver()
    async with driver.session() as session:
        concept_result = await session.run("MATCH (c:Concept) RETURN count(c) AS count")
        concept_count = 0
        async for record in concept_result:
            concept_count = record["count"]

        edge_result = await session.run("MATCH ()-[r:CO_OCCURS]->() RETURN count(r) AS count")
        edge_count = 0
        async for record in edge_result:
            edge_count = record["count"]

    return {
        "totalPages": stats.total_pages if stats else 0,
        "totalSentences": stats.total_sentences if stats else 0,
        "conceptCount": concept_count,
        "edgeCount": edge_count,
        "frontierSize": frontier_size,
        "updatedAt": stats.updated_at.isoformat() if stats and stats.updated_at else None,
    }


async def _top_associations(concept: str, limit: int = 20, min_count: int = MIN_EDGE_COUNT) -> list[dict]:
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:Concept {word: $concept})-[r:CO_OCCURS]->(b) "
            "WHERE r.count >= $min_count "
            "RETURN b.word AS word, r.g2 AS g2, r.count AS count "
            "ORDER BY r.g2 DESC LIMIT $limit",
            concept=concept, limit=limit, min_count=min_count,
        )
        return [{"word": r["word"], "g2": r["g2"], "count": r["count"]} async for r in result]


async def _top_dependencies(concept: str, limit: int = 20, min_count: int = MIN_EDGE_COUNT) -> list[dict]:
    """The reverse of `_top_associations`: concepts that point AT `concept`.

    Edges are genuinely directed — `brain_nlp` orients every one of them from
    the dependency parse (subject->object, with the FORWARD/BACKWARD connective
    tables flipping cause vs prerequisite). Until now nothing ever read them
    backwards, so half the causal information in the graph was unreachable:
    out-edges answer "what does X produce", and only these in-edges answer
    "what does X depend on" / "what causes X".

    This is Function 7 step 6's first bullet ("what this concept depends on")
    in AKKI_FULL_ARCHITECTURE.md, and it costs one reversed arrow.
    """
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:Concept)-[r:CO_OCCURS]->(b:Concept {word: $concept}) "
            "WHERE r.count >= $min_count "
            "RETURN a.word AS word, r.g2 AS g2, r.count AS count "
            "ORDER BY r.g2 DESC LIMIT $limit",
            concept=concept, limit=limit, min_count=min_count,
        )
        return [{"word": r["word"], "g2": r["g2"], "count": r["count"]} async for r in result]


async def _reachable_with_depth(concept: str, max_depth: int = 3, min_count: int = MIN_EDGE_COUNT) -> dict[str, int]:
    """Concepts reachable from `concept` within max_depth hops, traversing only
    edges seen at least min_count times (so one-off co-occurrences don't
    create spurious 'convergence')."""
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH path = (a:Concept {word:$c1})-[:CO_OCCURS*1..%d]->(mid) "
            "WHERE ALL(rel IN relationships(path) WHERE rel.count >= $min_count) "
            "RETURN mid.word AS word, min(length(path)) AS depth" % max_depth,
            c1=concept, min_count=min_count,
        )
        return {r["word"]: r["depth"] async for r in result}


async def infer_links(concept: str, limit: int = 5, min_count: int = MIN_EDGE_COUNT) -> list[dict]:
    """The reasoning step: derive 2-hop connections the graph never stored
    directly. If A->B and B->C are both real (count-floored) edges, C is
    surfaced here as a *derived* link of A — something the brain reasons its
    way to rather than one it looked up.

    Candidates are ranked by path strength (g2(A->B) * g2(B->C)) rather than
    hop count, so the strongest derived connections surface first instead of
    alphabetical noise. `via` names the intermediate concept (B) that produced
    the best (max) strength for each candidate."""
    direct = await _top_associations(concept, min_count=min_count)
    direct_words = {d["word"] for d in direct}

    best: dict[str, dict] = {}
    for b in direct[:12]:
        g2ab = b["g2"]
        seconds = await _top_associations(b["word"], min_count=min_count)
        for s in seconds:
            c = s["word"]
            if c == concept or c in direct_words:
                continue
            strength = g2ab * s["g2"]
            if c not in best or strength > best[c]["strength"]:
                best[c] = {"concept": c, "via": b["word"], "strength": strength, "derived": True}

    ranked = sorted(best.values(), key=lambda d: d["strength"], reverse=True)
    return ranked[:limit]


async def discover(concept: str, concept2: str | None = None) -> dict:
    concept = concept.strip().lower()

    if not concept2:
        associations = await _top_associations(concept)
        if not associations:
            return {"concept": concept, "associations": [], "error": "No known associations yet — the brain hasn't learned this concept."}
        return {"concept": concept, "associations": associations}

    concept2 = concept2.strip().lower()
    reached_from_1 = await _reachable_with_depth(concept)
    reached_from_2 = await _reachable_with_depth(concept2)

    shared = set(reached_from_1) & set(reached_from_2)
    convergence_points = sorted(
        (
            {"concept": word, "depthFrom1": reached_from_1[word], "depthFrom2": reached_from_2[word],
             "combinedDepth": reached_from_1[word] + reached_from_2[word]}
            for word in shared
        ),
        key=lambda c: c["combinedDepth"],
    )

    if not convergence_points:
        return {"concept1": concept, "concept2": concept2, "convergencePoints": [],
                "error": "No convergence found yet within 3 hops of either concept."}

    return {"concept1": concept, "concept2": concept2, "convergencePoints": convergence_points}



# How many random seeds to draw when measuring what the graph reaches by
# chance, and the smallest degree a drawn seed may have. A concept with one or
# two edges reaches almost nothing and would understate the noise floor; the
# floor should be measured against seeds that resemble the ones actually asked
# about. Both are settings rather than constants because the right sample size
# depends on how large the graph has grown.
_BACKGROUND_SAMPLE = int(os.getenv("BRAIN_CONVERGENCE_SAMPLE", "200"))
_BACKGROUND_MIN_DEGREE = 3

# Measured once per (depth, sample) and reused. The measurement costs one query
# per drawn seed, which is far too slow to repeat on every request.
_BACKGROUND: dict[tuple[int, int], dict[str, float]] = {}


async def background_reachability(max_depth: int = 3,
                                  sample_size: int = _BACKGROUND_SAMPLE) -> dict[str, float]:
    """How often each concept is reached from a RANDOM seed.

    This is the graph's own noise floor, measured rather than assumed. Some
    concepts are reached from almost any starting point -- on the current
    graph "example" is reached from 48% of random seed triples, "time" from
    38%, "case" from 35% -- not because they are related to anything in
    particular but because they are common nouns that co-occur with everything.

    Knowing that rate is what separates a finding from a frequent word. It is
    deliberately NOT a list of words to ignore: a stopword list would be
    exactly the hardcoded knowledge this project exists to avoid, would be
    wrong for any corpus that is not English prose, and could not adapt as the
    graph grows. The floor here is a property of THIS graph at THIS moment, and
    is re-measured when the graph is re-crawled.
    """
    key = (max_depth, sample_size)
    if key in _BACKGROUND:
        return _BACKGROUND[key]

    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Concept) WITH c, COUNT{(c)--()} AS degree "
            "WHERE degree >= $min_degree "
            "RETURN c.word AS word ORDER BY rand() LIMIT $limit",
            min_degree=_BACKGROUND_MIN_DEGREE, limit=sample_size,
        )
        seeds = [record["word"] async for record in result]

    if not seeds:
        _BACKGROUND[key] = {}
        return {}

    reached: Counter = Counter()
    for seed in seeds:
        for word in await _reachable_with_depth(seed, max_depth):
            if word != seed:
                reached[word] += 1

    # Jeffreys smoothing, so a concept that appeared in none of the draws gets a
    # small non-zero rate instead of an infinite surprise score.
    profile = {word: (hits + 0.5) / (len(seeds) + 1) for word, hits in reached.items()}
    profile["__sample__"] = float(len(seeds))
    _BACKGROUND[key] = profile
    return profile


def _surprise(origin_count: int, seed_count: int, rate: float) -> float:
    """How unlikely it is that this many independent seeds all reached this
    concept by chance.

    The probability of at least `origin_count` of `seed_count` random seeds
    reaching a concept that a random seed reaches with probability `rate`,
    reported as -log10 so that larger is more surprising. Same idea as the
    permutation test used for sense counts: compare what was observed against
    what chance produces, rather than trusting the raw count.
    """
    tail = sum(
        math.comb(seed_count, k) * (rate ** k) * ((1 - rate) ** (seed_count - k))
        for k in range(origin_count, seed_count + 1)
    )
    tail = min(max(tail, 1e-12), 1.0)
    return round(-math.log10(tail), 2)


async def discover_convergence(seeds: list[str], max_depth: int = 3,
                               min_origins: int = 2, limit: int = 30,
                               against_chance: bool = True) -> dict:
    """Multi-origin convergence — the core of the dependency-convergence
    theory. Grow the reachable set from each seed independently and surface the
    concepts that are reached from the MOST distinct, unrelated seeds. A concept
    that many independent origins all arrive at is a candidate 'hidden truth',
    ranked by how SURPRISING that convergence is, not by how many origins
    reach it.

    Counting origins alone does not work, and the failure was measured rather
    than anticipated. On the live graph, seeding photosynthesis, consciousness
    and penicillin returns "dna" and "mechanism" from all three origins -- and
    also "time", "century", "process" and "type" from two apiece. Ranked by
    origin count those are one undifferentiated list. Against 40 random seed
    triples, however, "time" turns up 38% of the time and "dna" never does. One
    of them is a finding and the other is a common noun, and the count cannot
    tell them apart because the count is the same.

    So each point is scored against `background_reachability`: how likely it is
    that this many independent seeds would all arrive here by chance. A concept
    that everything reaches has to be reached from far more origins before it
    means anything, and one that nothing normally reaches is interesting
    immediately. The floor is measured from the graph itself, so no words are
    named anywhere.

    Returns convergence points with the originating seeds, the number of
    origins, the average hop-distance, the concept's background rate, and the
    surprise score they are ranked by.
    """
    norm_seeds = [s.strip().lower() for s in seeds if s and s.strip()]
    seed_set = set(norm_seeds)
    if len(seed_set) < min_origins:
        return {"seeds": norm_seeds, "convergencePoints": [],
                "error": f"Need at least {min_origins} distinct seed concepts."}

    origins: dict[str, set] = {}
    depth_total: dict[str, int] = {}
    for seed in seed_set:
        reachable = await _reachable_with_depth(seed, max_depth)
        for word, depth in reachable.items():
            if word in seed_set:
                continue  # a seed reaching another seed isn't a convergence point
            origins.setdefault(word, set()).add(seed)
            depth_total[word] = depth_total.get(word, 0) + depth

    background = await background_reachability(max_depth) if against_chance else {}
    # With no measured floor every concept is treated as equally unexpected,
    # which is the old behaviour: ranking falls back to the raw origin count.
    default_rate = 1.0 / (background.get("__sample__", 0) + 1) if background else 1.0

    points = []
    for word, origs in origins.items():
        if len(origs) < min_origins:
            continue
        rate = background.get(word, default_rate)
        points.append({
            "concept": word,
            "originCount": len(origs),
            "origins": sorted(origs),
            "avgDepth": round(depth_total[word] / len(origs), 2),
            "randomRate": round(rate, 4),
            "surprise": _surprise(len(origs), len(seed_set), rate) if background else 0.0,
        })

    # Most surprising first; origin count and closeness break ties.
    points.sort(key=lambda p: (-p["surprise"], -p["originCount"], p["avgDepth"]))

    if not points:
        return {"seeds": norm_seeds, "convergencePoints": [],
                "error": "No concept was reached from enough independent seeds yet — "
                         "the graph may need more crawling."}
    return {"seeds": norm_seeds, "convergencePoints": points[:limit]}
