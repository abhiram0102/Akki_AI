"""Page-level assertions checked against the CURRENT, live discovery +
extraction pipeline running end to end over the stored corpus -- not frozen
sentence strings.

Why this file exists
---------------------
`gold_relations.GOLD` and `real_text_gold.REAL_TEXT_GOLD` both feed a fixed
sentence STRING straight to `brain_nlp.extract_dependencies`. That is
deliberate for `GOLD` (a regression tripwire keyed to one pattern per case),
but it has a structural blind spot neither gold set can see past: a fix or
regression in `brain_discovery` -- which sentences get split out at all, and
which get thrown away as non-prose -- never touches those frozen strings.
Removing a fragment from the real pipeline does not remove it from a gold
set built from an earlier run's output.

This was not a hypothetical concern. Two sessions found it independently
within an hour of each other: session 11 found the harness never exercises
`resolve_source` (page *selection*) at all, and session 12 found it cannot
see a `brain_discovery` fix (page *structuring*) either -- `measure_real_text_
quality` stayed at the same 0.500 precision through a discovery change that
demonstrably removed two of its four false positives from the real pipeline.
Confirmed directly: running today's `discover_structure` + `extract_
dependencies` over the stored corpus, all four pairs below that were
historically false positives are ABSENT -- yet the frozen-string harness
still reports two of them as present, because it is quite literally re-running
extraction on last week's already-corrupted sentence text instead of asking
the current pipeline to produce its own.

What this checks instead
--------------------------
For each stored page, run discovery and extraction FRESH, exactly as the
crawler and on-demand learner would today, and check two page-level claims
that survive discovery reshaping the sentence list around them:

  - EXPECTED: a relation genuinely present in the source prose must appear
    SOMEWHERE in the page's relation set -- not tied to one sentence index,
    which discovery is free to split, merge, or renumber.
  - FORBIDDEN: a relation known to have come from a non-clause artifact
    (navigation chrome, a corrupted fragment, a negated/quantified clause)
    must appear NOWHERE in the page's relation set, regardless of which
    sentence discovery currently carves out of the page.

This is deliberately coarse (page-level, not sentence-level) -- that
coarseness is the point: it is robust to exactly the kind of reshaping a
legitimate discovery improvement performs, which sentence-level frozen gold
cannot be.
"""

# (page, expected pair, one-line provenance)
EXPECTED_SOMEWHERE_ON_PAGE: list[tuple[str, tuple[str, str], str]] = [
    ("stanford_consciousness", ("representationalist", "existence"),
     "real_text_gold #501, ordinary transitive statement"),
    ("wikipedia_photosynthesis", ("membrane", "cylindrical sheet"),
     "real_text_gold #58, passive with no expressed agent"),
    ("wikipedia_photosynthesis", ("otto heinrich warburg", "quantum photosynthesis reaction"),
     "real_text_gold #246, ordinary transitive statement, multi-word concepts"),
    ("wikipedia_photosynthesis", ("range", "total photosynthesis"),
     "real_text_gold #265, passive WITH an expressed agent (session 11 fix)"),
]

# (page, forbidden pair, one-line provenance -- what produced it and which
# session's fix was supposed to remove it)
FORBIDDEN_ANYWHERE_ON_PAGE: list[tuple[str, tuple[str, str], str]] = [
    ("arxiv_attention", ("access paper", "pdf"),
     "discovery-layer artifact: nav-chrome fragment parsed as a clause (session 12 fix)"),
    ("stanford_consciousness", ("perception", "fabric"),
     "discovery-layer artifact: fragment corrupted by a mis-placed sentence cut (session 12 fix)"),
    ("stanford_consciousness", ("conceptual plurality", "referential divergence"),
     "governing-clause negation, 'should not assume that X implies Y' (session 12/13 fix)"),
    ("wikipedia_photosynthesis", ("earth atmosphere", "oxygen"),
     "quantifier negation, 'contained almost no oxygen' (session 12/13 fix)"),
]
