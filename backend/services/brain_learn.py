"""AKKI Brain Engine — shared graph-write core.

Extracted from `backend.brain_crawler.crawl_one_page` so on-demand learning
(triggered by a user's query) and the background crawler write concepts and
edges to Neo4j through one code path instead of two copies drifting apart.
"""
import os
from collections import Counter
from urllib.parse import quote_plus

from backend.services.brain_fetchers import fetch_structure
from backend.services import brain_meaning
from backend.services.brain_nlp import extract_dependencies
from backend.services.brain_stats_math import log_likelihood_ratio

# Wikipedia (and many sites) return 403 to the default httpx User-Agent; a
# descriptive browser-like UA is required to fetch article content. Kept in
# sync with backend/brain_crawler.py's client headers — shared here so other
# on-demand callers (e.g. /api/brain/ask) use the same identity.
UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AKKI-Brain/1.0; +knowledge-graph research crawler)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Where to look when the brain is asked about something it has never read.
#
# This is the one place a source has to be named, and it is configuration
# rather than logic: `{term}` is filled in and the result is READ, not parsed
# against any site's API. Point it at a different search page and nothing else
# changes. What used to be here was the MediaWiki opensearch API — a
# site-specific JSON contract — with a fallback that guessed a URL by
# title-casing the term and joining it with underscores, which is Wikipedia's
# address convention applied as if it were universal.
_SEARCH_URL_TEMPLATE = os.getenv(
    "BRAIN_SEARCH_URL", "https://en.wikipedia.org/w/index.php?search={term}"
)


async def resolve_source(term: str, client) -> str | None:
    """Find an address to read about `term`, by reading a search page.

    The search results page is fetched and handed to `brain_discovery`, which
    works out its structure and hands back the references it offers. The first
    of those is the brain's entry point. No response format is assumed: this
    is the same discovery used on every other page, pointed at a page whose
    references happen to be search results.

    Returns None when nothing readable came back, so the caller can report not
    knowing rather than proceed with a guessed address.
    """
    from backend.services.brain_fetchers import fetch_structure

    search_url = _SEARCH_URL_TEMPLATE.format(term=quote_plus(term.strip()))
    try:
        # Every reference, not just the dominant shape: on a search page the
        # results are the minority and the site's navigation is the majority.
        structure = await fetch_structure(search_url, client, narrow_to_shape=False)
    except Exception:
        return None
    references = structure.get("references") or [
        {"url": u, "text": ""} for u in (structure.get("links") or [])
    ]
    if not references:
        return None

    # Take the reference that best matches what was asked for, not whichever
    # appeared first. A search page leads with its own navigation, so the first
    # reference on it is reliably the wrong one. Matching uses the words the
    # document attached to each reference and the words in the address itself,
    # both of which are evidence the document supplied.
    wanted = {w for w in term.lower().split() if w}

    def score(reference: dict) -> int:
        haystack = (reference.get("text", "") + " " + reference["url"]).lower()
        return sum(1 for word in wanted if word in haystack)

    best = max(references, key=score)
    return best["url"] if score(best) else references[0]["url"]


async def learn_concept(term: str, client, neo4j_driver, follow_links: int = 1) -> dict:
    """Resolve `term` to a Wikipedia article, fetch it (and optionally its top
    `follow_links` linked articles), extract concept/edge pairs via dependency
    parsing, and write them into the graph in one call to `apply_to_graph`.

    Returns `{"term", "resolved_title", "new_concepts", "new_edges", "sources"}`.
    """
    resolved_url = await resolve_source(term, client)
    if not resolved_url:
        return {"term": term, "resolved_title": None, "new_concepts": 0,
                "new_edges": 0, "sources": []}

    urls = [resolved_url]

    word_freq: Counter = Counter()
    edge_counts: Counter = Counter()
    sources: list[str] = []

    url = urls[0]
    structure = await fetch_structure(url, client)
    links = structure["links"]
    sources.append(url)
    _accumulate(structure["sentences"], word_freq, edge_counts)

    for link_url in links[:follow_links]:
        try:
            linked = await fetch_structure(link_url, client)
        except Exception:
            continue
        sources.append(link_url)
        _accumulate(linked["sentences"], word_freq, edge_counts)

    anchor = term.strip().lower()
    if anchor and len(anchor) >= 3 and word_freq:
        # Topical anchor: an encyclopedia article about X evidences that X is
        # associated with the concepts it most prominently discusses. Guarantees
        # the queried term is itself a node and is answerable after learning.
        word_freq[anchor] += 1  # ensure the anchor node exists
        top = [w for w, _ in word_freq.most_common(25) if w != anchor][:20]
        for w in top:
            edge_counts[(anchor, w)] += word_freq[w]  # weight by article salience

    async with neo4j_driver.session() as session:
        result = await apply_to_graph(session, word_freq, edge_counts)

    return {
        "term": term,
        "resolved_title": resolved_url,
        "new_concepts": result["new_concepts"],
        "new_edges": result["new_edges"],
        "sources": sources,
    }


def _accumulate(sentences: list[str], word_freq: Counter, edge_counts: Counter) -> None:
    """Extract relationships from sentences ALREADY split at boundaries this
    document taught us.

    This used to take raw text and split it on ". ", which is a hardcoded
    assumption about how sentences end — and one that silently produced
    nothing on a document that ends them any other way. Boundaries now come
    from `brain_discovery`, so the caller passes statements rather than prose.

    Minimum 3 words is the grammatical floor for extract_dependencies to find
    a subject-verb-object triple ("Fire causes heat" is exactly 3).
    """
    sentences = [s for s in sentences if len(s.split()) >= 3]
    pairs: list[tuple[str, str]] = []
    # Which sentence each concept was found in. This is what the meaning layer
    # clusters: a concept's senses are discovered from the company it keeps,
    # so the context has to be the exact sentence the concept was extracted
    # from rather than the page as a whole.
    contexts: dict[str, list[str]] = {}

    for sentence in sentences[:200]:  # cap per-page NLP cost, matches the crawler
        try:
            found = extract_dependencies(sentence)
        except Exception:
            continue
        pairs.extend(found)
        for cause, effect in found:
            contexts.setdefault(cause, []).append(sentence)
            contexts.setdefault(effect, []).append(sentence)

    for cause, effect in pairs:
        word_freq[cause] += 1
        word_freq[effect] += 1
        edge_counts[(cause, effect)] += 1

    # Recording meaning must never be able to break a read that succeeded.
    for concept, sentences_for_concept in contexts.items():
        brain_meaning.record_contexts(concept, sentences_for_concept)


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
