"""Query layer for the Brain Engine — reads from Neo4j (the knowledge
graph) and Postgres (crawl state)."""
from sqlalchemy import select, func

from backend.models import BrainStats, BrainFrontier, BrainDeadLetter
from backend.services.neo4j_service import get_driver, health_check as neo4j_health_check


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


async def _top_associations(concept: str, limit: int = 20) -> list[dict]:
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:Concept {word: $concept})-[r:CO_OCCURS]->(b) "
            "RETURN b.word AS word, r.g2 AS g2, r.count AS count "
            "ORDER BY r.g2 DESC LIMIT $limit",
            concept=concept, limit=limit,
        )
        return [{"word": r["word"], "g2": r["g2"], "count": r["count"]} async for r in result]


async def _reachable_with_depth(concept: str, max_depth: int = 3) -> dict[str, int]:
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH path = (a:Concept {word:$c1})-[:CO_OCCURS*1..%d]->(mid) "
            "RETURN mid.word AS word, min(length(path)) AS depth" % max_depth,
            c1=concept,
        )
        return {r["word"]: r["depth"] async for r in result}


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
