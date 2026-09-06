"""Dependency-parse-based relationship extraction for the Brain Engine.

Replaces the original brain/ prototype's regex keyword matching ("split the
sentence after the string 'leads to'") with real subject/verb/object
structure from spaCy's dependency parser.
"""
import os

import spacy

_NLP = None

# Verb lemmas where the SUBJECT is the cause and the OBJECT is the effect.
FORWARD_CONNECTIVES = {"cause", "lead", "produce", "create", "enable", "trigger", "result"}

# Verb lemmas where the SUBJECT is the effect and the OBJECT is the cause
# (the thing needed/depended upon).
BACKWARD_CONNECTIVES = {"require", "need", "depend", "rely", "stem"}

# Light/copular/auxiliary verbs that carry no real relationship — excluded
# from the general subject→object extraction so the graph isn't flooded with
# "X is Y" / "X has Y" noise.
_SKIP_VERBS = {
    "be", "have", "do", "seem", "become", "appear", "get", "make", "let",
    "say", "tell", "call", "use", "include", "involve", "mean", "remain",
}


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

# Loanword plurals where spaCy's morphologically correct classical singular
# is rare or archaic in ordinary technical prose, or denotes a different
# sense entirely ("media" -> "medium" collapses "the media"/"social media"
# into the unrelated sense of a physical/artistic medium). Measured against
# ~40 candidate irregular plurals over realistic sentences (see
# docs/evaluation-log.md): most loanword plurals (matrix/matrices,
# index/indices, thesis/theses, virus/viruses, child/children, ...) are
# lemmatised correctly and consolidating them onto one singular node is the
# *desired* behaviour, not a bug. Only these five measurably misfire.
#
# Keyed on the SURFACE word the writer used, not on the lemma spaCy assigns,
# so a genuine singular use ("a growth medium", "one datum point") is left
# untouched -- only the plural spelling itself is pinned to its own surface
# form as the concept key. This is a hardcoded lexical exception list, the
# same class already flagged for FORWARD_CONNECTIVES/BACKWARD_CONNECTIVES
# below: a curated table rather than structure discovered from the bytes.
_IRREGULAR_PLURAL_SURFACE = {"data", "media", "criteria", "phenomena", "trivia"}


def _normalized_lemma(token) -> str:
    """The lemma to use as (part of) a concept key.

    Almost always spaCy's own lemma. Overridden only for
    `_IRREGULAR_PLURAL_SURFACE`, so the same word always normalises to the
    same key for both the writer and the query path.
    """
    surface = token.text.lower()
    if surface in _IRREGULAR_PLURAL_SURFACE:
        return surface
    return token.lemma_.lower()


# Which parser model to load. Configurable so that changing it is a setting
# rather than a code change plus two Dockerfile edits.
#
# The default stays on the SMALL model, and that is a measured decision rather
# than an unexamined default. All three models were compared on the stored
# corpus and on the sampled real-text gold set (docs/evaluation-log.md):
#
#   model  relations  real-text precision  real-text recall  peak RSS
#   sm           149                0.500             1.000     136MB
#   md           154                0.571             1.000     341MB
#   lg           156                0.444             1.000     710MB
#
# The large model scores best on the hand-written cases and WORST on real
# crawled text, which is exactly what a fifteen-case hand-written set is prone
# to hide: it was better at the sentence shapes someone thought to write down
# and worse at the ones the web actually produces. It also costs 5.2x the
# memory, in a request path, with a second copy in the crawler.
#
# The spread between all three is within the noise of a 45-sentence sample, so
# no switch is justified. What the numbers do say clearly is that recall is
# already saturated at 1.000 everywhere and PRECISION is the binding
# constraint — and precision is limited by fragments arriving from the
# discovery layer, which no parser model fixes.
MODEL_NAME = os.getenv("BRAIN_SPACY_MODEL", "en_core_web_sm")


def get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load(MODEL_NAME)
    return _NLP


def _concept_lemma(token) -> str | None:
    """Single-token concept: the token's normalized lemma if it is a content
    noun/proper-noun of length >= 3, else None (fallback when no noun phrase)."""
    if token.is_stop or not token.is_alpha or len(token.lemma_) < 3:
        return None
    if token.pos_ not in _CONTENT_POS:
        return None
    return _normalized_lemma(token)


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
        kept = [
            t for t in chunk
            if not t.is_stop and t.is_alpha and t.pos_ in _PHRASE_POS and len(t.lemma_) >= 3
        ]
        words = [_normalized_lemma(t) for t in kept]
        # Require a genuine noun/proper-noun head somewhere in the kept words.
        has_noun_head = any(t.pos_ in _CONTENT_POS for t in kept)
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


def _passive_agent_of(token) -> str | None:
    """The by-phrase's object in a passive sentence ("caused BY friction"),
    found via spaCy's own `agent` dependency label -- not the generic `prep`
    label `_object_of` looks for, which is why a passive by-agent was
    previously invisible to extraction entirely."""
    for child in token.children:
        if child.dep_ == "agent":
            for grandchild in child.children:
                if grandchild.dep_ == "pobj":
                    return _concept_from_token(grandchild)
    return None


def _true_subject_object(verb) -> tuple[str | None, str | None]:
    """Resolve the semantic (agent-like, patient-like) pair for a verb,
    correctly handling passive voice with an expressed agent.

    Found by real crawled text (Task C sampling): "Y is caused by X" has
    Y as `nsubjpass` and X as the object of an `agent`-labelled by-phrase.
    Treating `nsubjpass` as if it were an ordinary subject -- which is what
    the active-voice case correctly does -- would pair (Y, X): backwards,
    since X is still the cause either way the sentence is voiced. When an
    agent is expressed, the roles invert relative to the plain nsubjpass
    reading; when no agent is expressed ("may be folded into sheets"),
    there is nothing to invert against, so the existing nsubjpass-as-subject
    reading is kept unchanged.
    """
    agent = _passive_agent_of(verb)
    if agent is not None:
        subject_tok = next((c for c in verb.children if c.dep_ == "nsubjpass"), None)
        if subject_tok is not None:
            return agent, _concept_from_token(subject_tok)
    return _subject_of(verb), _object_of(verb)


def _is_negated(token) -> bool:
    """True if the verb itself carries a dependency-parse negation ("not",
    "never", "n't", ...), OR sits as the clausal complement of a verb that
    does. spaCy already labels both — `neg` on the negated verb, `ccomp`/
    `xcomp` on a clause whose truth is under its governing verb's mood — so
    this reads two existing dependency labels, not a new lexicon.

    Found by real crawled text (Task C / session 12 sampling), two distinct
    cases:
      - "the cyanobacteria did NOT generate oxygen" — negation on the
        relation verb itself.
      - "one should NOT ASSUME that X implies Y" — the negation sits on the
        governing verb ("assume"); the relation-bearing verb ("implies") is
        its `ccomp` and carries no `neg` of its own. Walked up through
        consecutive ccomp/xcomp links (the embedding can nest) so the
        negation is inherited from whichever ancestor governs the clause's
        truth. Deliberately narrow: negation does NOT propagate across a
        relative clause (`acl`/`relcl`) or a coordinated verb (`conj`) —
        only ccomp/xcomp genuinely put the embedded clause under the
        governing verb's polarity, so "I know a woman who lives in Paris"
        is not negated by an unrelated negated matrix verb.

    Still not attempted: quantifier negation ("almost NO oxygen") — that is
    a determiner on the object noun, not a verb-attached `neg`, and is
    handled separately by `_relation_negated_by_quantifier`.

    A known remaining false-negative source, not fixed here: a governing
    verb that is ITSELF lexically negative ("doubt", "deny", "refuse")
    inverts its ccomp's truth on its own, so negating that verb ("does NOT
    DOUBT that X") asserts X rather than denying it — this walk would
    wrongly suppress a relation the sentence actually asserts. Fixing that
    needs knowing which verbs are inherently negative, which is exactly the
    kind of lexicon this fix was deliberately built to avoid adding
    casually. Rare enough in practice (and worse to guess at than to name)
    that it is left as an open gap rather than a fourth hardcoded table.
    """
    node = token
    while node is not None:
        if any(child.dep_ == "neg" for child in node.children):
            return True
        node = node.head if node.dep_ in ("ccomp", "xcomp") else None
    return False


def _negating_determiner(token) -> bool:
    """True if `token` carries a "no" determiner ("almost no oxygen") --
    negation expressed as a quantifier on the noun itself, invisible to
    `_is_negated` because it never attaches to the verb at all.
    """
    return any(child.dep_ == "det" and child.lemma_.lower() == "no" for child in token.children)


def _relation_negated_by_quantifier(verb) -> bool:
    """True if the subject or object `_true_subject_object` would resolve
    for `verb` carries a negating determiner ("the atmosphere contained
    ALMOST NO oxygen" was extracting (atmosphere, oxygen) as if asserted).

    Mirrors `_subject_of`/`_object_of`/`_passive_agent_of`'s own traversal
    to find the same tokens they resolve into concept strings, checked
    before that resolution discards the token. The passive-agent case
    ("no oxygen was produced BY X") is included for the same reason the
    active case is; only found live in the active-voice shape, so the
    passive path is unverified against a real sentence rather than assumed
    safe by symmetry alone.
    """
    for child in verb.children:
        if child.dep_ in ("nsubj", "nsubjpass", "dobj", "obj") and _negating_determiner(child):
            return True
        if child.dep_ in ("prep", "agent"):
            for grandchild in child.children:
                if grandchild.dep_ == "pobj" and _negating_determiner(grandchild):
                    return True
    return False


def extract_dependencies(sentence: str) -> list[tuple[str, str]]:
    """Return (cause/source, effect/target) concept pairs found in the sentence.

    Two layers, both over real dependency structure (never regex):
      1. Typed causal connectives ("X causes/leads to/requires Y") — high
         confidence, direction set by the connective's meaning.
      2. General subject→object relations for any other content verb ("X
         protects Y", "X encrypts Y") — this is what makes the graph DENSE:
         ordinary sentences produce edges instead of only rare causal ones.
    Copular/auxiliary/light verbs are skipped so "X is Y" noise stays out.
    A negated verb ("does not require", "never causes") yields no edge: it
    would otherwise assert the opposite of what the sentence says.
    """
    doc = get_nlp()(sentence)
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(a: str | None, b: str | None):
        if a and b and a != b and (a, b) not in seen:
            seen.add((a, b))
            pairs.append((a, b))

    for token in doc:
        if token.pos_ != "VERB":
            continue
        if _is_negated(token) or _relation_negated_by_quantifier(token):
            continue
        lemma = token.lemma_.lower()
        subject, obj = _true_subject_object(token)

        if lemma in FORWARD_CONNECTIVES:
            add(subject, obj)                 # cause → effect
        elif lemma in BACKWARD_CONNECTIVES:
            add(obj, subject)                 # prerequisite → dependent
        elif lemma not in _SKIP_VERBS:
            add(subject, obj)                 # general subject → object relation

    return pairs
