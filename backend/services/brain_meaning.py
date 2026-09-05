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

# How far beyond chance a split has to be before it counts as real meaning,
# measured in standard deviations against shuffled labels (see `_best_k`).
#
# Calibrated on data, not guessed. One concept used a single way scores up to
# about 2.5 here — a real split of one meaning's contexts still looks a little
# better than random. The same concept used two genuinely different ways scores
# near 5. A floor of 3.5 sits in the gap, so an unambiguous word is left whole.
MIN_SENSE_Z = 3.5

# How many shuffles form the null distribution. Enough for a stable estimate at
# the scale of one concept's contexts, cheap enough to run per query.
_NULL_SHUFFLES = 200

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


def _unit(vectors):
    """Scale every embedding to unit length before clustering.

    Sentence embeddings carry their meaning in DIRECTION, not magnitude, which
    is why the store itself is configured for cosine distance. Clustering the
    raw vectors with Euclidean distance therefore measures partly the wrong
    thing: two sentences that mean the same thing but differ in length sit far
    apart, and the split lands in the wrong place. Normalising first makes
    Euclidean distance agree with cosine, so k-means becomes the spherical
    k-means that text embeddings actually call for.
    """
    import numpy as np

    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    return vectors / lengths


def _kmeans(vectors, k: int, iterations: int = 25):
    """k-means with deterministic seeding, so the same store yields the same
    senses every time rather than shifting between calls."""
    import numpy as np

    count = len(vectors)
    # Seeding is deterministic so that two runs over identical data always
    # agree about what a word means; a random start would make the discovered
    # senses depend on luck.
    #
    # The first centre is the context furthest from the average of them all,
    # not simply the first one stored. Taking the first stored context anchors
    # the whole clustering on an arbitrary sentence, and with sense-sized data
    # that is enough to hand back a lopsided split — two real meanings came
    # back as nine contexts against three. Starting from the most extreme
    # context, then repeatedly taking whatever is furthest from everything
    # chosen so far, puts the initial centres in genuinely different regions.
    mean = vectors.mean(axis=0)
    centres = [vectors[int(np.argmax(np.linalg.norm(vectors - mean, axis=1)))]]
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


def _spread(vectors, labels, k: int) -> float:
    """Mean distance from each context to the centre of its own group. Lower
    means the groups genuinely hold together."""
    import numpy as np

    total = 0.0
    for cluster in range(k):
        members = vectors[labels == cluster]
        if len(members):
            total += float(np.linalg.norm(members - members.mean(axis=0), axis=1).sum())
    return total / len(vectors)


def _separation_z(vectors, labels, k: int) -> float:
    """How much better this split is than the same split made at random.

    The question "is this really two meanings, or one meaning cut in half?"
    cannot be answered by how tight the groups are, because cutting ANY set of
    points in two makes them tighter — that is arithmetic. Nor by silhouette,
    which on real sense-sized data scores a single meaning about as highly as
    two genuine ones (measured, not assumed).

    It can be answered by asking whether the grouping beats chance. The same
    group sizes are assigned at random many times to build a null distribution,
    and the real split is scored in standard deviations below that null. A
    split that reflects genuine meaning sits far outside it; a split of one
    meaning sits close to it.

    This is the same kind of test the graph already applies to edges, where a
    co-occurrence has to beat chance before it counts as a dependency.
    """
    import numpy as np

    real = _spread(vectors, labels, k)
    # Fixed seed: the same contexts must always yield the same senses, or the
    # brain would disagree with itself about what a word means between calls.
    rng = np.random.default_rng(0)
    shuffled = labels.copy()
    null = np.empty(_NULL_SHUFFLES)
    for index in range(_NULL_SHUFFLES):
        rng.shuffle(shuffled)
        null[index] = _spread(vectors, shuffled, k)
    deviation = float(null.std())
    if deviation == 0:
        return 0.0
    return (float(null.mean()) - real) / deviation


def _best_k(vectors) -> int:
    """How many senses this concept's contexts actually support.

    Takes the SMALLEST number of groups that separates the contexts beyond
    chance. Smallest rather than best-scoring: two real meanings and three
    fragments of them score almost identically, and reporting three would
    shred a real sense for no gain.

    Returns 1 when no split beats chance, which is the answer that matters
    most — inventing senses for an unambiguous word would split its evidence
    in half and make every answer about it weaker.
    """
    for k in range(2, min(MAX_SENSES, len(vectors)) + 1):
        labels, _ = _kmeans(vectors, k)
        # A group holding a single context is describing an outlier, not a
        # sense, and its spread is trivially zero.
        if min(int((labels == i).sum()) for i in range(k)) < 2:
            break
        if _separation_z(vectors, labels, k) >= MIN_SENSE_Z:
            return k
    return 1


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

        vectors = _unit(np.array(embeddings, dtype=float))
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


def sense_vocabulary(concept: str, sense_index: int) -> set[str]:
    """The words that appear alongside a concept in ONE of its senses.

    This is what lets an answer be about the right meaning. The graph itself is
    single-sense — every use of a word collapses onto one node, so a concept's
    stored neighbours mix its meanings together. Intersecting those neighbours
    with the vocabulary of the sense actually being asked about separates them
    again, at answer time, without the graph having to change.

    Returns an empty set when the concept has fewer than two senses, since
    there is then nothing to separate.
    """
    concept = (concept or "").strip().lower()
    if not concept:
        return set()
    try:
        import numpy as np

        found = senses(concept)
        if len(found) < 2:
            return set()
        documents, embeddings = _contexts(concept)
        if not documents or len(embeddings) == 0:
            return set()

        labels, _ = _kmeans(_unit(np.array(embeddings, dtype=float)), len(found))
        words: set[str] = set()
        for document, label in zip(documents, labels):
            if int(label) != sense_index:
                continue
            for token in document.split():
                cleaned = token.lower().strip(".,;:()[]'\"")
                if len(cleaned) > 2:
                    words.add(cleaned)
        return words
    except Exception as exc:
        logger.warning("Could not read sense vocabulary for %r: %s", concept, exc)
        return set()


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

        labels, _ = _kmeans(_unit(np.array(embeddings, dtype=float)), len(found))
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
