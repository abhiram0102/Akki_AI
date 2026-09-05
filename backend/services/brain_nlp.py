"""Dependency-parse-based relationship extraction for the Brain Engine.

Replaces the original brain/ prototype's regex keyword matching ("split the
sentence after the string 'leads to'") with real subject/verb/object
structure from spaCy's dependency parser.
"""
import spacy

_NLP = None

# Verb lemmas where the SUBJECT is the cause and the OBJECT is the effect.
FORWARD_CONNECTIVES = {"cause", "lead", "produce", "create", "enable", "trigger", "result"}

# Verb lemmas where the SUBJECT is the effect and the OBJECT is the cause
# (the thing needed/depended upon).
BACKWARD_CONNECTIVES = {"require", "need", "depend", "rely", "stem"}


# Only nouns and proper nouns anchor a concept. This filters out function
# words (pronouns like "you"/"it"/"that", determiners, auxiliaries) that spaCy
# legitimately attaches as the nsubj/dobj/pobj of a connective verb but which
# are noise as graph concepts.
_CONTENT_POS = {"NOUN", "PROPN"}
# Content POS kept as modifiers inside a multi-word concept phrase.
_PHRASE_POS = {"NOUN", "PROPN", "ADJ"}
# Max words in a multi-word concept (head noun + up to 2 modifiers). Keeps
# "machine learning" / "sql injection" intact without fragmenting the graph
# into long, near-unique phrases.
_MAX_PHRASE_WORDS = 3


def get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


def _concept_lemma(token) -> str | None:
    """Single-token concept: the token's lowercased lemma if it is a content
    noun/proper-noun of length >= 3, else None (fallback when no noun phrase)."""
    if token.is_stop or not token.is_alpha or len(token.lemma_) < 3:
        return None
    if token.pos_ not in _CONTENT_POS:
        return None
    return token.lemma_.lower()


def _concept_from_token(token) -> str | None:
    """Expand a token to the multi-word noun phrase it heads/belongs to, so
    "machine learning" is one concept rather than "machine" + "learning".

    Finds the spaCy noun chunk containing the token, keeps its content words
    (nouns/proper-nouns/adjectives, no stopwords/determiners), and returns the
    last few (head noun + nearest modifiers) as a normalized lowercase phrase.
    Falls back to the single-token lemma when there's no usable noun chunk.
    """
    chunk = None
    for nc in token.doc.noun_chunks:
        if nc.start <= token.i < nc.end:
            chunk = nc
            break
    if chunk is not None:
        words = [
            t.lemma_.lower() for t in chunk
            if not t.is_stop and t.is_alpha and t.pos_ in _PHRASE_POS and len(t.lemma_) >= 3
        ]
        # Require a genuine noun/proper-noun head somewhere in the kept words.
        has_noun_head = any(t.pos_ in _CONTENT_POS for t in chunk if t.lemma_.lower() in words)
        if words and has_noun_head:
            return " ".join(words[-_MAX_PHRASE_WORDS:])
    return _concept_lemma(token)


def _subject_of(token) -> str | None:
    for child in token.children:
        if child.dep_ in ("nsubj", "nsubjpass"):
            return _concept_from_token(child)
    return None


def _object_of(token) -> str | None:
    for child in token.children:
        if child.dep_ in ("dobj", "obj"):
            return _concept_from_token(child)
    # "leads to X" / "results in X" / "depends on X" — object is inside a
    # prepositional phrase (prep -> pobj).
    for child in token.children:
        if child.dep_ == "prep":
            for grandchild in child.children:
                if grandchild.dep_ == "pobj":
                    return _concept_from_token(grandchild)
    return None


def extract_dependencies(sentence: str) -> list[tuple[str, str]]:
    """Return a list of (cause, effect) pairs found in the sentence."""
    doc = get_nlp()(sentence)
    pairs: list[tuple[str, str]] = []

    for token in doc:
        lemma = token.lemma_.lower()

        if lemma in FORWARD_CONNECTIVES:
            subject = _subject_of(token)
            obj = _object_of(token)
            if subject and obj:
                pairs.append((subject, obj))

        elif lemma in BACKWARD_CONNECTIVES:
            subject = _subject_of(token)
            obj = _object_of(token)
            if subject and obj:
                pairs.append((obj, subject))

    return pairs
