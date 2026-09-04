"""Connection management for the Brain Engine's Neo4j knowledge graph."""
import os
from neo4j import AsyncGraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

_driver = None


def get_driver():
    """Get or create the singleton async Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


async def ensure_schema() -> None:
    """Create the uniqueness constraint on Concept.word if it doesn't exist yet."""
    driver = get_driver()
    async with driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT concept_word_unique IF NOT EXISTS "
            "FOR (c:Concept) REQUIRE c.word IS UNIQUE"
        )


async def health_check() -> bool:
    """True if Neo4j is reachable and responds to a trivial query."""
    try:
        driver = get_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            return record is not None and record["ok"] == 1
    except Exception:
        return False


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
