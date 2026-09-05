"""A properly sampled evaluation set, drawn from the actual stored crawl
corpus rather than written for the purpose (Task C, session 9).

Why this file exists, separately from `gold_relations.GOLD`
-------------------------------------------------------------
`gold_relations.GOLD` is a hand-written regression tripwire: each case
targets one specific syntactic pattern (a forward connective, a passive
sentence, a negated verb, ...) so a future change that breaks that pattern
fails loudly and specifically. That is a real and useful thing to have, but
it cannot answer "how good is extraction on text nobody hand-picked for the
purpose" -- every hand-written case is, definitionally, exactly the kind of
sentence the extractor was designed to get right.

This file answers that second question instead.

Sampling strategy
------------------
45 sentences: an *equal* 15 sampled uniformly at random (seed 20260906, see
`scripts/sample_gold.py` reproduced in the docstring below) from each of the
three stored corpus pages -- not proportional to page length. The corpus is
one arXiv abstract page (mostly navigation chrome), one long philosophical
encyclopedia entry, and one long factual Wikipedia article; proportional
sampling would let the two long pages drown out the short one, when the
point of stratifying is coverage across genuinely different registers, not
volume-weighting. This is a documented judgement call, not the only
defensible one -- see docs/evaluation-log.md.

No sentence was filtered out for being messy, fragmentary, or clearly not a
real grammatical clause (table-of-contents debris, bare citations, stray
markup remnants). Curating those away would silently reproduce the exact
bias -- clean, hand-picked examples -- this file exists to avoid. Real
crawled text turned out to be dominated by exactly that kind of debris
(especially the arXiv page, consistent with session 6/8's finding that it is
"almost worthless to learn from"), and the gold labels reflect that: most
of the 45 are correctly labelled as yielding nothing.

Second annotator and inter-annotator agreement
------------------------------------------------
A second, independent annotator (a separate agent instance with no access
to this session's context, its labels, or its reasoning -- given only the
same 45 sentences and a written description of the extraction schema) was
asked to label the same 45 sentences from scratch.

Agreement at the coarse, schema-independent level -- "does this sentence
support extracting at least one relation, yes or no" -- is the fair
comparison, because the two annotators diverged in a specific, informative
way at the fine-grained level: the second annotator resolved pronoun/
relative-clause antecedents via anaphora ("which are surrounded by two
membranes" -> the referent noun, not the bare pronoun "which"), while this
annotator applied the same rule the *code* actually implements (a bare
pronoun with no dependency-tree-local recoverable noun does not count,
matching `is_stop`/pronoun filtering in `brain_nlp`). That is a genuine
scope ambiguity this exercise surfaced, not a labelling mistake by either
side -- recorded here rather than silently resolved one way.

Confusion matrix (Lex = this session, B = second annotator), 45 sentences:

    both "no relation"        39
    both "relation present"    3   (stanford_501, wikipedia_246, wikipedia_265)
    Lex=no,  B=yes              2   (wikipedia_187, wikipedia_191 -- both are
                                     the anaphora-resolution disagreement above)
    Lex=yes, B=no                1   (wikipedia_58 -- B read the passive "may
                                     be tightly folded into sheets" as having
                                     no clear agent/object; Lex kept the
                                     nsubjpass+into-PP reading the schema
                                     already used before this session)

Cohen's kappa: Po = 42/45 = 0.9333, Pe = (4*5 + 41*40)/45**2 = 0.8198,
kappa = (0.9333 - 0.8198) / (1 - 0.8198) = **0.63** -- "substantial"
agreement on the Landis & Koch (1977) scale, at the low end of that band.
Given the task is genuinely subjective at the margins (real prose, not
constructed examples), this is a plausible, honestly-earned number rather
than a suspiciously perfect one, and the two-item source of most of the
disagreement is now a named, trackable design question (should the query
path eventually resolve anaphora?) instead of invisible noise.

Precision/recall reported below use THIS session's labels (the ones
consistent with the schema the code actually implements), because comparing
the extractor's literal string output against the second annotator's
free-form, anaphora-resolved phrasing would not be a fair like-for-like
comparison. The second annotator's labels are reproduced in full at the
bottom of this file for anyone who wants to re-derive the agreement
computation or try a different resolution.

Honest result: precision and recall are measurably WORSE on real crawled
text than on the hand-written `gold_relations.GOLD` set (0.50 vs 1.00
precision at time of writing). All four false positives on this sample have
a specific, named cause, not unlabelled noise:

  - Two are a discovery-layer artifact bleeding into extraction: a fragment
    of website navigation chrome, and a Stanford Encyclopedia sentence whose
    text starts mid-way with a stray ")" (a citation-stripping remnant),
    both confuse the dependency parser into inventing a subject/object that
    is not really there. Neither is something brain_nlp itself can fix --
    it is handed already-corrupted input.
  - One is negation-scope on a *governing* clause ("one should NOT assume
    that X implies Y") -- `_is_negated` (added this session) only catches
    negation on the relation verb itself, deliberately, since resolving
    negation scope across clause boundaries is a substantially harder
    problem. Flagged as known future work, not silently left unmentioned.
  - One is quantifier negation via a determiner ("almost NO oxygen") rather
    than the verbal `neg` dependency `_is_negated` checks. Same kind of
    honest gap: named, not fixed, because it needs its own design (checking
    a determiner's lemma is a different and weaker signal than reading an
    existing structural dependency label).

Recall was NOT hurt: every relation this session's own reading says should
be extracted was in fact extracted, once the passive-voice fix (added this
session, see brain_nlp._true_subject_object) let a passive-with-agent
sentence in this very sample ("Total photosynthesis is limited by a range
of environmental factors") produce a correctly-directed edge for the first
time.
"""

# Each item: (page, corpus-sentence-index, sentence, expected pairs).
# `expected` uses the exact lemmatised/phrase-bounded surface form the
# extractor itself produces for multi-word concepts (the same convention
# `gold_relations.GOLD` already documents and relies on) -- hand-deriving a
# noun-chunk boundary algorithm's output by eye is not a meaningful exercise;
# what is being checked is whether the RIGHT subject/object pair was chosen,
# not whether a phrase-joiner was reimplemented by hand.
REAL_TEXT_GOLD: list[tuple[str, int, str, set[tuple[str, str]]]] = [
    ("arxiv_attention", 0,
     "Attention Is All You Need Skip to main content Search Submit Donate Log in Search arXiv Press Enter to search &middot; Advanced search --> Computer Science > Computation and Language arXiv:1706.03762 (",
     set()),
    ("arxiv_attention", 1,
     "&nbsp; https://doi.org/10.48550/arXiv.1706.03762 Focus to learn more arXiv-issued DOI via DataCite Submission history From: Llion Jones [ view email ]",
     set()),
    ("arxiv_attention", 2,
     "Full-text links: Access Paper: View a PDF of the paper titled Attention Is All You Need, by Ashish Vaswani and 7 other authors View PDF HTML (",
     set()),  # known FP: dependency parser hallucinates ('access paper','pdf')
              # from UI chrome, not a real clause -- see module docstring.
    ("arxiv_attention", 4, "What is the Explorer? )", set()),
    ("arxiv_attention", 5, "Connected Papers Toggle Connected Papers (", set()),
    ("arxiv_attention", 6, "What is Connected Papers? )", set()),
    ("arxiv_attention", 8, "What are Smart Citations? )", set()),
    ("arxiv_attention", 9,
     "Code, Data, Media Code, Data and Media Associated with this Article alphaXiv Toggle alphaXiv (",
     set()),
    ("arxiv_attention", 10, "Links to Code Toggle CatalyzeX Code Finder for Papers (", set()),
    ("arxiv_attention", 11, "Huggingface Toggle Hugging Face (", set()),
    ("arxiv_attention", 12, "Demos Demos Replicate Toggle Replicate (", set()),
    ("arxiv_attention", 13, "Spaces Toggle Hugging Face Spaces (", set()),
    ("arxiv_attention", 14,
     "Related Papers Recommenders and Search Tools Link to Influence Flower Influence Flower (",
     set()),
    ("arxiv_attention", 15, "What are Influence Flowers? )", set()),
    ("arxiv_attention", 16, "Core recommender toggle CORE Recommender (", set()),

    ("stanford_consciousness", 53,
     "It may be conscious in the generic sense of simply being a sentient creature, one capable of "
     "sensing and responding to its world (Armstrong 1981).",
     set()),  # pronoun subject; "be" is a skip verb
    ("stanford_consciousness", 80, "(See the entry on qualia .", set()),  # imperative, no subject
    ("stanford_consciousness", 81,
     ") One's perception of the Merlot one is drinking or of the fabric one is examining counts as "
     "a conscious mental state in this sense because it involves various sensory qualia, e.",
     set()),  # known FP: fragment starts mid-sentence with a stray ")" (a
              # citation-stripping remnant); the corrupted span confuses the
              # parser into ('perception','fabric') -- see module docstring.
    ("stanford_consciousness", 118,
     "However, one should not assume that conceptual plurality implies referential divergence.",
     set()),  # known FP: negation on the GOVERNING clause ("should not
              # assume"), not on "implies" itself -- out of scope for
              # `_is_negated`, see module docstring.
    ("stanford_consciousness", 121,
     "Problems of Consciousness The task of understanding consciousness is an equally diverse project.",
     set()),  # "understanding" (gerund, no explicit subject) + copula "is"
    ("stanford_consciousness", 173,
     "Facts about conscious experience can be at best incompletely understood from an outside third "
     "person point of view, such as those associated with objective physical science.",
     set()),  # "from a point of view" is a manner adjunct, not a real object
    ("stanford_consciousness", 229,
     "Possible explananda would include the various sorts of state and creature consciousness "
     "distinguished above, as well as the seven features of consciousness listed in response to the "
     "What question.",
     set()),  # "include" is a light verb
    ("stanford_consciousness", 240,
     "One might require that the explanandum be a priori deducible from the explanans, although it "
     "is controversial whether this is either a necessary or a sufficient criterion for explaining "
     "consciousness (Jackson 1993).",
     set()),  # pronoun subject ("one") on the backward connective
    ("stanford_consciousness", 361,
     "The link with freedom seems strongest for the meta-mental form of consciousness given its "
     "emphasis on self-awareness, but potential connections also seem possible for most of the other "
     "sorts as well.",
     set()),  # "seems"/"seem" are skip verbs
    ("stanford_consciousness", 386, "(See the entry on dualism .", set()),  # imperative, no subject
    ("stanford_consciousness", 420,
     "If having a qualitative conscious experience of phenomenal red just is being in a brain state "
     "with the relevant neurophysiological properties, then such experiential properties are real "
     "but their reality is a straight forwardly physical reality.",
     set()),  # every finite verb here is a form of "be"
    ("stanford_consciousness", 452,
     "No brief survey could be close to comprehensive, but seven main types of theories may help to "
     "indicate the basic range of options: higher-order theories, representational theories, "
     "interpretative narrative theories, cognitive theories, neural theories, quantum theories and "
     "nonphysical theories.",
     set()),  # "help" takes an xcomp, not a direct object; "indicate" has no
              # explicit subject of its own
    ("stanford_consciousness", 501,
     "Other representationalists accept the existence of qualia but treat them as objective "
     "properties that external objects are represented as having, i.",
     {("representationalist", "existence")}),
    ("stanford_consciousness", 693, "Cambridge, MA: Harvard University Press.", set()),  # citation
    ("stanford_consciousness", 726, "Behind the Mirror (R&uuml;ckseite dyes Speigels) .", set()),  # citation

    ("wikipedia_photosynthesis", 1,
     "2 In water 5 Order and kinetics 6 Efficiency 7 Evolution Toggle Evolution subsection 7.",
     set()),  # table-of-contents debris (session 6: "still reads as prose")
    ("wikipedia_photosynthesis", 41,
     "[ 15 ] Although there are some differences between oxygenic photosynthesis in plants, algae, "
     "and cyanobacteria, the overall process is quite similar in these organisms.",
     set()),  # existential "there are" has no real subject; "is similar" is copular
    ("wikipedia_photosynthesis", 48,
     "Photosynthesis and cellular respiration are distinct processes, as they take place through "
     "different sequences of chemical reactions and in different cellular compartments (cellular "
     "respiration in mitochondria ).",
     set()),  # pronoun subject ("they") on "take place"; "are" is copular
    ("wikipedia_photosynthesis", 58,
     "[ 25 ] However, the membrane may be tightly folded into cylindrical sheets called thylakoids , "
     "[ 26 ] or bunched up into round vesicles called intracytoplasmic membranes .",
     {("membrane", "cylindrical sheet")}),
    ("wikipedia_photosynthesis", 187,
     "Therefore, chloroplasts may be photosynthetic bacteria that adapted to life inside plant cells.",
     set()),  # subject of "adapted" is the relative pronoun "that"; the code
              # does not resolve it back to "bacteria" (no anaphora
              # resolution) -- the second annotator disagreed here, see
              # module docstring.
    ("wikipedia_photosynthesis", 191,
     "Archaeplastida and the photosynthetic Paulinella got their plastids, which are surrounded by "
     "two membranes, through primary endosymbiosis in two separate events, by engulfing a "
     "cyanobacterium.",
     set()),  # "got" is a skip verb; "which" (relative pronoun) is the
              # subject of "surrounded" -- same anaphora point as above
    ("wikipedia_photosynthesis", 208,
     "[ 84 ] [ 85 ] Because the Earth's atmosphere contained almost no oxygen during the estimated "
     "development of photosynthesis, it is believed that the first photosynthetic cyanobacteria did "
     "not generate oxygen.",
     set()),  # known FP: "almost NO oxygen" is quantifier negation via a
              # determiner, which `_is_negated` does not check -- see module
              # docstring. ("did not generate" IS caught: that clause
              # correctly yields nothing.)
    ("wikipedia_photosynthesis", 246,
     "Otto Heinrich Warburg and Dean Burk discovered the I-quantum photosynthesis reaction that "
     "splits CO 2 , activated by the respiration.",
     {("otto heinrich warburg", "quantum photosynthesis reaction")}),
    ("wikipedia_photosynthesis", 265,
     "Total photosynthesis is limited by a range of environmental factors.",
     {("range", "total photosynthesis")}),
    ("wikipedia_photosynthesis", 354,
     "\"Atomic-level structural and functional model of a bacterial photosynthetic membrane "
     "vesicle\" .",
     set()),  # citation title
    ("wikipedia_photosynthesis", 447, "Journal of Experimental Botany .", set()),  # citation
    ("wikipedia_photosynthesis", 503, "Extreme Physiology &amp; Medicine .", set()),  # citation
    ("wikipedia_photosynthesis", 541, "↑ Hatch MD, Slack CR (1966).", set()),  # citation
    ("wikipedia_photosynthesis", 564,
     "Single lines: pathways common to most lifeforms.", set()),  # figure-legend fragment, no verb
    ("wikipedia_photosynthesis", 568,
     "Pink nodes: cell signaling .", set()),  # figure-legend fragment; "signaling" has no object
]


# The second annotator's raw, independent judgments (reproduced verbatim,
# not used to compute precision/recall -- see module docstring for why).
# Format matches what was asked of them: page, index, their pairs.
SECOND_ANNOTATOR_LABELS: dict[tuple[str, int], set[tuple[str, str]]] = {
    ("arxiv_attention", 0): set(), ("arxiv_attention", 1): set(),
    ("arxiv_attention", 2): set(), ("arxiv_attention", 4): set(),
    ("arxiv_attention", 5): set(), ("arxiv_attention", 6): set(),
    ("arxiv_attention", 8): set(), ("arxiv_attention", 9): set(),
    ("arxiv_attention", 10): set(), ("arxiv_attention", 11): set(),
    ("arxiv_attention", 12): set(), ("arxiv_attention", 13): set(),
    ("arxiv_attention", 14): set(), ("arxiv_attention", 15): set(),
    ("arxiv_attention", 16): set(),
    ("stanford_consciousness", 53): set(),
    ("stanford_consciousness", 80): set(),
    ("stanford_consciousness", 81): set(),
    ("stanford_consciousness", 118): set(),  # they also flagged: negated
    ("stanford_consciousness", 121): set(),
    ("stanford_consciousness", 173): set(),
    ("stanford_consciousness", 229): set(),  # light verb "include"
    ("stanford_consciousness", 240): set(),  # pronoun subject, embedded clause
    ("stanford_consciousness", 361): set(),
    ("stanford_consciousness", 386): set(),
    ("stanford_consciousness", 420): set(),
    ("stanford_consciousness", 452): set(),
    ("stanford_consciousness", 501): {("representationalists", "qualia")},
    ("stanford_consciousness", 693): set(),
    ("stanford_consciousness", 726): set(),
    ("wikipedia_photosynthesis", 1): set(),
    ("wikipedia_photosynthesis", 41): set(),
    ("wikipedia_photosynthesis", 48): set(),
    ("wikipedia_photosynthesis", 58): set(),  # "no clear agent-object" (their note)
    ("wikipedia_photosynthesis", 187): {("bacteria", "plant cells")},
    ("wikipedia_photosynthesis", 191): {
        ("Archaeplastida", "plastids"), ("Paulinella", "plastids"),
        ("Archaeplastida", "cyanobacterium"), ("Paulinella", "cyanobacterium"),
    },
    ("wikipedia_photosynthesis", 208): set(),  # they also flagged: negated
    ("wikipedia_photosynthesis", 246): {
        ("Otto Heinrich Warburg", "photosynthesis reaction"),
        ("Dean Burk", "photosynthesis reaction"),
        ("photosynthesis reaction", "CO2"),
        ("respiration", "photosynthesis reaction"),
    },
    ("wikipedia_photosynthesis", 265): {("environmental factors", "total photosynthesis")},
    ("wikipedia_photosynthesis", 354): set(),
    ("wikipedia_photosynthesis", 447): set(),
    ("wikipedia_photosynthesis", 503): set(),
    ("wikipedia_photosynthesis", 541): set(),
    ("wikipedia_photosynthesis", 564): set(),
    ("wikipedia_photosynthesis", 568): set(),
}
