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


def get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


def _subject_of(token) -> str | None:
    for child in token.children:
        if child.dep_ in ("nsubj", "nsubjpass"):
            return child.lemma_.lower()
    return None


def _object_of(token) -> str | None:
    for child in token.children:
        if child.dep_ in ("dobj", "obj"):
            return child.lemma_.lower()
    # "leads to X" / "results in X" / "depends on X" — object is inside a
    # prepositional phrase (prep -> pobj).
    for child in token.children:
        if child.dep_ == "prep":
            for grandchild in child.children:
                if grandchild.dep_ == "pobj":
                    return grandchild.lemma_.lower()
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
