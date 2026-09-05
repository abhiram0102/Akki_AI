"""AKKI Brain Engine — shared graph-write core.

Extracted from `backend.brain_crawler.crawl_one_page` so on-demand learning
(triggered by a user's query) and the background crawler write concepts and
edges to Neo4j through one code path instead of two copies drifting apart.
"""
from collections import Counter

from backend.services.brain_stats_math import log_likelihood_ratio


async def apply_to_graph(session, word_freq: Counter, edge_counts: Counter) -> dict:
    """Upsert concepts/edges for one page (or one on-demand query) into Neo4j.

    `session` is an already-open Neo4j async session — the caller is
    responsible for opening (and closing) it; this function does not manage
    session lifecycle. Returns `{"new_concepts": int, "new_edges": int}`
    counting the concepts/edges touched by this call.
    """
    updated_freq: dict[str, int] = {}
    updated_total = 0

    if word_freq:
        # Upsert word frequencies AND the running global total-occurrence
        # counter in one call, returning post-update values so G2 can be
        # computed below without a second full read.
        result = await session.run(
            "UNWIND $words AS w "
            "MERGE (c:Concept {word: w.word}) "
            "ON CREATE SET c.frequency = w.count, c.first_seen = datetime() "
            "ON MATCH SET c.frequency = c.frequency + w.count "
            "WITH c, w "
            "MERGE (m:Meta {id: 'singleton'}) "
            "ON CREATE SET m.totalWordOccurrences = w.count "
            "ON MATCH SET m.totalWordOccurrences = m.totalWordOccurrences + w.count "
            "RETURN c.word AS word, c.frequency AS frequency, m.totalWordOccurrences AS total",
            words=[{"word": w, "count": c} for w, c in word_freq.items()],
        )
        async for record in result:
            updated_freq[record["word"]] = record["frequency"]
            updated_total = record["total"]  # same value every row — last write wins, all consistent

    if edge_counts:
        # Upsert edge counts, returning the post-update count per edge.
        result = await session.run(
            "UNWIND $edges AS e "
            "MATCH (a:Concept {word: e.cause}) "
            "MATCH (b:Concept {word: e.effect}) "
            "MERGE (a)-[r:CO_OCCURS]->(b) "
            "ON CREATE SET r.count = e.count, r.last_updated = datetime() "
            "ON MATCH SET r.count = r.count + e.count, r.last_updated = datetime() "
            "RETURN e.cause AS cause, e.effect AS effect, r.count AS count",
            edges=[{"cause": c, "effect": eff, "count": n} for (c, eff), n in edge_counts.items()],
        )
        updated_counts: dict[tuple[str, str], int] = {}
        async for record in result:
            updated_counts[(record["cause"], record["effect"])] = record["count"]

        # Recompute G2 for every edge touched this call, using the
        # post-update frequencies/total from above, then write it back —
        # a third small batched call, not one per edge.
        g2_updates = []
        for (cause, effect), count in updated_counts.items():
            freq_a = updated_freq.get(cause, count)
            freq_b = updated_freq.get(effect, count)
            if updated_total > 0:
                g2 = log_likelihood_ratio(count, freq_a, freq_b, updated_total)
                g2_updates.append({"cause": cause, "effect": effect, "g2": g2})

        if g2_updates:
            await session.run(
                "UNWIND $updates AS u "
                "MATCH (a:Concept {word: u.cause})-[r:CO_OCCURS]->(b:Concept {word: u.effect}) "
                "SET r.g2 = u.g2",
                updates=g2_updates,
            )

    return {"new_concepts": len(word_freq), "new_edges": len(edge_counts)}
