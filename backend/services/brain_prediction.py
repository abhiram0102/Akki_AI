"""Whether the brain knows anything, tested by making it guess.

Every other measurement in this project counts what the brain has collected:
pages read, concepts stored, relations extracted. None of them can tell
knowledge from volume, because a graph of pure noise scores well on all of
them -- it just needs to be big.

This asks a different question, and it is the first one the brain can FAIL.

Take a relation it has already learned and hide it. Ask the rest of the graph
what that concept connects to. If the hidden fact comes back near the top,
then the fact was IMPLIED by everything else the brain knows -- it is not
merely stored, it is understood well enough to be reconstructed. If it comes
back at chance, the brain memorised a sentence and learned nothing from it.

Measured on the live graph at ~54k concepts: 8-9% of hidden relations are
recovered in the top ten out of a 6,500-concept candidate space, against 0.15%
for chance. That is roughly 55x better than guessing, and it is also wrong
nine times in ten. Both halves of that are worth keeping in view.

What this makes possible is comparison. Any change to extraction, discovery,
crawling or storage can now be asked the only question that matters -- does
the brain predict better afterwards? -- instead of the question that is easy
but hollow, which is whether it collected more.
"""
import math

from backend.services.neo4j_service import get_driver

# Rank candidates by their shared neighbours, weighting each shared neighbour
# by how rare it is: two concepts both linked to something obscure is real
# evidence, while both being linked to a hub is not. This is the Adamic-Adar
# measure, and it was chosen by measurement rather than taste -- against 150
# hidden relations it recovered 8.0%, where plain shared-neighbour counting
# managed 6.0%.
#
# Two variants that sound better and measured worse are recorded in
# docs/architecture-log.md rather than left as folklore: weighting by the
# stored `g2` edge strength HALVED the score, and following edge DIRECTION
# (a->mid->cand) scored exactly zero, which says the graph's directions do not
# compose and is the clearest evidence available that `CO_OCCURS` is an
# association rather than a relation.
_RANK_BY_RARE_SHARED_NEIGHBOURS = """
MATCH (a:Concept {word: $concept})--(shared)--(candidate:Concept)
WHERE candidate <> a AND (candidate.word = $withheld OR NOT (a)--(candidate))
WITH candidate, shared, COUNT{(shared)--()} AS shared_degree
RETURN candidate.word AS word, sum(1.0 / log(shared_degree + 2.0)) AS score
ORDER BY score DESC LIMIT $limit
"""

# A relation is only worth testing if a prediction was possible at all: a
# concept with two edges cannot be expected to imply anything, and including
# such cases measures the crawl's coverage rather than the graph's structure.
_TESTABLE_RELATIONS = """
MATCH (a:Concept)-[e:CO_OCCURS]->(b:Concept)
WHERE e.count >= $min_count
  AND COUNT{(a)--()} >= $min_source_degree
  AND COUNT{(b)--()} >= $min_target_degree
RETURN a.word AS source, b.word AS target
ORDER BY rand() LIMIT $sample
"""

_CANDIDATE_SPACE = """
MATCH (c:Concept) WHERE COUNT{(c)--()} >= $min_target_degree RETURN count(c) AS size
"""


async def predict(concept: str, limit: int = 10,
                  withheld: str | None = None) -> list[dict]:
    """What the graph expects `concept` to connect to, strongest first.

    `withheld` names a concept that is allowed back into the candidate set even
    though a direct edge exists -- that is what makes a fair test possible,
    since otherwise the answer is excluded by the very filter that keeps this
    from returning things already known.
    """
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            _RANK_BY_RARE_SHARED_NEIGHBOURS,
            concept=concept, withheld=withheld, limit=limit,
        )
        return [{"concept": r["word"], "score": r["score"]} async for r in result]


async def measure_knowledge(sample: int = 150, limit: int = 10,
                            min_count: int = 2, min_source_degree: int = 6,
                            min_target_degree: int = 3) -> dict:
    """Hide known relations one at a time and see how many the graph rebuilds.

    Returns the recovery rate, the rate chance alone would give on the same
    candidate space, the lift between them, and mean reciprocal rank -- which
    separates "found it at position one" from "found it at position ten" in a
    way a hit rate cannot.
    """
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            _TESTABLE_RELATIONS, min_count=min_count,
            min_source_degree=min_source_degree,
            min_target_degree=min_target_degree, sample=sample,
        )
        relations = [(r["source"], r["target"]) async for r in result]

        space = await session.run(_CANDIDATE_SPACE,
                                  min_target_degree=min_target_degree)
        candidate_space = [r["size"] async for r in space][0]

        if not relations or not candidate_space:
            return {"tested": 0, "recovered": 0, "recoveryRate": 0.0,
                    "chanceRate": 0.0, "lift": 0.0, "meanReciprocalRank": 0.0,
                    "candidateSpace": candidate_space}

        recovered = 0
        reciprocal_rank = 0.0
        for source, target in relations:
            ranked = await session.run(
                _RANK_BY_RARE_SHARED_NEIGHBOURS,
                concept=source, withheld=target, limit=limit,
            )
            words = [r["word"] async for r in ranked]
            if target in words:
                recovered += 1
                reciprocal_rank += 1.0 / (words.index(target) + 1)

    rate = recovered / len(relations)
    chance = limit / candidate_space
    return {
        "tested": len(relations),
        "recovered": recovered,
        "recoveryRate": round(rate, 4),
        "chanceRate": round(chance, 6),
        "lift": round(rate / chance, 1) if chance else 0.0,
        "meanReciprocalRank": round(reciprocal_rank / len(relations), 4),
        "candidateSpace": candidate_space,
    }
