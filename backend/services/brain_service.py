"""Query layer for the Brain Engine — reads from Neo4j (the knowledge
graph) and Postgres (crawl state)."""
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


async def discover_convergence(seeds: list[str], max_depth: int = 3,
                               min_origins: int = 2, limit: int = 30) -> dict:
    """Multi-origin convergence — the core of the dependency-convergence
    theory. Grow the reachable set from each seed independently and surface the
    concepts that are reached from the MOST distinct, unrelated seeds. A concept
    that many independent origins all arrive at is a candidate 'hidden truth',
    ranked by how many origins converge on it (and, secondarily, how closely).

    Returns convergence points with the originating seeds, the number of
    origins, and the average hop-distance across those origins.
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

    points = [
        {
            "concept": word,
            "originCount": len(origs),
            "origins": sorted(origs),
            "avgDepth": round(depth_total[word] / len(origs), 2),
        }
        for word, origs in origins.items()
        if len(origs) >= min_origins
    ]
    # Strongest convergence first: most origins, then closest average distance.
    points.sort(key=lambda p: (-p["originCount"], p["avgDepth"]))

    if not points:
        return {"seeds": norm_seeds, "convergencePoints": [],
                "error": "No concept was reached from enough independent seeds yet — "
                         "the graph may need more crawling."}
    return {"seeds": norm_seeds, "convergencePoints": points[:limit]}
