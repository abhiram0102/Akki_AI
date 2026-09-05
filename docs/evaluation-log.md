# AKKI Brain — Evaluation Log

Running log of what was measured, how, and how the numbers moved. Newest
entry first. Complements `docs/architecture-log.md` (design decisions) —
this file is specifically for measurement: sampling strategy, inter-annotator
agreement, precision/recall over time.

---

## 2026-09-06 (session 9) — Real-text evaluation, two fixes, a trend line

**Status:** implemented and tested. 219 backend tests pass (was 206 at the
start of this session).

### Starting point

Session 8 recorded a baseline (precision 0.90, recall 0.82, F1 0.86 over 15
hand-written cases) and named two defects without fixing them: "data" stored
as "datum", and "Enzymes catalyse reactions" yielding nothing. It also
recorded two honest limitations: the 15 gold cases were one person's
judgement, written for the purpose rather than sampled, so the number
measured agreement with one reading rather than truth.

This session's assignment was those two defects, plus replacing the
evaluation itself so the next session isn't measuring against
training-adjacent examples.

### Task A — is `en_core_web_sm` the real bottleneck?

Measured `en_core_web_sm` against `md` and `lg`, both the gold-set
precision/recall and per-page yield over the stored corpus, plus load time
and peak memory (Windows `GetProcessMemoryInfo`, fresh subprocess per model
so one model's footprint can't contaminate another's).

| model | precision | recall | F1 | load (s) | peak RSS (MB) | corpus eval (s) |
|---|---|---|---|---|---|---|
| en_core_web_sm | 0.90 | 0.818 | 0.857 | 3.0 | 136 | 8.2 |
| en_core_web_md | 0.90 | 0.818 | 0.857 | 4.3 | 341 | 9.6 |
| en_core_web_lg | 0.909 | 0.909 | 0.909 | 5.5 | 710 | 20.9 |

`md` does **not** fix "Enzymes catalyse reactions" — its tagger makes the
same error as `sm` (tags "catalyse" as a NOUN in a bare-plural-subject,
present-tense, no-determiner construction: "Enzymes catalyse reactions",
even "Enzymes catalyze reactions" with the American spelling). Only `lg`
gets it right (`catalyse` correctly tagged VERB, ROOT).

Cost of `lg` over `sm`: **5.2x peak memory, ~2.5x slower per sentence**,
in a request path (session 8 flagged this pipeline runs at read/answer
time, not just crawl time). Gain: one gold case fixed, plus a modest yield
bump on the already-thin arXiv page (2→6 concepts, 1→3 relations). Both
Dockerfiles (`Dockerfile.backend:44`, `Dockerfile.brain-crawler:14`) would
need updating.

**Not switched.** Per the brief, this is an architectural fork, not a
routine choice — flagged to ammu/god with these numbers rather than decided
unilaterally. Recommendation, for the record: the cost looks
disproportionate to the gain for a narrow sentence class (bare-plural
subject/object with no determiner and a present-tense verb); Task C's
real-text sample below found the actual precision-limiting patterns on real
crawled text are elsewhere (negation, discovery-layer fragments feeding
extraction bad input) — `lg` would not have moved most of those.

### Task B — irregular plural morphology

`brain_nlp` already uses a real morphological analyzer (spaCy's
lemmatiser), not naive suffix-stripping — there was no regex stemmer to
replace. Measured ~40 candidate irregular plurals over realistic sentences
(not the single degenerate template "The X matter.", which mistags almost
everything regardless of the real defect) to find which ones spaCy's own
lemmatiser actually gets wrong, rather than guessing a list.

Result: the vast majority are lemmatised *correctly*, and collapsing a
plural mention onto its singular is the **desired** behaviour (matrix/
matrices, index/indices, thesis/theses, virus/viruses, child/children,
mouse/mice, goose/geese all consolidate correctly in real sentence
context). Only five measurably misfire — Latin/Greek loanwords whose
classical singular is rare/archaic or names a different sense in ordinary
technical prose: **data → datum, media → medium, criteria → criterion,
phenomena → phenomenon, trivia → trivium**.

Fix: `brain_nlp._IRREGULAR_PLURAL_SURFACE`, a 5-word curated exception list
keyed on the *surface word the writer used* (not the lemma spaCy assigns),
so a genuine singular use ("a growth medium", "one datum point") is left
untouched — only the plural spelling itself is pinned to its own surface
form as the concept key. This is a hardcoded lexical table, the same class
already flagged for `FORWARD_CONNECTIVES`/`BACKWARD_CONNECTIVES`.

Irregular verb morphology was checked too (went→go, ran→run, caught→catch,
led→lead, arose→arise, ...) and found **already correct** — spaCy's verb
lemmatiser has no equivalent defect. The system brief's premise that this
generalises to "every irregular plural/verb form" does not hold; it is
specifically these five loanword nouns.

Tests: `backend/tests/test_brain_nlp.py` — irregular loanword plurals stay
as-is, a genuine singular ("medium") is not rewritten to the plural form,
ordinary loanword plurals (matrix, thesis, ...) still consolidate onto the
singular (proving the exception list is narrow, not "keep every plural"),
native English irregular plurals lemmatise correctly with no override
needed, and irregular past-tense verbs still match `FORWARD_CONNECTIVES`.

### Two more defects found and fixed while sampling for Task C

Neither was in the original brief; both were found because Task C's real
sentences, unlike hand-written ones, contain negation and passive voice.

**Negation.** "The cyanobacteria did not generate oxygen" was extracting
`(cyanobacteria, oxygen)` as if asserted — backwards from what the sentence
says. Fix reads spaCy's own `neg` dependency label on the relation verb
(`brain_nlp._is_negated`) — no new lexicon, an existing parser output field
was simply never checked. Deliberately scoped to verb-local negation only;
negation on a *governing* clause ("one should NOT assume that X implies Y")
and quantifier negation via a determiner ("almost NO oxygen") are named,
not fixed — full negation-scope resolution is a harder problem than this
session's budget covered.

**Passive voice with an expressed agent.** "Heat is caused by friction"
was yielding nothing at all (the by-agent uses spaCy's `agent` dependency
label, not `prep`, so `_object_of`'s prep-based fallback never found it).
Fixing the missing-object bug alone would have gotten the **direction**
backwards for typed connectives: `nsubjpass` is the grammatical patient, not
the agent, so pairing it with the by-agent the same way active-voice
subject/object are paired inverts the relationship. `brain_nlp.
_true_subject_object` now detects an expressed passive agent and swaps
roles accordingly; a passive sentence with no agent ("membrane may be
folded into sheets") is untouched, since there is nothing to invert
against. Verified: `"Friction causes heat."` and `"Heat is caused by
friction."` now produce the identical pair, in both directions
(forward/backward connectives), and for the general (non-connective) verb
case too.

Tests added for both in `backend/tests/test_brain_nlp.py`.

### Task C — a properly sampled evaluation set

Full methodology, the 45 sentences, both annotators' labels, and the
inter-annotator agreement computation live in
`backend/eval/real_text_gold.py` (reproducible sampling script:
`backend/eval/sample_gold.py`). Summary:

- **Sampling:** 15 sentences sampled uniformly at random (fixed seed) from
  each of the 3 stored corpus pages — equal per page, not proportional to
  page length, so the two long pages don't drown out the short one; the
  goal is register diversity (arXiv nav chrome, Stanford philosophical
  prose, Wikipedia factual prose), not volume-weighting. No quality
  filtering — messy/fragmentary "sentences" were kept and labelled as
  such, since filtering them out would recreate the exact bias (clean,
  hand-picked examples) this sample exists to avoid.
- **Second annotator:** an independent agent instance, given only the 45
  sentences and a written description of the schema, no access to this
  session's labels or reasoning, labelled the same set blind.
- **Inter-annotator agreement:** Cohen's kappa = **0.63** ("substantial"
  agreement, Landis & Koch 1977, low end of the band) on the coarse
  question "does this sentence support extracting at least one relation".
  42/45 sentences agreed. All 3 disagreements trace to one specific,
  named scope question the exercise itself surfaced: the second annotator
  resolved pronoun/relative-clause antecedents via anaphora ("which are
  surrounded by two membranes" → the noun it refers to); this session
  applied the same rule the code implements (a bare pronoun with no
  dependency-tree-local recoverable noun does not count). That is a real
  open design question — should the pipeline eventually resolve anaphora —
  not an annotator error on either side.
- **Precision/recall, measured separately from the hand-written set**
  (comparing exact extractor output against the second annotator's
  free-form, anaphora-resolved phrasing would not be a fair comparison, so
  precision/recall use this session's schema-consistent labels; the second
  annotator's raw labels are preserved in full for anyone re-deriving the
  agreement number):

| set | cases | precision | recall | F1 |
|---|---|---|---|---|
| hand-written (`gold_relations.GOLD`, regression tripwire) | 22 | 1.00 | 0.938 | 0.968 |
| **real-text sample (`real_text_gold.REAL_TEXT_GOLD`, held-out)** | **45** | **0.50** | **1.00** | **0.667** |

**This is the number that should be trusted going forward.** Precision on
real crawled text is measurably worse than the hand-written set suggested —
exactly the honest result Task C exists to surface, not a suspiciously
clean confirmation. All 4 false positives on the real-text sample have a
specific, named cause (see `real_text_gold.py` docstring): two are the
discovery layer handing extraction already-corrupted input (nav chrome, a
citation-stripping remnant), one is the governing-clause negation gap named
above, one is the quantifier-negation gap named above. Recall is 1.00
because every relation this session's reading says should be extracted,
was — including the passive-agent sentence in this very sample
(`wikipedia_photosynthesis#265`), which would have been a recall miss
before this session's passive-voice fix.

Both new gold sets are now baseline-guarded
(`backend/tests/test_eval_baseline.py`); the guard on the new set was
verified to actually fire (temporarily disabling the negation check dropped
measured real-text precision from 0.50 to 0.444, enough to fail it).

### Word sense induction — benchmark alignment (checked, not yet acted on)

The brief asked whether published WSI evaluation protocols (e.g. SemEval-13
Task 11, SemEval-10 Task 14) apply to `brain_meaning.py`'s sense discovery.
They do, in principle — those tasks use Fuzzy B-Cubed / V-Measure against
human sense-annotated corpora, and `brain_meaning`'s k-means-with-a-
null-distribution-floor is exactly the kind of system such benchmarks
target. Not adopted this session: no `brain_meaning` code was touched (out
of scope — this session's brief was `brain_nlp.py` and `backend/eval/*`
only), and the existing sense-discovery evaluation (session 5's "test
against chance", measured on real crawl data with a calibrated 3.5σ floor)
is closer to an intrinsic clustering-quality check than a WSI accuracy
benchmark. Adopting a SemEval-style protocol would need labelled
sense-tagged data this project doesn't have and no source currently
provides — flagging this as a real methodological fork for whoever next
works on `brain_meaning.py`, not deciding it here.

### Honest limitations, carried forward

- Negation-scope across clause boundaries and quantifier negation
  ("almost no X") are named, real gaps, not silently left out of this log.
- The real-text sample is 45 sentences from 3 pages — a genuine sample, but
  still small and drawn from only the sources session 8 happened to store.
  Growing the stored corpus (more pages, more source types) would let a
  future session grow this sample without re-deriving a sampling strategy.
- IAA was computed from one independent annotator, not several — a kappa
  from a single pair is a real number but a thinner basis than one averaged
  over multiple annotators would be.
