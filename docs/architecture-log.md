# AKKI Brain — Architecture Log

Running log so a new session resumes without re-deriving context. Newest entry first.

---

## 2026-09-06 (session 11) — resolve_source: found live, fixed, and re-verified live

**Status:** implemented and tested. All tests in this change's own files pass
(`test_brain_learn.py`, `test_brain_fetchers.py`, plus the pre-existing
crawler/learn-engine tests, unaffected). The whole-suite number was a moving
target while writing this: `brain_discovery.py` had uncommitted changes
throughout (confirmed via `git status`) from ammu's concurrent work on the
nav-chrome/citation-fragment issue, and `test_brain_discovery.py` /
`test_eval_baseline.py` failures tracked her edits in progress, not anything
in this diff -- this session's own changes never touch that file.

### Found by actually running the system, not by a test

Smoke-testing the live app (per Sanju's request) against a genuinely new
topic ("graphene") surfaced a bug no test could have caught: `resolve_source`
resolved it to the Wikipedia article "GrapheneOS" (a phone OS) instead of the
material, and extraction correctly found nothing useful on that page. Neither
the unit suite nor the eval harness exercises this function at all -- the
eval corpus is stored HTML, so the harness never calls the step that
*chooses* a page in the first place.

### Two independent bugs in one function, both fixed

1. **Word-overlap ranking couldn't tell a real word from a fragment of a
   longer one.** "graphene" is a raw substring of "grapheneos", so a
   bag-of-words overlap count scored both references identically and ties
   resolved arbitrarily. Replaced with `_reference_match_score`: three
   ordinal tiers -- exact anchor-text match, token-bounded match (a real
   word/phrase, not a substring), bare substring match -- with overlap count
   used only to break ties *within* a tier, never to let raw count override
   the tier ordering. No hardcoded knowledge of Wikipedia's (or any site's)
   naming conventions -- the ordering comes from the shape of the match
   itself, per the project's charter.
2. **The bigger one, found only by testing the fix against the live site:**
   searching "graphene" doesn't render a results list at all -- MediaWiki
   302-redirects straight to the real article on an exact title match. The
   old code (and the fixed ranking, on its own) was reading *that landed-on
   article's own* outbound links ("Discovery of graphene", "GrapheneOS",
   "Graphite", ...) as if they were search results, and ranking among those.
   `brain_fetchers.fetch_structure` now reports `redirectedTo` -- the final
   address, if and only if `resp.history` shows the HTTP transport itself
   redirected there. `resolve_source` trusts that outright when present,
   never consulting references at all: the search mechanism's own redirect
   is stronger evidence than anything derived from the page it lands on.
   This reads the transport's own behaviour, not any site's search format --
   the same non-hardcoding constraint as fix (1).

### Verified live, twice

Per the tripwire's own limit (`resolve_source` isn't in the eval harness, so
a green suite is not evidence here): ran the fix against the real Wikipedia
search endpoint before and after. Before: `graphene` -> `GrapheneOS`. After
fix (1) alone: `graphene` -> `Discovery_of_graphene` (better, still wrong).
After fix (2): `graphene` -> `Graphene`, and `penicillin`/`insulin`/
`mitochondria` (previously resolving to `..._` with a stray trailing
underscore -- the same reference-ranking symptom) now resolve to the clean
canonical article address too.

### Scope and ownership

`brain_learn.py` and `brain_fetchers.py` only. `brain_discovery.py` stays
ammu's -- confirmed via `git status` before and after this change that it
was never touched, matching the file-level split agreed for this pair of
issues (mirrors the `brain_nlp.py` split earlier in this thread, pointed the
other way).

### Open items, named rather than fixed

- Ammu's original second-signal suggestion -- fetch the chosen page and
  check whether its own text confirms the topic -- is now largely
  subsumed by the redirect signal for the common "single clear match"
  case, but remains a real idea for the case where a search page renders a
  genuine results list with several plausible candidates and no redirect
  happens. Not built; flagged for whoever next touches this function.
- The reference-ranking tiers were designed and tested against constructed
  cases (the real bug's shape, reproduced without hardcoding the specific
  site), not against a sampled set of real ambiguous search pages the way
  Task C sampled real sentences. Worth doing if this function turns out to
  need more than the two fixes above.

## 2026-09-06 (session 10) — Parser model: decided, and the measurement redirected the work

**Status:** decided and recorded. 219 backend tests pass.

### The decision: stay on the small model

lex measured the three parser models and correctly refused to switch without
sign-off, bringing quality on the hand-written gold set:

| model | hand-written F1 | load | peak RSS |
|---|---|---|---|
| sm | 0.857 | 3.0s | 136MB |
| md | 0.857 | 4.3s | 341MB |
| lg | 0.909 | 5.5s | 710MB |

On that table alone the large model looks like the answer. Two numbers were
missing, and both were needed because they are what the decision actually turns
on: how many relations each model draws from real pages, and how each scores on
the **sampled real-text** set that lex themselves identified as the number to
trust over the hand-written one.

| model | relations from corpus | real-text precision | real-text recall |
|---|---|---|---|
| sm | 149 | 0.500 | 1.000 |
| md | 154 | 0.571 | 1.000 |
| lg | 156 | **0.444** | 1.000 |

**The large model is the best on hand-written cases and the worst on real
crawled text.** That is exactly the failure a small hand-written set is prone to
hide: it is better at the sentence shapes someone thought to write down and
worse at the ones the web actually produces. It also costs 5.2x the memory, in
a request path, with a second copy running in the crawler.

The spread across all three is within the noise of a 45-sentence sample, so no
switch is justified on this evidence. The small model stays, now behind
`BRAIN_SPACY_MODEL` so that revisiting it is a setting rather than a code change
plus two Dockerfile edits.

### What the measurement actually found

More useful than the model comparison itself: **recall is already saturated at
1.000 on every model, and precision is the binding constraint.** The extractor
is finding everything it should and also things it should not.

No parser model fixes that, which is why swapping one would have been effort
spent in the wrong place. lex's real-text analysis named the causes, and half of
them are mine rather than the extractor's: fragments arriving from the discovery
layer — navigation chrome and a citation-stripping remnant — are non-clauses
that the parser then invents structure from. That is a `brain_discovery`
problem, and it is now the highest-value open item in extraction quality.

### Rejected

- **Switching to the large model.** Worse where it counts, most expensive.
- **Switching to the medium model.** Best real-text precision of the three, but
  the margin is roughly one false positive out of eight predictions on a
  45-sentence sample. Not distinguishable from noise, and it costs 2.5x the
  memory. Revisit if the gold set grows enough to separate them.

### Open questions

1. Discovery-layer fragments feeding the parser corrupted input. Mine to fix.
2. Whether md beats sm is unresolved rather than answered; the sample is too
   small to tell. Growing the real-text set would settle it.
3. Word sense induction has published evaluation protocols (SemEval Fuzzy
   B-Cubed, V-Measure) that apply to `brain_meaning.py` but need sense-labelled
   data this project does not have. Flagged by lex, still undecided.


## 2026-09-06 (session 9) — Both session-8 defects fixed; the evaluation replaced

**Status:** implemented and tested. 219 backend tests pass. Full
measurement detail (sampling strategy, inter-annotator agreement,
precision/recall trend) is in the new `docs/evaluation-log.md` — this entry
is the design summary.

### The two named defects

**"data" → "datum".** Not a naive stemmer (there wasn't one to replace —
`brain_nlp` already used spaCy's real morphological lemmatiser). Measured
~40 candidate irregular plurals over realistic sentences and found the
lemmatiser gets almost all of them right (matrix/matrices, thesis/theses,
child/children, mouse/mice, ...) — consolidating a plural onto its singular
is the *desired* behaviour there. Only five Latin/Greek loanwords
measurably misfire, where the "correct" classical singular is rare/archaic
or names a different sense: data, media, criteria, phenomena, trivia. Fixed
with a 5-word exception list keyed on the surface word the writer used
(`brain_nlp._IRREGULAR_PLURAL_SURFACE`), so a genuine singular use ("a
growth medium") is untouched.

**"Enzymes catalyse reactions" → nothing.** Confirmed the session-8
diagnosis: `en_core_web_sm`'s tagger mistags "catalyse"/"catalyze" as a
NOUN in a determiner-less, bare-plural-subject, present-tense construction.
Measured `sm` against `md` and `lg` on the gold set, corpus yield, load
time and peak memory. `md` does **not** fix it (same tagging error as
`sm`); only `lg` does, at 5.2x the memory and ~2.5x the per-sentence
latency, in a request path. **Not switched** — flagged to ammu/god as an
architectural fork with the numbers, per the assignment's own instruction
not to just swap it. See evaluation-log for the full table and reasoning.

### Two more defects, found (and fixed) via real-text sampling

Sampling real sentences for Task C surfaced two patterns no hand-written
test happened to cover:

- **Negation.** "The cyanobacteria did not generate oxygen" was extracted
  as if asserted. Fixed by reading spaCy's existing `neg` dependency label
  on the relation verb (`brain_nlp._is_negated`) — no new lexicon.
  Deliberately scoped to verb-local negation; negation on a governing
  clause and quantifier negation via a determiner ("almost no X") are named
  limitations, not fixed.
- **Passive voice with an expressed agent.** "Heat is caused by friction"
  produced nothing (the by-agent is spaCy's `agent` dependency label, not
  `prep`) and, once that's fixed naively, would have gotten the direction
  backwards (`nsubjpass` is the patient, not the agent).
  `brain_nlp._true_subject_object` now swaps roles when an agent is
  expressed; passives without one are unaffected.

### The evaluation, replaced

Session 8's 0.90-precision figure came from 15 sentences this project
wrote and labelled itself — a regression tripwire, not a measurement, and
it said so honestly at the time. This session: sampled 45 real sentences
from the stored corpus (stratified equally across its 3 pages, no quality
filtering), had an independent second annotator blind-label the same set,
computed Cohen's kappa (0.63, "substantial" agreement) between the two, and
now reports precision **and** recall against that held-out sample
separately from the hand-written set. The honest result: 0.50 precision on
real text versus 1.00 on the hand-written set — worse, as it should
plausibly be, with every false positive traced to a specific named cause
rather than left as unlabelled noise. Full detail: `docs/evaluation-log.md`.

### Rejected: fixing every gap the real-text sample found

The sample also surfaced governing-clause negation, quantifier negation,
and discovery-layer fragments (nav chrome, a citation-stripping remnant)
that confuse the dependency parser into inventing relations from
non-clauses. None of these were fixed this session — the first two are
harder problems than a well-scoped fix (full negation-scope resolution),
and the third is not this file's bug to fix (`brain_nlp` is doing the right
thing with corrupted input it was handed; the fix, if any, belongs in
`brain_discovery`'s prose/fragment filtering). Named in evaluation-log
rather than either silently left out or hastily patched.

### Word sense induction benchmarks — checked, not adopted

SemEval WSI tasks (Fuzzy B-Cubed / V-Measure against sense-labelled
corpora) are the established protocol and would apply to
`brain_meaning.py` in principle, but adopting one needs sense-labelled data
this project doesn't have, and `brain_meaning.py` itself was out of this
session's scope (`brain_nlp.py` and `backend/eval/*` only). Flagged as an
open fork for whoever next works on that file, not decided here.

### Open questions

1. Task A's model-size fork (`sm` vs `lg`) needs a decision from ammu/god,
   not another session assuming an answer.
2. Anaphora resolution: the second annotator's disagreements were entirely
   about resolving a relative pronoun ("which"/"that") back to its
   antecedent. The current pipeline doesn't attempt this anywhere. Worth a
   deliberate decision (in scope or explicitly out) rather than leaving it
   as an accidental gap.
3. Negation-scope across clause boundaries, and quantifier negation via a
   determiner, remain unfixed — named in evaluation-log, not silently
   dropped.
4. Growing the stored eval corpus (more pages, more source types) would
   let a future Task-C-style sample grow past 45 sentences / 3 pages
   without re-deriving a sampling strategy from scratch.

## 2026-09-06 (session 8) — An evaluation harness, and the first two defects it found

**Status:** implemented and tested. 206 backend tests pass.

### Why this came before more features

Everything in this pipeline was tuned by looking at one or two pages. The unit
tests prove specific behaviours still work, but nothing could answer the
question that actually matters when changing a threshold: *did that help?*
Without a number that moves, every future change is guesswork, and the cost of
adding this only grows with the codebase.

### What it measures

`python -m backend.eval.run_eval`, over a fixed corpus of three real pages
stored compressed in the repository:

- **Yield per page** — what structure was discovered, how much readable text
  came out, how many references, and how many concepts and relations the
  extractor produced. These say whether a change made the brain read more of a
  page or less of it.
- **Relation quality** — precision, recall and F1 against hand-labelled
  sentences in `gold_relations.py`. Yield can always be raised by accepting
  noise, so it means nothing without precision beside it. The labels include
  sentences that must yield *nothing*: a graph full of "X is Y" cannot answer
  anything, so silence is a correct answer that gets checked for.

The corpus is stored rather than fetched because an evaluation that hits the
network measures the network. Pages change and sites rate-limit, so two runs
would stop being comparable and the only thing that should move the numbers is
a change to the code.

### The baseline, first recorded

| page | sentences | text | links | concepts | relations |
|---|---|---|---|---|---|
| arxiv_attention | 18 | 5,085 | 17 | 2 | 1 |
| stanford_consciousness | 835 | 157,041 | 19 | 103 | 57 |
| wikipedia_photosynthesis | 582 | 129,592 | 50 | 127 | 88 |

Relation extraction: precision 0.90, recall 0.82, F1 0.86 over 15 cases.

`backend/tests/test_eval_baseline.py` compares a fresh run against this and
fails if quality drops or yield collapses. Tolerances are loose deliberately: a
tripwire that fires on harmless changes gets switched off. **The guard was
verified by deliberately degrading the prose filter and confirming it failed
with the specific numbers that moved**, then reverting. An untested tripwire is
worthless.

### Two real defects the harness found immediately

1. **"data" is stored as "datum".** The lemmatiser normalises it, so the graph
   node is `datum`. This is internally consistent — a question about data
   normalises the same way, so lookup still works — but it is user-visible: the
   brain will say "Encryption drives datum." Every irregular plural has this
   problem.
2. **"Enzymes catalyse reactions" yields nothing.** A perfectly ordinary
   scientific statement produces no relation at all, so sentences like it are
   invisible to the graph. Worth investigating whether it is the verb, the
   spelling, or the parse.

Neither was fixed in this session. They are recorded because the harness
existing is what makes them visible at all, and because fixing them now would
mean changing extraction and the measuring instrument in the same commit.

### Also confirmed, quantitatively

The arXiv abstract page yields 2 concepts and 1 relation from 18 sentences.
That page is almost worthless to learn from, which matches the qualitative
finding in session 6 that it is mostly navigation. It stays in the corpus
precisely because a page with little to offer is a case discovery has to
survive.

### Honest limitations

- The gold labels are my own judgement, not an independent annotator's, so the
  quality figure measures agreement with one reading rather than objective
  truth. The pairs also use the extractor's own lemmatised form, which builds
  in its normalisation.
- The cases were written for the purpose rather than sampled from crawled
  text, so they under-represent how messy real sentences are.
- Nothing here measures the graph, convergence, or answer quality, because
  those need a populated database. This covers discovery and extraction only.

Both limitations are exactly the kind of thing a person with an information
retrieval background would fix properly, and they are the reason the numbers
above should be read as a regression instrument rather than a score.

## 2026-09-05 (session 7) — The curiosity loop now closes on itself

**Status:** implemented and tested. 201 backend tests pass.

### The last open loop

Curiosity detected gaps, queued reading, and never checked whether reading
helped. That is an open loop: the brain would go on making a losing bet
indefinitely, because nothing could tell a bet that pays from one that does not.

Three kinds of bet are now kept apart, because they are genuinely different
wagers with different odds: the graph had nothing on a concept, the brain
inferred something and wants to verify it, or a concept was named on thin
evidence. `measure_effectiveness` reports, per kind, how many reads completed,
how many taught the brain anything, and the resulting rate. `select_gaps` then
stops acting on a kind whose reads have reliably yielded nothing.

Two safeguards, both tested. A kind with too little history is always kept, so
a new one is never killed by one bad read. And with no measurements at all the
behaviour is exactly as before, so an unmeasurable loop falls back to acting
rather than stopping.

### No new table, and no touching someone else's work in progress

The obvious design was an outcomes table. Rejected on two grounds. The data
already exists: the crawler carries a frontier entry's `source_type` through to
its visited-page record, so every completed read is on file with how many
sentences it produced. Appending the reason after a colon
(`curiosity:derived`) makes that record attributable, and the measurement
becomes a read over history the pipeline was already keeping.

The second reason is practical and worth writing down. Adding a model means
editing `backend/models.py` and `backend/database.py`, both of which carry
Sanju's uncommitted work. Committing a schema change would have meant
committing their unfinished work alongside it. A design that needs no schema
change avoided the conflict entirely.

### Correction to an earlier expectation

Partitioning graph edges by sense is **rejected, not pending** — recorded here
because it was still being tracked as upcoming. Cluster identity is not stable
as contexts accumulate, so an edge tagged today can denote a different sense
after more reading, and edges already written have no migration. Answer-time
filtering (session 5) reads the current clustering every time and is therefore
always consistent with what the brain currently believes.

### Open questions

1. `measure_effectiveness` runs on every ask. It is one grouped aggregate over
   a small table, but if the visited-page table grows large it should be cached
   for a few minutes rather than recomputed per request.
2. The thresholds — what counts as a useful read, how much history a reason
   needs — are reasoned defaults, not calibrated against real crawl data the
   way the sense threshold was. They should be revisited once the crawler has
   run long enough to produce a real distribution.
3. Wikipedia's table-of-contents text still reads as prose.

## 2026-09-05 (session 6) — Wikipedia access fixed by compliance; discovery hardened on real pages

**Status:** 195 backend tests pass.

### The 403 was a missing contact, not a block to route around

Every Wikimedia request returned 403 with a 141-byte pointer to their robot
policy, through the API as well as the HTML. The cause was the User-Agent: it
described the crawler but gave no way to reach whoever runs it, which their
published policy requires. Adding a contact returns 200 immediately.

A contact URL satisfies the policy on its own, so the default carries no
personal address; `BRAIN_CONTACT` lets an operator point it at themselves,
which is right since it is their deployment doing the fetching. Both the
crawler and the on-demand path now share one header set.

**Rejected: proxying or disguising the crawler to evade the block.** It would
have meant circumventing an access control the site publishes and enforces
deliberately, and it was unnecessary — the site documents exactly what it wants
and honouring that works. Wikimedia also offers bulk dumps for volume, which is
the right route if reading ever outgrows polite crawling.

### Two defects in discovery that only real pages exposed

Earlier validation used clean sources. A live Wikipedia article broke both, and
both were fixed from measurements rather than guesses.

**Sentence boundaries were being learned from navigation.** Scoring candidates
by how often a byte precedes a capital picked a navigation arrow (105
occurrences, 91% rate) over the full stop (2360 occurrences, 29% rate), because
the page also carries scripts and menus where a full stop is followed by
anything. Candidates are now scored on evidence *and* lift over the document's
own base rate, so a page of prose and a page of markup are each judged on their
own terms. The full stop now wins on both Wikipedia and Stanford.

**Script and data were being read as prose.** Code between a script's opening
and closing tags is not itself inside a markup span, so it survived separation
and became "sentences". Statements are now required to be mostly ordinary
words, which removes it without naming scripts, data formats or any element.
Wikipedia went from opening with `(function(){var className=...` to real text.

### Measured limitation, not fixed

On a page that is mostly navigation with little prose — an arXiv abstract page
is 5KB of extracted text, largely menus — boundary discovery has little to work
with. Its base rate of capitals-after-punctuation is 0.36, so almost anything
precedes a capital and the evidence is genuinely uninformative; brackets score
above the full stop. This behaviour predates this session's changes and is not
a regression. The mitigations are that non-prose statements are now discarded
and that the graph's own statistical floor filters what survives.

Wikipedia's table-of-contents text still reads as prose, because it *is*
word-like and telling it apart needs element context the discovery layer
deliberately does not have.

### Known cosmetic issue

An escaped ampersand in an address survives into the resolved URL
(`...&amp;redirect=no`). Decoding it would mean teaching the fetch path one
markup language's escape table, which is the class of assumption this layer
exists to avoid. Flagged rather than silently hardcoded; the address still
resolves.

## 2026-09-05 (session 5) — Senses now change the answer, not just label it

**Status:** implemented and tested. 193 backend tests pass.

### The gap this closes

Sense detection landed last session but was decorative: the answer could say
which meaning of a word was intended and then draw its evidence from the
single-sense graph anyway. Asking about the emotional sense of "fire" still
came back talking about oxygen and fuel.

`brain_meaning.sense_vocabulary` returns the words surrounding one sense, and
`brain_answer` intersects the graph's neighbours with it. Narrowing never
empties an answer: a sense whose vocabulary does not overlap the graph is a
reason to be less certain which meaning applies, not a reason to claim
ignorance of a concept the brain has read. `answer.senseFiltered` says whether
it happened.

### Rejected: partitioning the graph by sense

The obvious alternative was tagging every edge with the sense it came from.
Rejected because cluster identity is not stable as contexts accumulate — an
edge written today as sense 1 can denote a different sense once more reading
shifts the clusters — and there is no migration for edges already written.
Filtering at answer time reads the current clustering every time, so it always
agrees with what the brain currently believes, and needs no schema change.

### Three real defects found and fixed in the clustering

Found by measuring rather than assuming, and each one was silently wrong:

1. **Over-splitting.** The old rule took the largest split clearing a floor.
   Splitting further always tightens groups a little — arithmetic, not meaning
   — so every concept was driven to the maximum and one real sense came back
   as several fragments.
2. **Arbitrary seeding.** The first centre was simply the first stored context,
   which anchors the whole clustering on an arbitrary sentence. Two real
   meanings split nine-against-three. The first centre is now the context
   furthest from the average.
3. **The selection criterion could not discriminate at all.** Measured: mean
   spread improvement scored one meaning (0.12) *higher* than two genuine ones
   (0.11). Silhouette was no better, scoring a single meaning 0.126 against
   0.125 for two. Both would have accepted or rejected the wrong thing.

### What replaced it: a test against chance

The question "two meanings, or one meaning cut in half?" is answered by asking
whether the grouping beats chance. The same group sizes are assigned at random
many times to build a null distribution, and the real split is scored in
standard deviations below it. Measured: one meaning scores up to about 2.5, two
genuine meanings score near 5. The floor sits at 3.5, in the gap.

This is the same kind of test the graph already applies to edges, where a
co-occurrence must beat chance before it counts as a dependency. The threshold
is calibrated against measurements recorded above, not guessed, and the null is
drawn with a fixed seed so the brain never disagrees with itself about what a
word means between calls.

The smallest k that clears the floor wins, not the best-scoring one: two real
meanings and three fragments of them score almost identically, and reporting
three would shred a real sense for nothing.

### Open questions

1. The clustering signal is genuinely weak at small context counts. A concept
   needs a fair amount of reading before senses separate reliably. This is a
   property of the data, not a bug, but it means senses appear late.
2. Curiosity still has no feedback signal.
3. `answer.senseFiltered` is not yet rendered by the frontend.

## 2026-09-05 (session 4) — Source discovery replaces every hardcoded parser; meaning layer added

**Status:** implemented and tested. 186 backend tests pass.

### The charter is now actually met in the fetch path

This was the project's defining constraint and the code violated it everywhere.
Removed: Wikipedia's `#mw-content-text` container and `/wiki/` link prefix,
arXiv's `blockquote.abstract` and `/abs/`, a generic fetcher keyed to HTML's
`<p>` element with a fixed strip-list, a citation regex, a sentence splitter
keyed to `.!?` (in two places), fifteen hardcoded seed URLs, a source-type to
fetcher dispatch table, the MediaWiki opensearch API contract, and a fallback
that guessed addresses by title-casing a term and joining it with underscores.

**`backend/services/brain_discovery.py`** (new) discovers, per document:

- **Markup delimiters**, by scoring candidate byte pairs on three structural
  properties: the opener leads, the enclosed material is less space-dense than
  the text around it, and the pair opens about as often as it closes. Ranked by
  bracketing consistency, with enclosed volume breaking ties.
- **Prose**, as whatever falls outside the discovered spans.
- **Sentence boundaries**, as the bytes that statistically precede a
  whitespace-then-capital transition. English yields `.`, `?`, `!` from
  evidence.
- **References**, as URI-legal runs that resolve against the document's own
  address, then narrowed two ways: a run that IS the whole span is a bare name
  (`</div>` reads as the path `/div`), and a reference a document offers a
  reader carries readable text, which is what separates content links from
  stylesheets and scripts without naming a file type.

`brain_fetchers` is now one `fetch` for every source. `brain_crawler` starts
from a single `BRAIN_START_URL` and finds everything else by following what
documents point at. `brain_learn.resolve_source` finds a page for a term by
*reading a search page with the same discovery*, with the search address in
`BRAIN_SEARCH_URL` — configuration, not logic.

### Proof it is discovery and not a hidden HTML parser

The tests feed it **formats that do not exist**: `|`/`~` for markup and `§` for
sentence boundaries. Delimiters, prose, boundaries and references all come back
correctly. A parser in disguise returns nothing on those.

Validated live against real pages too. Stanford Encyclopedia yields 887 real
sentences and real article references (`/entries/qualia/`,
`/entries/consciousness-representational/`); arXiv yields real paper references.
Neither has a line of site-specific code behind it.

### The meaning layer (Function 7 step 3)

**`backend/services/brain_meaning.py`** (new) discovers word senses from
context. Every sentence a concept was extracted from is kept, embedded and
clustered; each cluster IS a sense. The number of senses comes from the spread
of the data, and a split is only accepted when it tightens the contexts by a
real margin over not splitting, so an unambiguous word stays single rather than
being fragmented. Senses are labelled by the words that distinguish them from
the concept's other senses, which needs no dictionary.

Tested against real embeddings, not mocks: "fire" used physically and
emotionally separates into two senses, and a question about fuel and oxygen
reaches a different sense than one about passion and conviction. The answer now
reports which sense it settled on.

### Decisions

- **ChromaDB over pgvector.** Already declared in `pyproject.toml` but never
  installed or used. It bundles a real local embedding model, so there is no
  API key, no second service to run, and no network at answer time — which the
  zero-internet-at-answer-time constraint requires. pgvector would have needed
  a database extension plus a separate embedding stack.
- **k-means on numpy** rather than adding scikit-learn for one algorithm.
  Seeded deterministically by furthest-point, so the same store always yields
  the same senses instead of shifting between runs.
- **Sub-delimiters excluded from reference paths, admitted after `?`.** The
  RFC's own query grammar. Without the exclusion `href='/a/b'` reads as one
  address starting with the attribute name; without the re-admission
  `/search?entry=1234` truncates and every result resolves to the same address.

### Honest boundaries, stated rather than hidden

- The RFC 3986 character set and relative-reference resolution are used
  deliberately. Those define the transport, not any site's conventions.
- `BRAIN_SEARCH_URL` still has to name *somewhere* to start. That is
  irreducible: something must say where the brain begins. It is configuration
  with a default, and no response format is assumed behind it.
- `brain_query._WH_INTENT` (two entries) and `brain_nlp`'s connective tables
  remain the only predefined linguistic rules left, both flagged in-line.

### Operational finding

**Wikipedia returns 403 to this network for every user agent tried**, serving a
141-byte robot-policy stub. The old pipeline would fail identically; this is not
caused by the rewrite. Live resolution was therefore validated against Stanford
and arXiv instead. Because the source is now configuration, pointing the brain
at a reachable search endpoint is a config change rather than a code change.

### Open questions

1. Senses are discovered and reported but do not yet partition graph edges, so
   the graph remains single-sense. Sense-tagged edges are the next real step.
2. Curiosity still has no feedback signal: it never learns whether reading a
   queued concept improved later answers.
3. The `sense` field on the answer is not yet rendered by the frontend.

## 2026-09-05 (session 3) — Built: curiosity loop + single-topic convergence

**Status:** implemented and tested. 153 backend tests pass.

### Function 8 — the loop now closes

AKKI_FULL_ARCHITECTURE.md describes the cycle as
`Question -> Answer -> Gap -> Read -> Better Answer -> Better Gap Detection`.
Every arrow but the third existed. `/ask` detected gaps and dropped them, so
the brain could say "my picture of this is thin" and never act on it.

**`backend/services/brain_curiosity.py`** (new) turns what an answer was least
able to stand behind into entries on the crawl frontier the background crawler
already drains. Ranked by weakness:

1. The concept asked about, when the graph had nothing solid on it.
2. **Derived links** — the brain's own 2-hop inferences that no source stated.
   Queueing these is what makes the loop self-correcting rather than
   self-confirming: it goes and checks its own guesses.
3. Concepts named in the answer resting on very few observations.

Two properties held deliberately. Selection is pure and reads only the
already-composed answer, and queueing runs *after* the response is streamed, so
"zero live internet at answer time" still holds and the answer gains no
latency. Only concepts the answer actually named can be queued, and the batch
is capped so curiosity trickles — the crawler's own seeding comment records
that a flood once drowned the knowledge sources.

A new `curious` SSE stage reports what it decided to go read.

### Function 7 step 5 now applies to every question

Convergence previously ran only for questions naming two or more concepts, so
the capability the architecture doc calls "the moment of intelligence" was
unreachable from the commonest kind of query. For a single topic, its own
strongest branches are used as the independent origins; a concept several of
them reach is a hub nothing stated directly. Seeds come from edges already
fetched, so it costs no extra neighbour lookup, and a seed or the topic itself
turning up is filtered out as circular rather than reported as a finding.

A real multi-origin convergence now outranks a 2-hop derived link for the
volunteered remark, since being reached from several independent branches is
stronger evidence than any single inferred path.

### Bugs found and fixed

- **"dark matter" was being looked up as "matter".** spaCy's noun chunker fails
  on the predicate of a question — for "what is dark matter" the only chunk it
  finds is "what" — so the writer's normalizer fell back to the bare head noun.
  The article that taught the concept stored "dark matter", so this was a
  guaranteed miss on a concept the brain genuinely knew. The parse still
  carries the dropped information as an adjectival-modifier label, so the
  phrase is rebuilt from dependency labels. This narrows the gap between the
  query and writer normalizers rather than widening it.
- **Dangling pronoun.** With no incoming edges the summary opened "It drives
  galaxy", a pronoun with no antecedent. The topic is named instead.

### Alternatives rejected

- **Queueing concepts rather than URLs.** The frontier is URL-keyed and the
  crawler consumes URLs, so this would have meant a schema change. Resolution
  is injected into `queue_reading` instead, keeping the module free of any one
  site's conventions even though the current caller passes a Wikipedia resolver.
- **Deeper single-topic convergence.** The origins start out related to each
  other, so a long walk finds trivial common ground. Depth is kept short.

### Hardcoded assumptions (charter status)

- **Flagged in-line, inherited not new:** `brain_curiosity.queue_reading`
  builds a URL from a resolved title. That is a predefined URL convention, the
  same one `brain_learn` already applies. The resolver is injected so this call
  site changes when the fetch layer learns to discover sources by pattern.
- Unchanged: `brain_query._WH_INTENT`, `brain_nlp` connective tables,
  `brain_learn` Wikipedia hardcoding.

### Open questions

1. Nothing yet reads the `curious` stage on the frontend.
2. Curiosity has no feedback signal — it does not learn whether reading a
   queued concept actually improved later answers.
3. Word-sense disambiguation still needs the vector layer. Single-sense.
4. `client/src/brain3d/useAskStream.ts` contract doc is stale: `thinking`
   carries `plan`, `answer` carries `answer`, and there is now a `curious`
   stage. Owned by whoever holds that file.

## 2026-09-05 (later) — Built: query understanding + answer formation

**Status:** implemented and tested. 137 backend tests pass. Human approved the
direction ("make it feel like Jarvis") and asked for the call to be made.

### The decision that shaped it

The user asked for something that feels like a real AI rather than a lookup
tool. The tempting reading is "make it speak in fluent prose", which in practice
means a language model writes the answer text. That was rejected, and not only
because two documents forbid it. Fluent paragraphs are the cheapest and least
distinctive part of the effect: any chatbot produces them, and routing the
answer through a model would mean the model is doing the thinking while the
graph becomes decoration.

What actually reads as intelligence here is the part that is genuinely the
brain's own: it learns live when it hits a gap, it derives links no source
stated, it volunteers a connection nobody asked about, and it admits what it
does not know. All of that is graph-native. So the answer speaks in confident
first person, and every sentence is composed from edges that exist.

A narrator model could later rephrase `summary` while being forbidden to add a
fact. Nothing in `brain_answer` would need to change. That remains open.

### Built

- **`backend/services/brain_query.py`** (new). Parses a natural question into
  `QueryPlan{intent, topics}` using the spaCy pipeline `brain_nlp` already
  loads. No new dependency, no model call. Topics go through the graph
  writer's own normalizer, so a term from a question is spelled exactly like
  the node key stored when that concept was learned.
- **`brain_service._top_dependencies`** (new). The reversed traversal. Edges
  were always directed but only ever read outward, so "what X depends on" was
  unreachable. One Cypher query with the arrow flipped.
- **`backend/services/brain_answer.py`** (new). Composes Function 7 step 6:
  `dependsOn`, `produces`, `convergences`, `derived`, plus a spoken `summary`,
  an unprompted `observation`, an honest `gap`, `confidence`, and `provenance`.
- **`/api/brain/ask`** now parses before querying, routes by intent, and
  carries provenance that was previously computed and discarded.
- **`BrainAskRequest.query`** added alongside `concept`. Both optional,
  `query` wins. Posting a bare concept behaves exactly as before.

### Direction is read from grammar, not vocabulary

`brain_nlp` already knows which verbs run cause-to-effect and which run
dependent-to-prerequisite, and uses that to orient every edge it writes. The
same tables applied to the question say which way to travel, based on the
dependency role the user's concept occupies:

    "what causes inflation"       -> concept is the OBJECT   -> read in-edges
    "what does inflation cause"   -> concept is the SUBJECT   -> read out-edges
    "what does encryption require"-> BACKWARD verb, subject   -> read in-edges

Identical vocabulary, opposite traversal. `test_causal_pair_disagree_on_direction`
asserts exactly that, and it is the test a question-word map cannot pass.

### Alternatives rejected

- **Language model for intent parsing or answer text.** See above.
- **Re-querying out-edges inside the composer.** The endpoint has already read
  them to decide whether to learn. Re-reading wastes a round trip and can
  return something different, which would leave the spoken answer disagreeing
  with the evidence list printed beside it. Caller now hands them in.
- **Changing `associations` / `inferred` in the SSE payload.** The 3D scene
  consumes them and was under concurrent edit. Everything new is additive.

### Bugs found and fixed while building

- A rare word the parser does not tag as a noun produced no topic at all, so
  the whole question stood in as the concept and the brain answered "I don't
  know what is quasicrystal". Grammar words are now stripped and the remainder
  used as the subject.
- `gap` and `confidence` were computed from different thresholds, so an answer
  could report strong confidence and "still thin" in the same breath.
- Spoken sentences opened lowercase because concept names are stored lowercase.

### Pre-existing defects found (fixed / flagged)

- **Fixed:** `sse-starlette` is imported by the ask endpoint but was never
  declared in `pyproject.toml`, so a clean install would import the app and
  then fail at request time. Its three endpoint tests were erroring on
  collection before this session began. Declared and installed.
- **Flagged, not fixed:** `neo4j`, `spacy` and `httpx` are also imported and
  installed but undeclared. The dependency list is systematically incomplete.
- **Flagged:** the test suite needs `DATABASE_URL` set to import at all, and
  there is no `conftest.py` providing one. Every backend test errors on
  collection in a clean shell.

### Hardcoded assumptions (charter status)

- **New, flagged in-line:** `brain_query._WH_INTENT`, a two-entry table mapping
  "why" and "how". Morphology cannot separate "why X" from "what X". It is the
  only lexical table in the query path, isolated so it can be swapped for a
  learned classifier. Same class as the existing `FORWARD_CONNECTIVES`.
- **Pre-existing, unchanged:** `brain_nlp` connective tables; `brain_learn`
  hardcoding Wikipedia and a title-cased URL guess.

### Open questions

1. Narrator model allowed to rephrase but not to add facts? Deferred, safe to.
2. Word-sense disambiguation (Function 7 step 3) still needs a vector layer
   that does not exist. Answers are single-sense.
3. The SSE contract documented in `client/src/brain3d/useAskStream.ts` is now
   stale: `thinking` carries `plan`, and `answer` carries `answer`. Left for
   whoever owns that file, since it was under concurrent edit.
4. Gap admissions are surfaced but not yet fed into the crawl frontier
   (Function 7 step 8).

## 2026-09-05 — Scoping: `/api/brain/ask` query understanding + answer formatting

**Status:** design proposal only. No code written. Awaiting sign-off on three questions.

### What already exists (do not rebuild)

The learn-on-demand path is built and verified live: Wikipedia crawl-on-miss →
Neo4j upsert → `infer_links` 2-hop reasoning → SSE answer stream.

| Capability | Where | Reached from `/ask`? |
|---|---|---|
| Direct associations (out-edges) | `brain_service._top_associations` | yes |
| 2-hop derived links | `brain_service.infer_links` | yes |
| 2-concept convergence | `brain_service.discover` | **no** |
| Multi-origin convergence | `brain_service.discover_convergence` | **no** |
| In-edges ("what X depends on") | *not implemented* | n/a |

### Design intent already on record

`AKKI_FULL_ARCHITECTURE.md` lines 307–332, **"Function 7 — Answer Formation"**,
specifies both query understanding and answer shape. It is not referenced by the
learn-on-demand plan or spec. Any work in this area should implement Function 7
rather than invent a design.

Function 7 step 6 defines the answer schema directly: what the concept depends
on, what it produces, hidden convergences from unrelated origins, and connections
nobody usually makes. Each maps onto an existing or near-existing graph op
(in-edges / out-edges / `discover_convergence` / `infer_links`).

### Gaps found

1. **No query parsing exists.** `BrainAskRequest` (`backend/schemas.py:153`) has a
   single field, `concept: str`. `backend/main.py:3958` lowercases the whole
   string and uses it as a Neo4j node key, so a full question sentence becomes a
   literal node lookup and then a verbatim Wikipedia opensearch term.
2. **Direction is stored but never read backwards.** Edges are genuinely directed
   (`brain_nlp` derives subject→object from the dependency parse), but
   `_top_associations` only ever matches `(a)-[r:CO_OCCURS]->(b)`. Half the
   causal information in the graph is unreachable. One reversed Cypher query
   unlocks it — the cheapest high-value fix in this area.
3. **Provenance is discarded.** `learn_concept` returns `sources`; the `/ask`
   generator uses only `new_concepts` and `new_edges`. The brain cannot cite what
   it just read.
4. **No answer formatting layer.** The answer event is a raw bag of
   `{word,g2,count}` + `{concept,via,strength}`; `client/src/pages/brain.tsx:378`
   renders the summary as literally "N associations, M inferred links".

### Alternatives considered and rejected

- **LLM for query intent parsing / prose answers.** Rejected as a routine choice.
  The design spec §3 lists "Any LLM in the answer path" as an explicit non-goal,
  and `AKKI_FULL_ARCHITECTURE.md` says "Never asks LLM after Phase 1". Adopting it
  reverses two documents and requires explicit human sign-off, so it is raised as
  an open question rather than decided.
- **A new NLU dependency.** Rejected — spaCy is already loaded by `brain_nlp`.
  Reusing it costs nothing and keeps query-term normalization identical to the
  normalization used when writing node keys, which currently can silently mismatch.
- **Breaking the existing `associations` / `inferred` arrays into a new shape.**
  Rejected — the 3D scene consumes them and `brain3d` was under concurrent edit.
  Any new answer structure must be additive; `useAskStream` ignores unknown keys.

### Hardcoded assumptions that violate the project charter (flagged, not fixed)

- `backend/services/brain_learn.py` hardcodes Wikipedia as the sole source
  (`_OPENSEARCH_URL`, `fetch_wikipedia`) **and** hardcodes a URL format — a
  title-cased guess turning `quantum tunneling` into `Quantum_Tunneling`. This is
  both a hardcoded seed and a hardcoded URL format.
- `backend/services/brain_nlp.py` hardcodes `FORWARD_CONNECTIVES`,
  `BACKWARD_CONNECTIVES`, and `_SKIP_VERBS` — predefined linguistic rules rather
  than direction discovered from position statistics.
- Consequence: the charter is already violated in-tree, so "no hardcoded rules"
  is currently an aspiration, not an invariant. Worth an explicit ruling before
  more rule tables are added.

### Open questions

1. Should the spoken answer be a deterministic sentence composed from graph edges
   by template, or fluent prose (which in practice requires an LLM and reverses a
   stated non-goal)?
2. Function 7 step 3, "determine which meaning cluster is being asked about",
   needs the vector/meaning layer (pgvector or ChromaDB). It does not exist; the
   graph is single-sense per word. Defer, or build it now?
3. Intent classification needs some interrogative signal. spaCy morphology
   (question tag, root verb lemma, wh-token POS, noun-chunk count) avoids literal
   word lists but leans on a pretrained parser. A hardcoded question-word map is
   simpler but is exactly what the charter forbids. Which side?
4. `AKKI_INTERNET_BRAIN.md` is referenced by the agent task brief but does not
   exist in the repo. Is `AKKI_FULL_ARCHITECTURE.md` the authoritative document,
   or is there a separate one?
