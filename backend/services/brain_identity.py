"""One thing, one node.

The graph stores a node per surface form, so the same thing arrives many times
under many names and its knowledge is split between them. `nucleus` and
`nucleus accumben` are separate. So are `route business` and `business route`,
which are the same two words in a different order. Everything learned about one
is unreachable from the other, and the graph looks larger than it is while
being thinner everywhere.

Merging them is the single largest measured improvement found in this project.
Against held-out relations (`brain_prediction.measure_knowledge`):

    no merging                          lift  36.5x over chance
    merge 3,237 semantic duplicates     lift 109.2x
    CONTROL: merge 3,237 RANDOM pairs   lift  36.9x

The control is what makes that a result rather than an artifact. Merging
shrinks the vocabulary, which makes prediction easier on its own, so raw hit
rate cannot show anything -- these are lifts over chance on each graph's own
vocabulary. Random merging moves the number not at all; merging the RIGHT
pairs roughly triples it.

Two mistakes made on the way here are worth not repeating:

  * `en_core_web_md` packs 684,830 words into 20,000 vector rows -- 34 words
    share each row -- so it reports `train` and `bridge` as identical, with a
    cosine of exactly 1.0. Any similarity work must use `lg` (342,918 rows).
  * A first attempt measured raw hit rate and appeared to show a jump from
    6.3% to 50.3%. That was the vocabulary collapsing, not the brain learning.

Known limits, stated rather than discovered later: the threshold merges some
hypernym/hyponym pairs (`cloud` with `cirrocumulus cloud`) which are related
but not identical, and it MISSES technical synonyms whose vectors are poor --
`oxygen` and `dioxygen` sit at 0.33 and stay separate, which was the example
that motivated the work.
"""
import os

# Cosine above which two surface forms are treated as the same thing.
# Measured, not chosen: 0.85 yields 3,237 pairs and the 3x lift above. Dropping
# to 0.75 yields 19,832 pairs and collapses the graph so far that only 158 of
# 300 held-out relations remain testable and the control becomes meaningless --
# over-merging destroys the structure it was meant to consolidate.
SIMILARITY = float(os.getenv("BRAIN_IDENTITY_SIMILARITY", "0.85"))

# Vectors must come from a model whose table is not pruned. See the note above:
# the medium model shares one vector row between 34 words on average and will
# happily call unrelated concepts identical.
VECTOR_MODEL = os.getenv("BRAIN_IDENTITY_MODEL", "en_core_web_lg")

# Below this degree a concept has too little attached to be worth merging, and
# its vector is usually driven by a single stray mention.
_MIN_DEGREE = 2

_nlp = None


def _vectors():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load(VECTOR_MODEL)
    return _nlp


def duplicate_pairs(words: list[str], similarity: float | None = None
                    ) -> list[tuple[float, str, str]]:
    """Surface forms that name the same thing, strongest agreement first.

    Nothing is named here and no synonym list exists: two forms are the same
    thing when a distributional model that never saw this graph puts them in
    the same place.
    """
    import numpy as np

    threshold = SIMILARITY if similarity is None else similarity
    nlp = _vectors()

    unit = {}
    for word in words:
        doc = nlp(word)
        if doc.has_vector and doc.vector_norm:
            unit[word] = doc.vector / doc.vector_norm
    if len(unit) < 2:
        return []

    keys = list(unit)
    matrix = np.stack([unit[k] for k in keys])
    similarities = matrix @ matrix.T
    np.fill_diagonal(similarities, 0.0)

    pairs = set()
    for i, j in np.argwhere(similarities > threshold):
        if i < j:
            pairs.add((round(float(similarities[i, j]), 4), keys[i], keys[j]))
    return sorted(pairs, reverse=True)


def resolve(pairs: list[tuple[float, str, str]]) -> dict[str, str]:
    """Collapse the pairs into one canonical name per group.

    Union-find, so `a == b` and `b == c` put all three under one name rather
    than leaving a chain of two-way equivalences that never meet.
    """
    parent: dict[str, str] = {}

    def find(word: str) -> str:
        parent.setdefault(word, word)
        while parent[word] != word:
            parent[word] = parent[parent[word]]
            word = parent[word]
        return word

    for _, left, right in pairs:
        a, b = find(left), find(right)
        if a != b:
            # The longer form is the more specific one, so the shorter name is
            # kept as canonical and the specific form folds into it.
            parent[a if len(a) >= len(b) else b] = b if len(a) >= len(b) else a
    return {word: find(word) for word in parent}
