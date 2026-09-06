"""One thing, one node -- ATTEMPTED, MEASURED, AND NOT ACHIEVED.

**Do not apply this to a graph.** It is kept because what it rules out is worth
more than another untested idea, and because the retraction below is the most
useful thing in this file.

The problem is real. The graph stores a node per surface form, so `nucleus` and
`nucleus accumben` are separate and everything learned about one is unreachable
from the other. `oxygen` has 32 edges and `dioxygen` has 1.

WHAT WAS CLAIMED, AND WHY IT WAS WRONG
---------------------------------------
An earlier version of this file reported that merging semantic duplicates
raised prediction from 36.5x chance to 109.2x -- roughly tripling it -- with a
random-merge control at 36.9x that appeared to rule out artifacts.

That claim is WITHDRAWN. Inspecting what it actually merged on the live graph:

    'new'  <- additional training, algebraic geometry, analysis, antivirus software
    'gas'  <- acetic acid, amino acid, arachidonic acid, atom
    'gust' <- chemical energy, efficiency, electrical energy
    'new': 2 edges -> 5,172 edges

Union-find transitivity chains a~b and b~c into a==c until unrelated concepts
share one node. Predicting a node joined to everything is trivial, which is
where the lift came from. Concepts with enough edges to answer well went DOWN,
3,503 -> 3,024.

The aggregate metric AND its control both missed this. Only looking at the
output caught it. That is the lesson: a controlled number is not a substitute
for reading what the code produced.

THREE RULES TRIED, ALL UNSAFE OR TRIVIAL
-----------------------------------------
1. Cosine + transitivity: blobs, as above.
2. Cosine + mutual-nearest, no transitivity: 1,209 clean-looking pairs, but on
   single words it merges ANTONYMS -- `north`/`south`, `east`/`west`,
   `november`/`september`, `democrats`/`republicans`. Distributional vectors
   place opposites together because opposites occur in identical contexts. This
   is a property of the method, not a threshold to tune.
3. Lexical permutation and containment: safe (zero antonyms, no blobs) but
   yields six pairs on 12,198 concepts, and half are wrong anyway --
   `time constant`/`constant time`, `toll road`/`road toll` and
   `ground coffee`/`coffee ground` are distinct concepts that happen to be
   anagrams.

WHAT WOULD ACTUALLY BE NEEDED
------------------------------
Evidence that two forms are the same thing must come from how they BEHAVE in
the graph -- whether they take the same neighbours, in the same roles -- rather
than from how they look or where a language model puts them. That is a real
piece of work and it is not done here.

`duplicate_pairs` and `resolve` remain because they are the measured negative
result. Their output must be INSPECTED, never applied wholesale.
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
