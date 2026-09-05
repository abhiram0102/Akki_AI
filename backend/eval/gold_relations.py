"""Hand-labelled sentences and the relations they should yield.

Why this exists
---------------
Until now nothing could answer "did that change make extraction better or
worse?". Every threshold in the pipeline was set by looking at one or two
examples, and every future change would have been guesswork. A gold set turns
that into a number that moves.

What it tests
-------------
`brain_nlp.extract_dependencies` finds (cause, effect) pairs from a sentence.
The cases below cover the four things it has to get right:

- **Forward connectives**, where the subject causes the object.
- **Backward connectives**, where the subject is the dependent and the object
  is the thing depended upon, so the arrow points the other way. Getting these
  backwards would silently invert a chunk of the graph.
- **Ordinary transitive statements**, which are where most edges actually come
  from. If only causal verbs produced edges the graph would be almost empty.
- **Sentences that should yield NOTHING.** Copular and light verbs ("X is Y",
  "X has Y") carry no relationship, and a graph flooded with those becomes
  useless. Precision matters as much as recall here, so silence is a correct
  answer that has to be checked for.

An honest limitation
--------------------
These labels are my own judgement, not an independent annotator's, so this
measures agreement with one reading rather than objective truth. The pairs also
use the same lemmatised, lowercased form the extractor produces, which builds
in its normalisation. It is a regression instrument, not evidence that the
extractor is correct in some absolute sense. A second annotator, and cases
drawn from real crawled text rather than written for the purpose, would both
make it stronger.
"""

# Each case: the sentence, and the set of (cause, effect) pairs it should
# produce. An empty set means the sentence carries no relationship worth
# storing, which is a real and testable expectation.
GOLD: list[tuple[str, set[tuple[str, str]]]] = [
    # ── Forward connectives: subject causes object ──────────────────────────
    ("Friction causes heat.", {("friction", "heat")}),
    ("Deforestation leads to soil erosion.", {("deforestation", "soil erosion")}),
    ("Photosynthesis produces oxygen.", {("photosynthesis", "oxygen")}),
    ("Inflation triggers wage demands.", {("inflation", "wage demand")}),
    ("Vaccination creates immunity.", {("vaccination", "immunity")}),

    # ── Backward connectives: the arrow points the other way ────────────────
    # The subject is the dependent; the object is what it rests on. An
    # extractor that treated these like forward verbs would invert them.
    ("Photosynthesis requires sunlight.", {("sunlight", "photosynthesis")}),
    ("Combustion needs oxygen.", {("oxygen", "combustion")}),
    ("The economy depends on energy.", {("energy", "economy")}),

    # ── Ordinary transitive statements: where most edges come from ──────────
    ("Encryption protects data.", {("encryption", "data")}),
    ("Antibodies neutralise pathogens.", {("antibody", "pathogen")}),
    ("Enzymes catalyse reactions.", {("enzyme", "reaction")}),

    # ── Irregular plural morphology: "data" must not become "datum" ─────────
    # Loanword false friends where spaCy's classical singular is rare/wrong
    # in ordinary prose (Task B). Contrast case included so the exception
    # list is proven narrow rather than "keep every plural as-is".
    ("Advertisers target media.", {("advertiser", "media")}),
    ("Engineers multiply matrices.", {("engineer", "matrix")}),

    # ── Passive voice ────────────────────────────────────────────────────────
    # A passive sentence must yield the same (cause, effect) pair as its
    # active-voice paraphrase. Found missing/backwards by real-text sampling
    # (Task C): the by-agent uses spaCy's `agent` dependency label, not
    # `prep`, and naively treating `nsubjpass` like an ordinary subject gets
    # the direction backwards once the by-agent is found at all.
    ("Heat is caused by friction.", {("friction", "heat")}),
    ("Sunlight is required by photosynthesis.", {("sunlight", "photosynthesis")}),
    ("Data is protected by encryption.", {("encryption", "data")}),

    # ── Negation ─────────────────────────────────────────────────────────────
    # A negated verb asserts the ABSENCE of a relationship; extracting one
    # anyway would record the opposite of what the sentence says. Found by
    # real-text sampling (Task C): "the cyanobacteria did not generate
    # oxygen" was yielding (cyanobacteria, oxygen).
    ("The firewall does not block traffic.", set()),
    ("Vaccines never cause autism.", set()),

    # ── Sentences that must yield nothing ───────────────────────────────────
    # Copular and light verbs carry no relationship. A graph full of "X is Y"
    # is a graph that cannot answer anything.
    ("Photosynthesis is a process.", set()),
    ("The cell has a membrane.", set()),
    ("This is it.", set()),
    ("Consciousness seems mysterious.", set()),
]
