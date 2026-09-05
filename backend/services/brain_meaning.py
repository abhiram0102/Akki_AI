"""The meaning layer — word senses discovered from context.

Function 7 step 3 in AKKI_FULL_ARCHITECTURE.md is "determine which meaning
cluster is being asked about (which context — philosophical fire? physical
fire? emotional fire?)". Until now the graph was single-sense: every use of a
word collapsed onto one node, so the physical and the philosophical senses of
a concept shared their neighbours and contaminated each other's answers.

How a sense is found
--------------------
Nothing here defines what any word means. Every sentence the brain reads that
mentions a concept is kept as a context for it. Those contexts are embedded and
then clustered, and each cluster IS a sense: a group of uses that resemble one
another more than they resemble the rest. A concept used one way yields one
cluster; a concept used in two unrelated fields yields two. The number of
senses is decided by the spread of the data, not fixed in advance and not
listed anywhere.

Each sense is labelled with the words that distinguish it from the concept's
other senses, so a sense can be named without a dictionary: the label is
whatever those contexts say and the others do not.

Storage
-------
ChromaDB, which the project already declared as a dependency but had never
installed or used, holds the contexts and their embeddings. It is a real local
store with a real local embedding model — no API key, no network at query time,
which the project's "zero live internet at answer time" constraint requires.
The graph stays in Neo4j; this sits beside it and answers a different question.

Clustering is k-means over the stored embeddings, with k chosen by testing
whether splitting actually separates the contexts (see `_best_k`). It runs on
numpy, which arrives with ChromaDB, rather than pulling in a second scientific
stack for one algorithm.
"""
import logging
import os
import threading

logger = logging.getLogger(__name__)

# Where the meaning store lives. A directory rather than a server: the vector
# side has no availability requirement the graph does not already impose.
PERSIST_PATH = os.getenv("BRAIN_MEANING_PATH", "./data/brain_meaning")
COLLECTION = "concept_contexts"

# Below this many contexts a concept has not been seen enough for a split to
# mean anything; it is reported as a single sense.
MIN_CONTEXTS_FOR_SENSES = 6

# The most senses to look for. A word with more genuinely distinct uses than
# this is rare, and every extra candidate costs a clustering pass.
MAX_SENSES = 4

# A split is only accepted when it tightens the contexts by at least this much
# relative to leaving them together. Without a floor, k-means will always
# "find" clusters in noise.
MIN_SPLIT_IMPROVEMENT = 0.12

# Words this common carry no sense information; they are dropped from labels.
# Derived from the contexts themselves rather than a stopword list: a word that
# appears in most of a concept's senses cannot distinguish between them.
_LABEL_UBIQUITY = 0.6
_LABEL_TERMS = 4

_client = None
_collection = None
_lock = threading.Lock()


def _get_collection():
    """Open the meaning store, creating it if this is the first use."""
    global _client, _collection
    if _collection is not None:
        return _collection
    with _lock:
        if _collection is None:
            import chromadb

            _client = chromadb.PersistentClient(path=PERSIST_PATH)
            _collection = _client.get_or_create_collection(
                name=COLLECTION, metadata={"hnsw:space": "cosine"}
            )
    return _collection


def reset_for_tests(collection=None) -> None:
    """Point the module at a supplied collection, or forget the open one."""
    global _client, _collection
    _collection = collection
    if collection is None:
        _client = None


def record_contexts(concept: str, sentences: list[str]) -> int:
    """Remember the sentences a concept was used in.

    Called as the brain reads. Each context is keyed by concept and content, so
    re-reading the same sentence does not inflate a sense with duplicates of
    one use — a concept mentioned once in a page that gets crawled twice must
    not look like a concept with two independent uses.

    Returns how many contexts were stored. Never raises: failing to record a
    context must not fail the read that produced it.
    """
    concept = (concept or "").strip().lower()
    usable = [s.strip() for s in sentences if s and len(s.split()) >= 3]
    if not concept or not usable:
        return 0
    try:
        collection = _get_collection()
        ids = [f"{concept}::{abs(hash(s))}" for s in usable]
        collection.upsert(
            ids=ids,
            documents=usable,
            metadatas=[{"concept": concept} for _ in usable],
        )
        return len(usable)
    except Exception as exc:
        logger.warning("Could not record contexts for %r: %s", concept, exc)
        return 0


def _contexts(concept: str) -> tuple[list[str], list]:
    """Every stored context for a concept, with its embedding."""
    collection = _get_collection()
    got = collection.get(
        where={"concept": concept}, include=["documents", "embeddings"]
    )
    documents = got.get("documents") or []
    embeddings = got.get("embeddings")
    if embeddings is None or len(embeddings) == 0:
        return documents, []
    return documents, embeddings


def _kmeans(vectors, k: int, iterations: int = 25):
    """k-means with deterministic seeding, so the same store yields the same
    senses every time rather than shifting between calls."""
    import numpy as np

    count = len(vectors)
    # Seed with the points furthest apart rather than at random: a random start
    # makes the discovered senses depend on luck, and two runs over identical
    # data would disagree about what a word means.
    centres = [vectors[0]]
    for _ in range(1, k):
        distances = np.min(
            np.stack([np.linalg.norm(vectors - c, axis=1) for c in centres]), axis=0
        )
        centres.append(vectors[int(np.argmax(distances))])
    centres = np.stack(centres)

    labels = np.zeros(count, dtype=int)
    for _ in range(iterations):
        distances = np.stack([np.linalg.norm(vectors - c, axis=1) for c in centres])
        new_labels = np.argmin(distances, axis=0)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for index in range(k):
            members = vectors[labels == index]
            if len(members):
                centres[index] = members.mean(axis=0)
    return labels, centres


def _spread(vectors, labels, centres) -> float:
    """Mean distance from each context to the centre of its own group. Lower
    means the groups genuinely hold together."""
    import numpy as np

    return float(
        np.mean([np.linalg.norm(v - centres[labels[i]]) for i, v in enumerate(vectors)])
    )


def _best_k(vectors) -> int:
    """How many senses this concept's contexts actually support.

    Tries each candidate split and keeps the largest one that tightens the
    contexts by a real margin over not splitting at all. A concept used a
    single way never clears the margin and stays at one sense, which is the
    answer that matters most: inventing senses for an unambiguous word would
    fragment the graph for nothing.
    """
    import numpy as np

    baseline = _spread(vectors, np.zeros(len(vectors), dtype=int),
                       np.stack([vectors.mean(axis=0)]))
    if baseline == 0:
        return 1

    best = 1
    for k in range(2, min(MAX_SENSES, len(vectors)) + 1):
        labels, centres = _kmeans(vectors, k)
        # A split that leaves a group with a single context is describing an
        # outlier, not a sense.
        if min(int((labels == i).sum()) for i in range(k)) < 2:
            continue
        improvement = (baseline - _spread(vectors, labels, centres)) / baseline
        if improvement >= MIN_SPLIT_IMPROVEMENT:
            best = k
    return best


def _label(own: list[str], other: list[str]) -> list[str]:
    """Name a sense by what its contexts say that the others do not.

    No dictionary and no stopword list: a word is uninformative here precisely
    when it also turns up across the concept's other senses, which is measured
    rather than assumed.
    """
    from collections import Counter

    own_counts: Counter = Counter()
    for sentence in own:
        own_counts.update({w.lower().strip(".,;:()") for w in sentence.split() if len(w) > 3})
    other_counts: Counter = Counter()
    for sentence in other:
        other_counts.update({w.lower().strip(".,;:()") for w in sentence.split() if len(w) > 3})

    total_other = max(1, len(other))
    distinctive = [
        (word, count) for word, count in own_counts.items()
        if other_counts.get(word, 0) / total_other < _LABEL_UBIQUITY
    ]
    distinctive.sort(key=lambda pair: -pair[1])
    return [word for word, _ in distinctive[:_LABEL_TERMS]]


def senses(concept: str) -> list[dict]:
    """The distinct ways this concept has been used, discovered from context.

    Returns one entry per sense with the words that distinguish it, how many
    contexts support it, and one real example. A concept with too few contexts
    to judge comes back as a single sense rather than a guess.
    """
    concept = (concept or "").strip().lower()
    if not concept:
        return []
    try:
        import numpy as np

        documents, embeddings = _contexts(concept)
        if not documents:
            return []
        if len(documents) < MIN_CONTEXTS_FOR_SENSES or len(embeddings) == 0:
            return [{
                "sense": 0, "label": _label(documents, []),
                "contextCount": len(documents), "example": documents[0],
            }]

        vectors = np.array(embeddings, dtype=float)
        k = _best_k(vectors)
        if k == 1:
            return [{
                "sense": 0, "label": _label(documents, []),
                "contextCount": len(documents), "example": documents[0],
            }]

        labels, _ = _kmeans(vectors, k)
        out = []
        for index in range(k):
            own = [d for d, l in zip(documents, labels) if l == index]
            other = [d for d, l in zip(documents, labels) if l != index]
            if not own:
                continue
            out.append({
                "sense": index, "label": _label(own, other),
                "contextCount": len(own), "example": own[0],
            })
        out.sort(key=lambda s: -s["contextCount"])
        return out
    except Exception as exc:
        logger.warning("Could not compute senses for %r: %s", concept, exc)
        return []


def disambiguate(concept: str, query: str) -> dict | None:
    """Which sense of `concept` a question is asking about.

    The question is matched against the concept's stored contexts, and the
    sense holding the nearest ones wins. This is Function 7 step 3: asking
    about fire alongside heat and fuel reaches the physical sense, while asking
    about it alongside passion reaches another, without either being defined
    anywhere.

    Returns None when the concept has only one known sense, so a caller can
    skip the distinction entirely rather than handle a meaningless answer.
    """
    concept = (concept or "").strip().lower()
    if not concept or not (query or "").strip():
        return None
    try:
        found = senses(concept)
        if len(found) < 2:
            return None

        collection = _get_collection()
        nearest = collection.query(
            query_texts=[query], n_results=5, where={"concept": concept},
            include=["documents"],
        )
        matched = (nearest.get("documents") or [[]])[0]
        if not matched:
            return None

        # Each retrieved context votes for the sense whose examples it appears
        # among. Voting over several neighbours rather than trusting the single
        # closest keeps one atypical sentence from deciding the meaning.
        scores = {sense["sense"]: 0 for sense in found}
        documents, embeddings = _contexts(concept)
        if not documents or len(embeddings) == 0:
            return None
        import numpy as np

        labels, _ = _kmeans(np.array(embeddings, dtype=float), len(found))
        membership = {doc: int(label) for doc, label in zip(documents, labels)}
        for document in matched:
            sense_index = membership.get(document)
            if sense_index in scores:
                scores[sense_index] += 1

        best_index = max(scores, key=lambda i: scores[i])
        if scores[best_index] == 0:
            return None
        for sense in found:
            if sense["sense"] == best_index:
                return {**sense, "matchedContexts": scores[best_index]}
        return None
    except Exception as exc:
        logger.warning("Could not disambiguate %r: %s", concept, exc)
        return None
