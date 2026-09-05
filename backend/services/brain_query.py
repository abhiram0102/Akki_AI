"""Query understanding for POST /api/brain/ask — turn a natural question into
a plan of graph operations.

Why this module exists: before it, `/ask` used the raw request string directly
as a Neo4j node key (`body.concept.strip().lower()`), so "why does inflation
happen" became a literal node lookup for that whole sentence, missed, and was
handed verbatim to the source resolver. There was no parsing step to improve —
there was no parsing step at all.

Two deliberate constraints:

1. **No LLM.** The design spec lists "Any LLM in the answer path" as an
   explicit non-goal, and AKKI_FULL_ARCHITECTURE.md says "never asks LLM after
   Phase 1". This module uses only the spaCy pipeline `brain_nlp` already
   loads, so it adds no dependency and no model call.
2. **Same normalizer as the graph writer.** Topics are extracted with
   `brain_nlp._concept_from_token`, the exact function used when writing node
   keys. A term pulled out of a question is therefore spelled identically to
   the node stored when that concept was learned. Using a different normalizer
   here would silently miss nodes that genuinely exist.

Implements step 2 of "Function 7 — Answer Formation" in
AKKI_FULL_ARCHITECTURE.md ("identify concepts in question").
"""
from dataclasses import dataclass

from backend.services import brain_nlp

# Intents, each mapping to graph capability that already exists.
DEFINE = "define"    # "what is X"            -> out-edges + derived links
CAUSE = "cause"      # "why does X happen"    -> IN-edges (what X depends on)
EFFECT = "effect"    # "what does X lead to"  -> out-edges (what X produces)
RELATE = "relate"    # "how do X and Y link"  -> convergence between two concepts
EXPLORE = "explore"  # 3+ concepts            -> multi-origin convergence

# spaCy's Penn-Treebank tags for interrogative words. This is the parser's own
# morphological analysis of the token, not a list of English question words, so
# it costs no hardcoded vocabulary.
_WH_TAGS = {"WDT", "WP", "WP$", "WRB"}

# ── HARDCODED-ASSUMPTION FLAG ────────────────────────────────────────────────
# Project charter: no predefined linguistic rules. This table breaks it.
# Morphology alone cannot separate "why X" from "what X" — spaCy tags both as
# interrogative without saying which one asks for a cause. This is the ONLY
# lexical table in the query path. It is kept deliberately tiny and isolated
# here so it can be replaced by a learned classifier without touching any other
# module. It is the same class of assumption as brain_nlp.FORWARD_CONNECTIVES,
# which is already in-tree, so this adds no new kind of violation — but it is a
# violation and should not be extended.
_WH_INTENT = {
    "why": CAUSE,
    "how": RELATE,
}
# ─────────────────────────────────────────────────────────────────────────────

# Below this many distinct concepts a question is about one thing; at or above
# it, the user is asking how several things relate.
_RELATE_TOPICS = 2
_EXPLORE_TOPICS = 3


@dataclass
class QueryPlan:
    """What the user asked, resolved into concepts the graph can be queried with."""
    intent: str
    topics: list[str]
    raw: str
    wh: str | None = None

    @property
    def primary(self) -> str | None:
        return self.topics[0] if self.topics else None

    @property
    def secondary(self) -> str | None:
        return self.topics[1] if len(self.topics) > 1 else None

    def as_dict(self) -> dict:
        return {"intent": self.intent, "topics": self.topics, "wh": self.wh}


def _expand_with_modifiers(token) -> str | None:
    """Rebuild a multi-word concept from the token's own modifiers.

    spaCy's noun chunker fails on the predicate of a question: in "what is dark
    matter" the only chunk it finds is "what", so the graph writer's normalizer
    falls back to the bare head noun and the query looks up "matter" while the
    article that taught the concept stored "dark matter" — a guaranteed miss on
    a concept the brain genuinely knows.

    The parse still carries the information the chunker dropped: "dark" is an
    adjectival modifier of "matter". Reading those dependency labels rebuilds
    the same phrase the writer would have produced, so this narrows the gap
    between the two normalizers rather than widening it. Structural, not a word
    list — it uses the parser's own labels.
    """
    words = [
        child.lemma_.lower() for child in token.lefts
        if child.dep_ in ("amod", "compound")
        and child.is_alpha and not child.is_stop
        and child.pos_ in brain_nlp._PHRASE_POS
        and len(child.lemma_) >= 3
    ]
    if not words:
        return None
    words.append(token.lemma_.lower())
    return " ".join(words[-brain_nlp._MAX_PHRASE_WORDS:])


def extract_topics(doc) -> list[str]:
    """Concept phrases mentioned in the question, in the order asked.

    Uses the graph writer's own noun-phrase normalizer so these strings match
    stored node keys exactly. Interrogative tokens are excluded: "what" is a
    pronoun spaCy will happily hand back, but it is never a concept.
    """
    topics: list[str] = []
    for token in doc:
        if token.tag_ in _WH_TAGS:
            continue
        concept = brain_nlp._concept_from_token(token)
        # A single-word result may be a chunker failure rather than a
        # single-word concept; recover the modifiers from the parse.
        if concept and " " not in concept:
            expanded = _expand_with_modifiers(token)
            if expanded and " " in expanded:
                concept = expanded
        if concept and concept not in topics:
            topics.append(concept)
    return topics


def _wh_token(doc) -> str | None:
    for token in doc:
        if token.tag_ in _WH_TAGS:
            return token.lemma_.lower()
    return None


def _connective_intent(doc, primary: str | None) -> str | None:
    """Read intent from the DEPENDENCY ROLE the user's concept plays, not from
    word matching.

    `brain_nlp` already knows which verbs run cause->effect (FORWARD) and which
    run dependent->prerequisite (BACKWARD), and it uses that to orient every
    edge it writes. The same tables, applied to the question, say which
    DIRECTION of the graph the user is asking to travel:

      "what causes inflation"      -> inflation is the OBJECT of a forward
                                      connective, so the unknown is upstream:
                                      read IN-edges (CAUSE).
      "what does inflation cause"  -> inflation is the SUBJECT, so the unknown
                                      is downstream: read out-edges (EFFECT).
      "what does inflation require"-> require is BACKWARD, so its subject is
                                      the dependent and the unknown is again
                                      upstream: IN-edges (CAUSE).

    Returns None when no connective verb governs the user's concept.
    """
    if not primary:
        return None
    for token in doc:
        if token.pos_ != "VERB":
            continue
        lemma = token.lemma_.lower()
        forward = lemma in brain_nlp.FORWARD_CONNECTIVES
        backward = lemma in brain_nlp.BACKWARD_CONNECTIVES
        if not (forward or backward):
            continue
        if brain_nlp._object_of(token) == primary:
            return CAUSE if forward else EFFECT
        if brain_nlp._subject_of(token) == primary:
            return EFFECT if forward else CAUSE
    return None


def parse(text: str) -> QueryPlan:
    """Parse a question (or a bare concept) into a QueryPlan.

    A bare concept with no question around it parses to DEFINE on that single
    topic, which is exactly the behaviour `/ask` had before this module — so
    existing callers that post a plain concept string are unaffected.
    """
    raw = (text or "").strip()
    if not raw:
        return QueryPlan(intent=DEFINE, topics=[], raw=raw)

    doc = brain_nlp.get_nlp()(raw)
    topics = extract_topics(doc)
    wh = _wh_token(doc)

    # Fallback for a concept the parser does not recognise as a noun. Rare or
    # technical words ("quasicrystal") get tagged as something else, and the
    # noun-phrase normalizer then returns nothing — which previously left the
    # whole question standing in as the concept, so the brain would answer
    # "I don't know what is quasicrystal". Strip the parts of the question that
    # are grammar rather than subject (interrogatives, auxiliaries, verbs,
    # stopwords) and treat what remains as the thing being asked about.
    if not topics:
        residue = [
            t.lemma_.lower() for t in doc
            if t.tag_ not in _WH_TAGS and t.is_alpha and not t.is_stop
            and t.pos_ not in ("AUX", "VERB", "PART")
        ]
        if residue:
            topics = [" ".join(residue[-brain_nlp._MAX_PHRASE_WORDS:])]
        elif not wh:
            topics = [raw.lower()]

    if len(topics) >= _EXPLORE_TOPICS:
        intent = EXPLORE
    else:
        intent = _connective_intent(doc, topics[0] if topics else None)
        if intent is None and wh in _WH_INTENT:
            intent = _WH_INTENT[wh]
            # "how does X work" is a request for a description, not for a link
            # between two things. Concept count decides, not the word.
            if intent == RELATE and len(topics) < _RELATE_TOPICS:
                intent = DEFINE
        if intent is None:
            intent = RELATE if len(topics) >= _RELATE_TOPICS else DEFINE

    # RELATE needs two endpoints; degrade rather than query with a missing one.
    if intent == RELATE and len(topics) < _RELATE_TOPICS:
        intent = DEFINE

    return QueryPlan(intent=intent, topics=topics, raw=raw, wh=wh)
