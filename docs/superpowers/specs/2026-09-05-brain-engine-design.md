# AKKI Brain Engine — Design Spec (v2, production-grade)

Date: 2026-09-05
Status: Approved by user, pending implementation plan
Supersedes: the v1 draft earlier in this file (Postgres-only, regex extraction,
raw PMI) — kept here as history below the v2 design, since the user asked for
a genuinely production-grade system rather than a hardened prototype.

## Problem (unchanged from v1)

`brain/` (repo root) contains a personal research prototype exploring a
non-LLM "dependency convergence" theory of intelligence. The user confirmed
this should become a real AKKI capability — its own feature, alongside the
existing Gemini-backed chat, not a replacement for it — and, after seeing
three separate and partly incompatible aspirational docs in that folder
(`AKKI_CORE_THEORY.md`, `AKKI_BUILD_PLAN.md`, `AKKI_FULL_ARCHITECTURE.md` /
`AKKI_INTERNET_BRAIN.md`), asked for the genuinely buildable, legitimate,
production-grade pieces of that ambition — not the "discover language from
raw bytes with zero assumptions" research program, which isn't realistically
achievable at this scope.

## What "production-grade" means here, concretely

Six specific upgrades over the v1 draft, each a real, well-established
technique — not aspirational hand-waving:

1. **Neo4j for the knowledge graph** (concepts + relationships), not
   relational tables — multi-hop traversal and convergence-finding are
   native Cypher queries, not hand-rolled SQL BFS. This is what
   `AKKI_BUILD_PLAN.md` and `AKKI_INTERNET_BRAIN.md` both call for, and
   they're right that it's the correct storage shape for this data.
2. **spaCy dependency parsing** for relationship extraction, replacing
   regex keyword-matching — real subject/verb/object structure instead of
   "grab the words after the string 'leads to'."
3. **Log-likelihood ratio (G², Dunning 1993)** instead of raw PMI for
   association strength — PMI is well-known to be unstable/inflated on
   low-frequency pairs (exactly what produced the earlier prototype's
   noisy "strongest connections" like `'anxious' ←→ 'surrogate'` off a
   handful of occurrences). G² is the standard fix in computational
   linguistics.
4. **Concurrent, rate-limited, robots.txt-respecting crawling** via
   `httpx.AsyncClient` (already a dependency), not single-threaded
   `requests`.
5. **Multiple real sources** (Wikipedia, arXiv abstracts, one news RSS
   feed) behind a common fetcher interface, not Wikipedia-only — each
   added as an explicit, scoped parser (this is what "reads more of the
   internet" concretely means; it does not mean discovering HTML format
   from raw bytes).
6. **Real production operational concerns**: retry/backoff, a dead-letter
   table for permanently-failing URLs, a health-check endpoint, and
   crawl-state bookkeeping that survives process restarts.

What this deliberately does NOT attempt (kept from the earlier honesty
check): discovering tokenization/grammar/meaning from raw bytes with zero
prior knowledge, full-internet unbounded crawling, distributed multi-machine
processing, or LLM-free natural language answer generation. Those remain a
documented future-phase wishlist, not part of this build.

## Storage architecture — hybrid, by data shape

- **Neo4j** — the knowledge graph itself:
  - `(:Concept {word, frequency, position_sum, position_count, first_seen})`
  - `(:Concept)-[:CO_OCCURS {count, g2, last_updated}]->(:Concept)` —
    directed edges (both `(a)->(b)` and `(b)->(a)` exist, matching how a
    sliding co-occurrence window naturally produces symmetric-ish counts;
    kept directed rather than merged so `g2`/`count` per direction can
    differ slightly at sentence boundaries, same as the original in-memory
    structure).
- **Postgres** (already the app's DB) — crawl *state*, which is queue/log
  shaped, not graph-shaped:
  - `brain_visited_pages(url PK, concept, source_type, sentences_learned, visited_at)`
  - `brain_frontier(url PK, concept, source_type, discovered_at)`
  - `brain_dead_letters(url PK, source_type, error, attempts, last_attempt_at)`
    — a URL moves here after 3 failed fetch attempts and is not retried
    automatically again.
  - `brain_stats(id="singleton", total_pages, total_sentences, updated_at)`

Rationale for the split: forcing crawl-queue bookkeeping into Neo4j (a
graph store) or forcing the concept graph into Postgres (relational) each
fights the natural shape of one or the other; using each store for what
it's good at is the standard production pattern, not added complexity for
its own sake.

## Relationship extraction (spaCy)

Per sentence (via `en_core_web_sm` — small, CPU-only, no GPU dependency,
suitable for a background crawler process):
1. Parse the sentence with spaCy's dependency parser.
2. Scan for a causal connective token (same signal vocabulary as before —
   "causes", "leads to", "because", "due to", "results in", "requires",
   etc.) and identify which clause it attaches to via the dependency tree
   (`token.head`), rather than a raw string split.
3. For each of the two clauses, extract its syntactic head via dependency
   labels (`nsubj`/`nsubjpass` for the subject, `dobj`/`obj`/`pobj` for the
   object) as the concept endpoint — a real noun phrase head, not "the next
   10 words after the keyword."
4. Assign direction from the connective's semantics: "causes"/"leads
   to"/"results in"/"produces" → clause1 depends_on nothing, clause2
   depends_on clause1 (clause1 → clause2); "because"/"due to"/"since"/
   "requires"/"depends on" → clause2 → clause1 (the clause containing the
   connective's object is the cause).
5. Emit one `(concept_a, concept_b, direction)` triple per matched
   sentence; these become `CO_OCCURS` edge upserts.

## Statistical scoring (G², log-likelihood ratio)

For a candidate pair (a, b), build the 2×2 contingency table from
corpus-wide counts already tracked in `brain_words`/`brain_cooccurrence`
edges: `count(a,b)`, `count(a, not b)`, `count(not a, b)`,
`count(not a, not b)` (derived from `brain_words.frequency` for a and b and
the total word-occurrence count in `brain_stats`). Compute:

```
G² = 2 * Σ observed_i * ln(observed_i / expected_i)   (over the 4 cells)
```

using the standard expected-value formula from row/column marginals. Store
`g2` on the edge alongside the raw `count`; `/api/brain/discover` ranks by
`g2` descending, not raw count — this directly fixes the small-sample
instability raw PMI had.

## Crawler (`backend/brain_crawler.py`)

Async (`httpx.AsyncClient` + `asyncio`), replacing the original
single-threaded `requests` loop:

- **Concurrency**: `asyncio.Semaphore(10)` bounds in-flight requests.
- **Per-domain rate limiting**: a `dict[domain, last_request_time]`
  enforces a minimum 1-second gap between requests to the same domain
  (independent of global concurrency) — politeness that scales with
  multiple sources, not just Wikipedia's tolerance.
- **robots.txt compliance**: `urllib.robotparser.RobotFileParser`, fetched
  and cached per-domain, checked before every fetch.
- **Retry/backoff**: transient failures (timeout, connection error, 5xx)
  retry up to 3 times with exponential backoff (1s, 2s, 4s); after 3
  failures, the URL is written to `brain_dead_letters` and dropped from
  the active frontier.
- **Source fetchers**, a small common interface —
  `async def fetch(url: str) -> tuple[str, list[str]]` (text, discovered
  links) — with one implementation per source:
  - `WikipediaFetcher` (existing logic from `run.py`, ported to `httpx`)
  - `ArxivFetcher` (arXiv abstract pages — abstract text + citing/cited
    paper links from the abstract page)
  - `RssNewsFetcher` (one configured news RSS feed — article text via the
    feed's linked pages + any outbound links found in the article body)
  Each frontier/visited-page row carries `source_type` so the crawler
  dispatches to the right fetcher.
- **Per page**: fetch → extract sentences → run spaCy relationship
  extraction → accumulate page-local word frequency / position / pair
  counts → one batched Neo4j `UNWIND ... MERGE` write for concepts and
  edges (accumulating `count` and recomputing `g2`) → insert into
  `brain_visited_pages` (Postgres) → insert newly discovered links into
  `brain_frontier` (`ON CONFLICT DO NOTHING`) → update `brain_stats`.
- **Graceful shutdown**: SIGINT/SIGTERM finishes in-flight page writes
  before exiting (same guarantee as the original `run.py`).

## Query API (new endpoints in `backend/main.py`, matching this codebase's
existing convention of routes living directly in `main.py`)

- `GET /api/brain/health` → checks Neo4j connectivity (`RETURN 1`) and
  Postgres connectivity; 200 if both reachable, 503 with which one failed
  otherwise.
- `GET /api/brain/status` → `{totalPages, totalSentences, conceptCount,
  edgeCount, frontierSize, deadLetterCount, updatedAt}` — `conceptCount`/
  `edgeCount` from Neo4j (`MATCH (c:Concept) RETURN count(c)` and the
  equivalent for `CO_OCCURS`), the rest from Postgres.
- `POST /api/brain/discover` → body `{concept: str, concept2: str | null}`:
  - **Single-concept**: Cypher `MATCH (a:Concept {word: $c})-[r:CO_OCCURS]->(b) RETURN b.word, r.g2, r.count ORDER BY r.g2 DESC LIMIT 20`.
  - **Two-concept (convergence)**: two variable-length Cypher queries
    (`MATCH (a:Concept {word:$c1})-[:CO_OCCURS*1..3]->(mid) RETURN mid.word, min(length(path))`,
    same from `$c2`), intersected in Python, sorted by combined depth
    ascending — the concrete, graph-native convergence query.
  - Unknown concept (not in the graph yet) → `{"error": "..."}"`, HTTP 200.

## Frontend (`client/src/pages/brain.tsx`)

Same shape as v1: a live status panel (polls `/api/brain/status`), a
query form (single- or two-concept mode), results as a ranked list showing
word, G² score, and which source(s) contributed. No graph visualization in
this version (still YAGNI — a visual graph is a legitimate separate
follow-up, not required for the core capability to be useful).

## Docker

- New `neo4j` service in `docker-compose.yml` (`neo4j:5-community`, ports
  7474/7687, `NEO4J_AUTH` from an env var, a named volume for its data —
  matching the pattern the `db` service already uses for `pgdata`).
- `brain-crawler` service (as in v1), now depending on both `db` and
  `neo4j` with `service_healthy` conditions; its Dockerfile installs
  `httpx`, `beautifulsoup4`, `lxml`, `spacy` (+ downloads `en_core_web_sm`
  at build time), `feedparser`, `neo4j` (the Python driver), `sqlalchemy`,
  `psycopg2-binary`.
- `backend`'s own Dockerfile/environment gains the Neo4j connection env
  vars so `/api/brain/*` endpoints can query it.

## Error handling

- Page fetch failure → retried per the backoff policy above, then
  dead-lettered — never silently dropped, never crashes the crawl loop.
- Neo4j or Postgres unavailable at crawler startup → crawler logs and
  retries connecting on an interval (doesn't crash-loop the container).
- `/api/brain/discover` for an unknown concept, or with Neo4j temporarily
  unreachable → clear `{"error": "..."}"` response, HTTP 200 for "unknown
  concept" (matches this codebase's tool-result convention) and a 503 for
  genuine connectivity failure (distinguishable from "just don't know that
  word yet").

## Testing

- Unit tests (no live Neo4j/Postgres/network): the G² formula, the spaCy
  relationship-extraction function (given a sentence, assert the expected
  `(concept_a, concept_b, direction)` triples — spaCy's small model is
  deterministic enough for fixed test sentences), the robots.txt check
  logic, and the retry/backoff state machine — all testable as pure
  functions with fixtures/mocks.
- Integration tests (against `docker compose up db neo4j`): insert known
  concepts/edges into a test Neo4j instance, call the discover logic
  directly, assert expected single-concept and convergence results.
- Manual crawler smoke test: run the crawler for a few minutes against the
  docker-compose `db`+`neo4j`, confirm nodes/edges appear in Neo4j Browser
  and `brain_stats` updates in Postgres.

## Out of scope (this iteration)

- No raw-byte/zero-assumption format discovery, no full unbounded internet
  crawling, no distributed multi-machine processing, no LLM-free answer
  generation — these stay as a documented future-phase wishlist per the
  earlier honesty discussion, not part of this build.
- No graph visualization in the frontend.
- No integration with the chat agent / LangGraph tool-calling core — this
  remains a standalone capability, per the user's earlier explicit choice.
- No change to the original `brain/` folder's prototype scripts.

---

## v1 draft (superseded, kept for history)

The original draft proposed Postgres-only storage (`brain_words`,
`brain_cooccurrence` tables), regex keyword-matching for relationship
extraction (unchanged from the existing prototype), raw PMI scoring, and a
single-threaded synchronous crawler reading Wikipedia only. All of that is
replaced by the v2 design above per the user's explicit request for a
production-grade system rather than a hardened prototype.
