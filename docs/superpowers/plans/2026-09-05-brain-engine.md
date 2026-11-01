# AKKI Brain Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production-grade AKKI Brain — a standalone, always-on capability (separate from the Gemini-backed chat) that continuously crawls real sources, extracts real dependency relationships via spaCy, scores associations with a proper statistical test (G²), stores the knowledge graph in Neo4j, and exposes it through a query API and a new frontend page.

**Architecture:** A dual-store design — Postgres holds crawl *state* (frontier queue, visited pages, dead letters, stats; already the app's DB), Neo4j holds the knowledge *graph* (concepts + weighted directed `CO_OCCURS` edges). An async crawler process (`backend/brain_crawler.py`, its own Docker service) fetches from three real sources (Wikipedia, arXiv, one news RSS feed) behind a common fetcher interface, respects robots.txt and per-domain rate limits, extracts relationships via spaCy dependency parsing (not regex), and batch-writes to both stores per page. Two new FastAPI endpoints query the graph directly via Cypher.

**Tech Stack:** Neo4j 5 (new service), spaCy (`en_core_web_sm`), httpx (async, already a dependency), SQLAlchemy (existing Postgres models), pytest/pytest-asyncio (added in the exploit-tools plan — reused here), React/TypeScript (existing frontend conventions), Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-05-brain-engine-design.md` (v2 — production-grade; read the v2 section, the v1 draft below it is superseded and kept only for history)

## Global Constraints

- Crawl-state (queue/log-shaped data) lives in Postgres; the knowledge graph (concept nodes + weighted edges) lives in Neo4j — never the reverse.
- Relationship direction convention, used consistently everywhere in this plan: a `(cause, effect)` pair means "cause leads to / produces effect" — equivalently "effect depends_on cause". The Neo4j edge is written `(:Concept {word: cause})-[:CO_OCCURS]->(:Concept {word: effect})`.
- Every network fetch goes through the shared robots.txt check and per-domain rate limiter — no source fetcher bypasses either.
- No source fetcher assumes a URL succeeds — every fetch failure path leads to retry-with-backoff, then a `brain_dead_letters` row after 3 attempts, never a silent drop and never a crash of the crawl loop.
- This is a standalone capability — no changes to the existing chat/agent pipeline, no new dependency from `backend/main.py`'s existing 104 endpoints on anything in this plan beyond the 3 new ones added here.

---

### Task 1: Postgres crawl-state models

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/database.py`
- Create: `backend/tests/test_brain_models.py`

**Interfaces:**
- Produces: `BrainVisitedPage`, `BrainFrontier`, `BrainDeadLetter`, `BrainStats` — all importable from `backend.models`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_brain_models.py`:

```python
"""Structural tests for the brain crawl-state models — no live DB required."""
from backend.models import BrainVisitedPage, BrainFrontier, BrainDeadLetter, BrainStats


def test_brain_visited_page_columns():
    cols = {c.name for c in BrainVisitedPage.__table__.columns}
    assert cols == {"url", "concept", "source_type", "sentences_learned", "visited_at"}
    assert BrainVisitedPage.__table__.columns["url"].primary_key


def test_brain_frontier_columns():
    cols = {c.name for c in BrainFrontier.__table__.columns}
    assert cols == {"url", "concept", "source_type", "discovered_at"}
    assert BrainFrontier.__table__.columns["url"].primary_key


def test_brain_dead_letter_columns():
    cols = {c.name for c in BrainDeadLetter.__table__.columns}
    assert cols == {"url", "source_type", "error", "attempts", "last_attempt_at"}
    assert BrainDeadLetter.__table__.columns["url"].primary_key


def test_brain_stats_columns():
    cols = {c.name for c in BrainStats.__table__.columns}
    assert cols == {"id", "total_pages", "total_sentences", "updated_at"}
    assert BrainStats.__table__.columns["id"].primary_key
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'BrainVisitedPage' from 'backend.models'`.

- [ ] **Step 3: Add the models**

Modify `backend/models.py` — insert these four classes at the end of the file (after the last existing class, `UserMarketplaceItem`):

```python
class BrainVisitedPage(Base):
    """A page the brain crawler has already fetched — crawl state, not
    knowledge; the extracted knowledge itself lives in Neo4j."""
    __tablename__ = "brain_visited_pages"

    url: Mapped[str] = mapped_column(Text, primary_key=True)
    concept: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    sentences_learned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrainFrontier(Base):
    """URLs discovered but not yet crawled."""
    __tablename__ = "brain_frontier"

    url: Mapped[str] = mapped_column(Text, primary_key=True)
    concept: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BrainDeadLetter(Base):
    """A URL that failed 3 fetch attempts — stops being retried automatically."""
    __tablename__ = "brain_dead_letters"

    url: Mapped[str] = mapped_column(Text, primary_key=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BrainStats(Base):
    """Single-row crawl-progress counter, avoids full-table scans on every status query."""
    __tablename__ = "brain_stats"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: "singleton")
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_sentences: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Register the models in `init_db()`**

Modify `backend/database.py` — change the model import block inside `init_db()` from:

```python
    from backend.models import (  # noqa: F401
        User, Session, Message, Document, Chunk, Memory,
        ToolRun, Finding, VoiceInteraction, WorkspaceRecord,
        Workflow, WorkflowStep, ReportSectionTemplate, ReportConfiguration,
        MarketplaceItem, UserMarketplaceItem
    )
```

to:

```python
    from backend.models import (  # noqa: F401
        User, Session, Message, Document, Chunk, Memory,
        ToolRun, Finding, VoiceInteraction, WorkspaceRecord,
        Workflow, WorkflowStep, ReportSectionTemplate, ReportConfiguration,
        MarketplaceItem, UserMarketplaceItem,
        BrainVisitedPage, BrainFrontier, BrainDeadLetter, BrainStats
    )
```

(If the exploit-tools plan's Task 3 has already run, this import list will also
contain `ToolAuditLog` — add the 4 brain models alongside it, not instead of it.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_models.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/models.py backend/database.py backend/tests/test_brain_models.py
git commit -m "feat(brain): add Postgres crawl-state models"
```

---

### Task 2: Neo4j connection service

**Files:**
- Create: `backend/services/neo4j_service.py`
- Modify: `backend/requirements.txt`
- Create: `backend/tests/test_neo4j_service.py`

**Interfaces:**
- Produces: `get_driver() -> AsyncDriver`, `async def ensure_schema() -> None`,
  `async def health_check() -> bool`, `async def close_driver() -> None` —
  all importable from `backend.services.neo4j_service`.

- [ ] **Step 1: Add the `neo4j` driver to requirements**

Append to `backend/requirements.txt`:

```text

# ── Brain Engine ──────────────────────────────────────────────────────────
neo4j>=5.24.0
spacy>=3.7.0
feedparser>=6.0.11
```

- [ ] **Step 2: Install locally**

Run: `.venv/Scripts/python.exe -m pip install neo4j spacy feedparser`
Expected: installs cleanly. (spaCy's model download happens in Task 4 — this
step only installs the library.)

- [ ] **Step 3: Write the failing test**

Create `backend/tests/test_neo4j_service.py`:

```python
"""Tests for the Neo4j connection service. Uses a fake driver/session so no
live Neo4j instance is required for this test — connectivity itself is
verified manually in Task 8's Docker smoke test."""
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services import neo4j_service


class _FakeRecord(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _FakeSession:
    def __init__(self, result):
        self._result = result

    async def run(self, *args, **kwargs):
        return self._result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _fake_driver(result):
    driver = MagicMock()
    driver.session.return_value = _FakeSession(result)
    return driver


async def test_health_check_true_when_driver_returns_ok():
    neo4j_service._driver = _fake_driver(_FakeResult(_FakeRecord(ok=1)))
    assert await neo4j_service.health_check() is True
    neo4j_service._driver = None


async def test_health_check_false_on_exception():
    driver = MagicMock()
    driver.session.side_effect = Exception("connection refused")
    neo4j_service._driver = driver
    assert await neo4j_service.health_check() is False
    neo4j_service._driver = None


async def test_get_driver_reuses_existing_instance():
    with patch.object(neo4j_service, "AsyncGraphDatabase") as mock_gdb:
        mock_gdb.driver.return_value = "driver-instance"
        neo4j_service._driver = None
        d1 = neo4j_service.get_driver()
        d2 = neo4j_service.get_driver()
        assert d1 == d2 == "driver-instance"
        mock_gdb.driver.assert_called_once()
    neo4j_service._driver = None
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_neo4j_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.neo4j_service'`.

- [ ] **Step 5: Write the service**

Create `backend/services/neo4j_service.py`:

```python
"""Connection management for the Brain Engine's Neo4j knowledge graph."""
import os
from neo4j import AsyncGraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

_driver = None


def get_driver():
    """Get or create the singleton async Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


async def ensure_schema() -> None:
    """Create the uniqueness constraint on Concept.word if it doesn't exist yet."""
    driver = get_driver()
    async with driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT concept_word_unique IF NOT EXISTS "
            "FOR (c:Concept) REQUIRE c.word IS UNIQUE"
        )


async def health_check() -> bool:
    """True if Neo4j is reachable and responds to a trivial query."""
    try:
        driver = get_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            return record is not None and record["ok"] == 1
    except Exception:
        return False


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_neo4j_service.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/neo4j_service.py backend/requirements.txt backend/tests/test_neo4j_service.py
git commit -m "feat(brain): add Neo4j connection service"
```

---

### Task 3: G² (log-likelihood ratio) association scoring

**Files:**
- Create: `backend/services/brain_stats_math.py`
- Create: `backend/tests/test_brain_stats_math.py`

**Interfaces:**
- Produces: `def log_likelihood_ratio(count_ab: int, count_a: int, count_b: int, total: int) -> float`, importable from `backend.services.brain_stats_math`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_brain_stats_math.py`:

```python
"""Tests for the G² (log-likelihood ratio) association-strength formula
(Dunning, 1993) — a pure function, no I/O."""
import math

from backend.services.brain_stats_math import log_likelihood_ratio


def test_returns_zero_for_any_zero_count():
    assert log_likelihood_ratio(0, 10, 10, 1000) == 0.0
    assert log_likelihood_ratio(5, 0, 10, 1000) == 0.0
    assert log_likelihood_ratio(5, 10, 0, 1000) == 0.0
    assert log_likelihood_ratio(5, 10, 10, 0) == 0.0


def test_perfectly_independent_pair_scores_near_zero():
    # a and b occur exactly as often together as chance alone predicts
    total = 10_000
    count_a = 100
    count_b = 100
    expected_ab = (count_a * count_b) / total  # = 1
    g2 = log_likelihood_ratio(round(expected_ab), count_a, count_b, total)
    assert g2 < 1.0


def test_strongly_associated_pair_scores_high():
    # a and b co-occur almost every time either appears — strong association
    total = 10_000
    count_a = 50
    count_b = 50
    count_ab = 48
    g2 = log_likelihood_ratio(count_ab, count_a, count_b, total)
    assert g2 > 50.0


def test_rare_pair_does_not_get_inflated_like_raw_pmi_would():
    # This is the exact failure mode raw PMI had in the original prototype:
    # two words that each appear only twice, and happen to co-occur once,
    # produce a huge raw-PMI score despite being statistically meaningless.
    # G² must NOT rank this above the strongly-associated pair above.
    total = 10_000
    g2_rare = log_likelihood_ratio(1, 2, 2, total)
    g2_strong = log_likelihood_ratio(48, 50, 50, total)
    assert g2_rare < g2_strong


def test_symmetric_in_a_and_b():
    total = 5000
    g2_ab = log_likelihood_ratio(20, 60, 40, total)
    g2_ba = log_likelihood_ratio(20, 40, 60, total)
    assert math.isclose(g2_ab, g2_ba, rel_tol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_stats_math.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.brain_stats_math'`.

- [ ] **Step 3: Implement**

Create `backend/services/brain_stats_math.py`:

```python
"""Statistical association scoring for the Brain Engine.

Replaces raw PMI (used by the original brain/ prototype) with the Dunning
(1993) log-likelihood ratio (G²) test, which does not get inflated by
low-frequency pairs the way raw PMI does.
"""
import math


def log_likelihood_ratio(count_ab: int, count_a: int, count_b: int, total: int) -> float:
    """G² log-likelihood ratio for the association between word a and word b.

    count_ab: number of times a and b co-occur
    count_a:  total occurrences of a in the corpus
    count_b:  total occurrences of b in the corpus
    total:    total word occurrences in the corpus
    """
    if count_ab <= 0 or count_a <= 0 or count_b <= 0 or total <= 0:
        return 0.0

    o11 = count_ab
    o12 = max(count_a - count_ab, 0)
    o21 = max(count_b - count_ab, 0)
    o22 = max(total - o11 - o12 - o21, 0)

    row1, row2 = o11 + o12, o21 + o22
    col1, col2 = o11 + o21, o12 + o22
    grand = row1 + row2

    if grand <= 0:
        return 0.0

    def expected(row_total: int, col_total: int) -> float:
        return (row_total * col_total) / grand

    cells = [
        (o11, expected(row1, col1)),
        (o12, expected(row1, col2)),
        (o21, expected(row2, col1)),
        (o22, expected(row2, col2)),
    ]

    g2 = 0.0
    for observed, exp in cells:
        if observed > 0 and exp > 0:
            g2 += observed * math.log(observed / exp)

    return round(2 * g2, 4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_stats_math.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/brain_stats_math.py backend/tests/test_brain_stats_math.py
git commit -m "feat(brain): add G2 log-likelihood association scoring"
```

---

### Task 4: spaCy dependency-parsing relationship extraction

**Files:**
- Create: `backend/services/brain_nlp.py`
- Create: `backend/tests/test_brain_nlp.py`

**Interfaces:**
- Produces: `def extract_dependencies(sentence: str) -> list[tuple[str, str]]`
  (each tuple is `(cause, effect)`, per the Global Constraints direction
  convention), importable from `backend.services.brain_nlp`.

**Important note on this task's process**: dependency-parse output for a
specific sentence can only be known by actually running spaCy on it — it
cannot be reliably hand-predicted. This task's first step is therefore to
run spaCy on the fixture sentences and inspect the real parse, THEN write
the test's expected values and the extraction logic from that real output —
not from a guessed parse tree. This is a deliberate, necessary deviation
from writing the test before any code exists.

- [ ] **Step 1: Download the spaCy model**

Run: `.venv/Scripts/python.exe -m spacy download en_core_web_sm`
Expected: downloads and installs the small English pipeline.

- [ ] **Step 2: Inspect the real dependency parse for each fixture sentence**

Run:
```bash
.venv/Scripts/python.exe -c "
import spacy
nlp = spacy.load('en_core_web_sm')
sentences = [
    'Fire causes heat.',
    'Heat leads to energy.',
    'The engine requires fuel.',
    'The city grew because of trade.',
    'Rust depends on moisture.',
]
for s in sentences:
    doc = nlp(s)
    print(f'--- {s} ---')
    for t in doc:
        print(f'  {t.text:12} dep={t.dep_:10} head={t.head.text:12} lemma={t.lemma_}')
"
```
Record the printed dependency structure for each sentence — this is the
ground truth Step 4's implementation and Step 3's test assertions must
match. (Do not skip this — the extraction logic below is written to match
typical `en_core_web_sm` output for these five sentence *shapes*, but the
exact child/head relationships for these exact words must be confirmed
against this real output before the test's expected values are finalized.)

- [ ] **Step 3: Write the test using the real parse output from Step 2**

Create `backend/tests/test_brain_nlp.py`, using the actual head/child
relationships observed in Step 2 to confirm these expected extractions (the
five cases below are the intended semantics — adjust the expected concept
strings only if Step 2's real lemmas differ, e.g. "fire" vs "Fire"):

```python
"""Tests for spaCy-based dependency extraction. Requires en_core_web_sm
(installed in Step 1) — these are integration tests against the real
parser, not mocks, since the whole point is real dependency structure."""
from backend.services.brain_nlp import extract_dependencies


def test_forward_connective_cause_effect():
    # "Fire causes heat" -> fire is the cause, heat is the effect
    result = extract_dependencies("Fire causes heat.")
    assert ("fire", "heat") in result


def test_forward_connective_leads_to():
    # "Heat leads to energy" -> heat is the cause, energy is the effect
    result = extract_dependencies("Heat leads to energy.")
    assert ("heat", "energy") in result


def test_backward_connective_requires():
    # "The engine requires fuel" -> fuel is the cause (prerequisite), engine is the effect (dependent)
    result = extract_dependencies("The engine requires fuel.")
    assert ("fuel", "engine") in result


def test_backward_connective_depends_on():
    # "Rust depends on moisture" -> moisture is the cause, rust is the effect
    result = extract_dependencies("Rust depends on moisture.")
    assert ("moisture", "rust") in result


def test_no_connective_returns_empty():
    result = extract_dependencies("The sky is blue.")
    assert result == []
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_nlp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.brain_nlp'`.

- [ ] **Step 5: Implement, matching the real parse structure from Step 2**

Create `backend/services/brain_nlp.py`:

```python
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
    # "leads to X" / "results in X" — object is inside a prepositional phrase
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
```

- [ ] **Step 6: Run test to verify it passes; fix extraction logic if the
real parse structure from Step 2 requires it**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_nlp.py -v`
Expected: all 5 tests PASS. If a case fails, the fix is to adjust
`_subject_of`/`_object_of`/the connective-set membership to match what Step
2's real printed parse actually showed for that sentence — never to change
the test's expected tuple to match broken logic.

- [ ] **Step 7: Commit**

```bash
git add backend/services/brain_nlp.py backend/tests/test_brain_nlp.py
git commit -m "feat(brain): add spaCy dependency-parsing relationship extraction"
```

---

### Task 5: Source fetchers (Wikipedia, arXiv, RSS news) with robots.txt + rate limiting

**Files:**
- Create: `backend/services/brain_fetchers.py`
- Create: `backend/tests/test_brain_fetchers.py`

**Interfaces:**
- Consumes: `httpx.AsyncClient` (existing dependency).
- Produces: `class RobotsChecker` with `async def allowed(self, url: str, client) -> bool`;
  `class RateLimiter` with `async def wait(self, url: str) -> None`;
  `async def fetch_wikipedia(url: str, client) -> tuple[str, list[str]]`;
  `async def fetch_arxiv(url: str, client) -> tuple[str, list[str]]`;
  `async def fetch_rss_news(feed_url: str, client) -> list[tuple[str, str]]`
  (returns `[(article_url, concept_hint), ...]` — the RSS feed itself is the
  discovery mechanism, individual articles are fetched via a shared
  `fetch_generic_article` helper); all importable from
  `backend.services.brain_fetchers`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_brain_fetchers.py`:

```python
"""Tests for the brain crawler's source fetchers, robots.txt checker, and
rate limiter — using a mocked httpx client, no real network calls."""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.brain_fetchers import RobotsChecker, RateLimiter, fetch_wikipedia


def _mock_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestRobotsChecker:
    async def test_allows_when_no_disallow_matches(self):
        client = AsyncMock()
        client.get.return_value = _mock_response("User-agent: *\nDisallow: /admin/\n")
        checker = RobotsChecker()
        assert await checker.allowed("https://en.wikipedia.org/wiki/Fire", client) is True

    async def test_disallows_matching_path(self):
        client = AsyncMock()
        client.get.return_value = _mock_response("User-agent: *\nDisallow: /wiki/Special:\n")
        checker = RobotsChecker()
        assert await checker.allowed("https://en.wikipedia.org/wiki/Special:Random", client) is False

    async def test_caches_robots_txt_per_domain(self):
        client = AsyncMock()
        client.get.return_value = _mock_response("User-agent: *\nDisallow:\n")
        checker = RobotsChecker()
        await checker.allowed("https://en.wikipedia.org/wiki/A", client)
        await checker.allowed("https://en.wikipedia.org/wiki/B", client)
        assert client.get.call_count == 1  # robots.txt fetched once, reused


class TestRateLimiter:
    async def test_enforces_minimum_gap_per_domain(self):
        limiter = RateLimiter(min_interval_seconds=0.2)
        start = time.monotonic()
        await limiter.wait("https://en.wikipedia.org/wiki/A")
        await limiter.wait("https://en.wikipedia.org/wiki/B")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.2

    async def test_different_domains_not_rate_limited_against_each_other(self):
        limiter = RateLimiter(min_interval_seconds=5.0)
        start = time.monotonic()
        await limiter.wait("https://en.wikipedia.org/wiki/A")
        await limiter.wait("https://arxiv.org/abs/1234")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0


class TestFetchWikipedia:
    async def test_extracts_text_and_links(self):
        html = """
        <html><body><div id="mw-content-text">
        <p>Fire causes heat. Heat leads to energy.</p>
        <a href="/wiki/Heat">Heat</a>
        <a href="/wiki/Special:Random">Random</a>
        <a href="https://external.com/page">External</a>
        </div></body></html>
        """
        client = AsyncMock()
        client.get.return_value = _mock_response(html)
        text, links = await fetch_wikipedia("https://en.wikipedia.org/wiki/Fire", client)
        assert "Fire causes heat" in text
        assert "https://en.wikipedia.org/wiki/Heat" in links
        assert not any("Special:" in l for l in links)
        assert not any("external.com" in l for l in links)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_fetchers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.brain_fetchers'`.

- [ ] **Step 3: Implement**

Create `backend/services/brain_fetchers.py`:

```python
"""Source fetchers for the Brain Engine crawler.

Each fetcher returns (text, discovered_links). All network access goes
through the shared RobotsChecker and RateLimiter — no fetcher bypasses
either.
"""
import asyncio
import re
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup


class RobotsChecker:
    """Fetches and caches robots.txt per domain, checks URLs against it."""

    def __init__(self):
        self._cache: dict[str, RobotFileParser] = {}

    async def allowed(self, url: str, client) -> bool:
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self._cache:
            parser = RobotFileParser()
            try:
                resp = await client.get(f"{domain}/robots.txt")
                parser.parse(resp.text.splitlines())
            except Exception:
                parser.parse([])  # no robots.txt reachable -> treat as allow-all
            self._cache[domain] = parser

        return self._cache[domain].can_fetch("*", url)


class RateLimiter:
    """Enforces a minimum interval between requests to the same domain."""

    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval = min_interval_seconds
        self._last_request: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        now = time.monotonic()
        last = self._last_request.get(domain)
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
        self._last_request[domain] = time.monotonic()


def _extract_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in parts if 5 <= len(s.split()) <= 40]


async def fetch_wikipedia(url: str, client) -> tuple[str, list[str]]:
    """Fetch a Wikipedia article: main text + in-article links."""
    resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    body = soup.select_one("#mw-content-text") or soup
    paras = body.select("p")
    text = " ".join(p.get_text() for p in paras)
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    links: list[str] = []
    seen: set[str] = set()
    for a in body.select("a[href]"):
        href = a.get("href", "")
        if href.startswith("https://en.wikipedia.org/wiki/"):
            full = href
        elif href.startswith("/wiki/"):
            full = "https://en.wikipedia.org" + href
        else:
            continue
        path = full.replace("https://en.wikipedia.org/wiki/", "")
        if ":" in path or "#" in path:
            continue
        if full not in seen:
            seen.add(full)
            links.append(full)

    return text, links[:50]


async def fetch_arxiv(url: str, client) -> tuple[str, list[str]]:
    """Fetch an arXiv abstract page: abstract text + linked paper IDs."""
    resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    abstract_block = soup.select_one("blockquote.abstract")
    text = abstract_block.get_text(" ", strip=True) if abstract_block else ""
    text = re.sub(r'^Abstract:\s*', '', text)

    links: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "/abs/" in href:
            full = href if href.startswith("http") else f"https://arxiv.org{href}"
            if full not in seen:
                seen.add(full)
                links.append(full)

    return text, links[:30]


async def fetch_generic_article(url: str, client) -> tuple[str, list[str]]:
    """Fetch a plain article page (used for RSS-discovered news articles):
    paragraph text + outbound links found in the article body."""
    resp = await client.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    paras = soup.select("p")
    text = " ".join(p.get_text() for p in paras)
    text = re.sub(r'\s+', ' ', text).strip()

    links: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if href.startswith("http") and href not in seen:
            seen.add(href)
            links.append(href)

    return text, links[:20]


async def fetch_rss_news(feed_url: str, client) -> list[tuple[str, str]]:
    """Parse an RSS feed, return (article_url, title) for each entry."""
    import feedparser
    resp = await client.get(feed_url)
    parsed = feedparser.parse(resp.text)
    return [(entry.link, entry.get("title", "")) for entry in parsed.entries if entry.get("link")]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_fetchers.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/brain_fetchers.py backend/tests/test_brain_fetchers.py
git commit -m "feat(brain): add Wikipedia/arXiv/RSS fetchers with robots.txt and rate limiting"
```

---

### Task 6: The crawler main loop

**Files:**
- Create: `backend/brain_crawler.py`
- Create: `backend/tests/test_brain_crawler.py`

**Interfaces:**
- Consumes: `backend.services.brain_fetchers` (Task 5), `backend.services.brain_nlp.extract_dependencies` (Task 4), `backend.services.neo4j_service.get_driver` (Task 2), `backend.models.{BrainFrontier,BrainVisitedPage,BrainDeadLetter,BrainStats}` (Task 1).
- Produces: `async def crawl_one_page(frontier_entry: dict, client, robots: RobotsChecker, limiter: RateLimiter, neo4j_driver, pg_session) -> bool` (True on success) and `async def main()` (the entry point run via `python -m backend.brain_crawler`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_brain_crawler.py`:

```python
"""Tests for the crawler's per-page processing logic — mocked fetchers,
Neo4j driver, and Postgres session, so no live services are needed."""
from unittest.mock import AsyncMock, MagicMock, patch

from backend import brain_crawler


def _fake_pg_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


class _FakeNeo4jResult:
    """An async-iterable fake Neo4j result yielding no records by default —
    enough for the crawler's `async for record in result:` loops to run
    without error while asserting call counts, not record content."""
    def __aiter__(self):
        async def _empty():
            return
            yield
        return _empty()


def _fake_neo4j_driver():
    driver = MagicMock()
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = AsyncMock(return_value=_FakeNeo4jResult())
    driver.session.return_value = session_cm
    return driver


class TestCrawlOnePage:
    async def test_successful_page_writes_to_both_stores(self):
        entry = {"url": "https://en.wikipedia.org/wiki/Fire", "concept": "fire", "source_type": "wikipedia"}
        neo4j_driver = _fake_neo4j_driver()
        pg_session = _fake_pg_session()

        with patch.object(brain_crawler, "fetch_wikipedia", AsyncMock(
            return_value=("Fire causes heat. Heat leads to energy.", ["https://en.wikipedia.org/wiki/Heat"])
        )):
            ok = await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=neo4j_driver, pg_session=pg_session,
            )

        assert ok is True
        assert neo4j_driver.session.return_value.run.await_count >= 1
        assert pg_session.execute.await_count >= 1  # visited page + frontier insert
        pg_session.commit.assert_awaited()

    async def test_robots_disallowed_page_is_skipped_not_failed(self):
        entry = {"url": "https://en.wikipedia.org/wiki/Special:Random", "concept": "random", "source_type": "wikipedia"}
        ok = await brain_crawler.crawl_one_page(
            entry, client=AsyncMock(),
            robots=AsyncMock(allowed=AsyncMock(return_value=False)),
            limiter=AsyncMock(wait=AsyncMock()),
            neo4j_driver=_fake_neo4j_driver(), pg_session=_fake_pg_session(),
        )
        assert ok is False

    async def test_fetch_failure_returns_false_without_raising(self):
        entry = {"url": "https://en.wikipedia.org/wiki/Broken", "concept": "broken", "source_type": "wikipedia"}
        with patch.object(brain_crawler, "fetch_wikipedia", AsyncMock(side_effect=Exception("timeout"))):
            ok = await brain_crawler.crawl_one_page(
                entry, client=AsyncMock(),
                robots=AsyncMock(allowed=AsyncMock(return_value=True)),
                limiter=AsyncMock(wait=AsyncMock()),
                neo4j_driver=_fake_neo4j_driver(), pg_session=_fake_pg_session(),
            )
        assert ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_crawler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.brain_crawler'`.

- [ ] **Step 3: Implement**

Create `backend/brain_crawler.py`:

```python
"""AKKI Brain Engine — production crawler.

Runs continuously (python -m backend.brain_crawler). Fetches from
Wikipedia, arXiv, and one configured RSS news feed; extracts relationships
via spaCy dependency parsing; writes concepts/edges to Neo4j and crawl
state to Postgres. Replaces the original brain/run.py prototype's
single-threaded, pickle-persisted, regex-extraction design.
"""
import asyncio
import logging
import os
import signal
from collections import Counter
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import AsyncSessionLocal
from backend.models import BrainFrontier, BrainVisitedPage, BrainDeadLetter, BrainStats
from backend.services.neo4j_service import get_driver, ensure_schema
from backend.services.brain_fetchers import (
    RobotsChecker, RateLimiter, fetch_wikipedia, fetch_arxiv,
    fetch_generic_article, fetch_rss_news,
)
from backend.services.brain_nlp import extract_dependencies
from backend.services.brain_stats_math import log_likelihood_ratio

logger = logging.getLogger("akki.brain_crawler")

SEEDS = [
    ("https://en.wikipedia.org/wiki/Fire", "fire", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Energy", "energy", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Evolution", "evolution", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Consciousness", "consciousness", "wikipedia"),
    ("https://en.wikipedia.org/wiki/Mathematics", "mathematics", "wikipedia"),
]
NEWS_FEED_URL = os.environ.get("BRAIN_NEWS_FEED_URL", "https://feeds.bbci.co.uk/news/rss.xml")

MAX_ATTEMPTS = 3
PRUNE_EVERY_N_PAGES = 200
BATCH_SIZE = 20

_FETCHERS = {"wikipedia": fetch_wikipedia, "arxiv": fetch_arxiv, "news": fetch_generic_article}
_running = True


def _signal_handler(sig, frame):
    global _running
    logger.info("Signal %s received — finishing current page, then stopping.", sig)
    _running = False


async def crawl_one_page(entry: dict, client, robots: RobotsChecker, limiter: RateLimiter,
                          neo4j_driver, pg_session) -> bool:
    """Fetch, extract, and persist one frontier entry. Returns True on success."""
    url, concept, source_type = entry["url"], entry["concept"], entry["source_type"]

    if not await robots.allowed(url, client):
        logger.info("Skipping (robots.txt disallows): %s", url)
        return False

    await limiter.wait(url)

    fetcher = _FETCHERS.get(source_type, fetch_generic_article)
    try:
        text, links = await fetcher(url, client)
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        return False

    sentences = [s for s in text.split(". ") if len(s.split()) >= 5]
    pairs: list[tuple[str, str]] = []
    for sentence in sentences[:200]:  # cap per-page NLP cost
        try:
            pairs.extend(extract_dependencies(sentence))
        except Exception:
            continue

    word_freq: Counter = Counter()
    edge_counts: Counter = Counter()
    for cause, effect in pairs:
        word_freq[cause] += 1
        word_freq[effect] += 1
        edge_counts[(cause, effect)] += 1

    async with neo4j_driver.session() as session:
        updated_freq: dict[str, int] = {}
        updated_total = 0

        if word_freq:
            # Upsert word frequencies AND the running global total-occurrence
            # counter in one call, returning post-update values so G2 can be
            # computed below without a second full read.
            result = await session.run(
                "UNWIND $words AS w "
                "MERGE (c:Concept {word: w.word}) "
                "ON CREATE SET c.frequency = w.count, c.first_seen = datetime() "
                "ON MATCH SET c.frequency = c.frequency + w.count "
                "WITH c, w "
                "MERGE (m:Meta {id: 'singleton'}) "
                "ON CREATE SET m.totalWordOccurrences = w.count "
                "ON MATCH SET m.totalWordOccurrences = m.totalWordOccurrences + w.count "
                "RETURN c.word AS word, c.frequency AS frequency, m.totalWordOccurrences AS total",
                words=[{"word": w, "count": c} for w, c in word_freq.items()],
            )
            async for record in result:
                updated_freq[record["word"]] = record["frequency"]
                updated_total = record["total"]  # same value every row — last write wins, all consistent

        if edge_counts:
            # Upsert edge counts, returning the post-update count per edge.
            result = await session.run(
                "UNWIND $edges AS e "
                "MATCH (a:Concept {word: e.cause}) "
                "MATCH (b:Concept {word: e.effect}) "
                "MERGE (a)-[r:CO_OCCURS]->(b) "
                "ON CREATE SET r.count = e.count, r.last_updated = datetime() "
                "ON MATCH SET r.count = r.count + e.count, r.last_updated = datetime() "
                "RETURN e.cause AS cause, e.effect AS effect, r.count AS count",
                edges=[{"cause": c, "effect": eff, "count": n} for (c, eff), n in edge_counts.items()],
            )
            updated_counts: dict[tuple[str, str], int] = {}
            async for record in result:
                updated_counts[(record["cause"], record["effect"])] = record["count"]

            # Recompute G2 for every edge touched this page, using the
            # post-update frequencies/total from above, then write it back —
            # a third small batched call, not one per edge.
            g2_updates = []
            for (cause, effect), count in updated_counts.items():
                freq_a = updated_freq.get(cause, count)
                freq_b = updated_freq.get(effect, count)
                if updated_total > 0:
                    g2 = log_likelihood_ratio(count, freq_a, freq_b, updated_total)
                    g2_updates.append({"cause": cause, "effect": effect, "g2": g2})

            if g2_updates:
                await session.run(
                    "UNWIND $updates AS u "
                    "MATCH (a:Concept {word: u.cause})-[r:CO_OCCURS]->(b:Concept {word: u.effect}) "
                    "SET r.g2 = u.g2",
                    updates=g2_updates,
                )

    await pg_session.execute(
        pg_insert(BrainVisitedPage).values(
            url=url, concept=concept, source_type=source_type,
            sentences_learned=len(sentences),
        ).on_conflict_do_nothing()
    )
    await pg_session.execute(delete(BrainFrontier).where(BrainFrontier.url == url))

    new_links = [
        {"url": link, "concept": link.rsplit("/", 1)[-1].replace("_", " "), "source_type": source_type}
        for link in links
    ]
    if new_links:
        await pg_session.execute(
            pg_insert(BrainFrontier).values(new_links).on_conflict_do_nothing()
        )

    await pg_session.commit()
    return True


async def _record_failure(pg_session, url: str, source_type: str, error: str) -> None:
    result = await pg_session.execute(select(BrainDeadLetter).where(BrainDeadLetter.url == url))
    existing = result.scalar_one_or_none()
    if existing:
        existing.attempts += 1
        existing.error = error
        existing.last_attempt_at = datetime.now(timezone.utc)
        if existing.attempts >= MAX_ATTEMPTS:
            await pg_session.execute(delete(BrainFrontier).where(BrainFrontier.url == url))
    else:
        pg_session.add(BrainDeadLetter(url=url, source_type=source_type, error=error, attempts=1))
    await pg_session.commit()


async def _prune_low_value_edges(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (:Concept)-[r:CO_OCCURS]->() WHERE r.count < 2 DELETE r"
        )
        await session.run(
            "MATCH (a:Concept)-[r:CO_OCCURS]->() "
            "WITH a, r ORDER BY r.count DESC "
            "WITH a, collect(r) AS rels "
            "UNWIND rels[50..] AS excess "
            "DELETE excess"
        )
    logger.info("Pruning complete: dropped low-count and long-tail edges.")


async def main() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    neo4j_driver = get_driver()
    await ensure_schema()

    robots = RobotsChecker()
    limiter = RateLimiter(min_interval_seconds=1.0)
    pages_since_prune = 0

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        async with AsyncSessionLocal() as pg_session:
            # Seed the frontier if empty
            result = await pg_session.execute(select(BrainFrontier).limit(1))
            if result.scalar_one_or_none() is None:
                for url, concept, source_type in SEEDS:
                    await pg_session.execute(
                        pg_insert(BrainFrontier).values(
                            url=url, concept=concept, source_type=source_type,
                        ).on_conflict_do_nothing()
                    )
                try:
                    news_items = await fetch_rss_news(NEWS_FEED_URL, client)
                    for url, title in news_items[:20]:
                        await pg_session.execute(
                            pg_insert(BrainFrontier).values(
                                url=url, concept=title[:200], source_type="news",
                            ).on_conflict_do_nothing()
                        )
                except Exception as e:
                    logger.warning("Initial RSS seed failed (non-fatal): %s", e)
                await pg_session.commit()

            logger.info("Brain crawler starting.")

            while _running:
                result = await pg_session.execute(select(BrainFrontier).limit(BATCH_SIZE))
                batch = result.scalars().all()

                if not batch:
                    logger.info("Frontier empty — sleeping 30s before re-checking.")
                    await asyncio.sleep(30)
                    continue

                for entry in batch:
                    if not _running:
                        break
                    entry_dict = {"url": entry.url, "concept": entry.concept, "source_type": entry.source_type}
                    try:
                        ok = await crawl_one_page(entry_dict, client, robots, limiter, neo4j_driver, pg_session)
                    except Exception as e:
                        logger.error("Unhandled error crawling %s: %s", entry.url, e, exc_info=True)
                        ok = False

                    if ok:
                        stats_result = await pg_session.execute(select(BrainStats).where(BrainStats.id == "singleton"))
                        stats = stats_result.scalar_one_or_none()
                        if stats is None:
                            stats = BrainStats(id="singleton", total_pages=0, total_sentences=0)
                            pg_session.add(stats)
                        stats.total_pages += 1
                        await pg_session.commit()
                        pages_since_prune += 1
                    else:
                        await _record_failure(pg_session, entry.url, entry.source_type, "fetch or robots check failed")

                    if pages_since_prune >= PRUNE_EVERY_N_PAGES:
                        await _prune_low_value_edges(neo4j_driver)
                        pages_since_prune = 0

    logger.info("Brain crawler stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_crawler.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/brain_crawler.py backend/tests/test_brain_crawler.py
git commit -m "feat(brain): add the production crawler main loop"
```

---

### Task 7: Query API

**Files:**
- Create: `backend/services/brain_service.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_brain_service.py`

**Interfaces:**
- Consumes: `backend.services.neo4j_service.get_driver` (Task 2).
- Produces: `async def get_status(pg_session) -> dict`, `async def health() -> dict`,
  `async def discover(concept: str, concept2: str | None) -> dict` —
  importable from `backend.services.brain_service`; three new endpoints in
  `main.py`: `GET /api/brain/health`, `GET /api/brain/status`,
  `POST /api/brain/discover`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_brain_service.py`:

```python
"""Tests for the brain query service — mocked Neo4j session/driver, no live
graph required."""
from unittest.mock import AsyncMock, MagicMock

from backend.services import brain_service


def _make_result(records: list[dict]):
    """An async-iterable fake Neo4j result yielding the given record dicts,
    each accessed by dict-style key lookup (e.g. record["word"])."""
    async def _iter():
        for r in records:
            yield r
    result = MagicMock()
    result.__aiter__ = lambda self=result: _iter()
    return result


def _fake_driver_with_sequential_results(results_in_call_order: list[list[dict]]):
    """Each successive call to session.run() returns the next list of fake
    records in sequence — used because this service issues multiple
    structurally-identical-looking queries (e.g. the same Cypher shape
    called once per concept in convergence mode) that a query-text-based
    fake couldn't distinguish, but which must return different fake data
    per call."""
    driver = MagicMock()
    call_queue = [_make_result(r) for r in results_in_call_order]

    async def run(query, **params):
        return call_queue.pop(0)

    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session_cm
    session_cm.__aexit__.return_value = False
    session_cm.run = run
    driver.session.return_value = session_cm
    return driver


class TestDiscoverSingleConcept:
    async def test_returns_ranked_associations(self, monkeypatch):
        driver = _fake_driver_with_sequential_results([
            [{"word": "heat", "g2": 42.5, "count": 10}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)
        result = await brain_service.discover("fire", None)
        assert result["concept"] == "fire"
        assert result["associations"][0]["word"] == "heat"
        assert result["associations"][0]["g2"] == 42.5


class TestDiscoverConvergence:
    async def test_returns_convergence_points(self, monkeypatch):
        # First call = _reachable_with_depth("fire"), second = _reachable_with_depth("music")
        driver = _fake_driver_with_sequential_results([
            [{"word": "transformation", "depth": 2}],
            [{"word": "transformation", "depth": 3}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)
        result = await brain_service.discover("fire", "music")
        assert any(c["concept"] == "transformation" for c in result["convergencePoints"])


class TestGetStatus:
    async def test_reads_pg_stats_and_neo4j_counts(self, monkeypatch):
        # First call = concept count query, second call = edge count query
        driver = _fake_driver_with_sequential_results([
            [{"count": 500}],
            [{"count": 1200}],
        ])
        monkeypatch.setattr(brain_service, "get_driver", lambda: driver)

        pg_session = AsyncMock()
        stats_row = MagicMock(total_pages=42, total_sentences=1000, updated_at=None)
        frontier_count = MagicMock(scalar=MagicMock(return_value=17))
        pg_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=stats_row)),
            frontier_count,
        ])

        result = await brain_service.get_status(pg_session)
        assert result["totalPages"] == 42
        assert result["frontierSize"] == 17
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.brain_service'`.

- [ ] **Step 3: Implement the service**

Create `backend/services/brain_service.py`:

```python
"""Query layer for the Brain Engine — reads from Neo4j (the knowledge
graph) and Postgres (crawl state)."""
from sqlalchemy import select, func

from backend.models import BrainStats, BrainFrontier, BrainDeadLetter
from backend.services.neo4j_service import get_driver, health_check as neo4j_health_check


async def health() -> dict:
    neo4j_ok = await neo4j_health_check()
    return {"neo4j": neo4j_ok, "healthy": neo4j_ok}


async def get_status(pg_session) -> dict:
    stats_result = await pg_session.execute(select(BrainStats).where(BrainStats.id == "singleton"))
    stats = stats_result.scalar_one_or_none()

    frontier_result = await pg_session.execute(select(func.count()).select_from(BrainFrontier))
    frontier_size = frontier_result.scalar() or 0

    driver = get_driver()
    async with driver.session() as session:
        concept_result = await session.run("MATCH (c:Concept) RETURN count(c) AS count")
        concept_count = 0
        async for record in concept_result:
            concept_count = record["count"]

        edge_result = await session.run("MATCH ()-[r:CO_OCCURS]->() RETURN count(r) AS count")
        edge_count = 0
        async for record in edge_result:
            edge_count = record["count"]

    return {
        "totalPages": stats.total_pages if stats else 0,
        "totalSentences": stats.total_sentences if stats else 0,
        "conceptCount": concept_count,
        "edgeCount": edge_count,
        "frontierSize": frontier_size,
        "updatedAt": stats.updated_at.isoformat() if stats and stats.updated_at else None,
    }


async def _top_associations(concept: str, limit: int = 20) -> list[dict]:
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:Concept {word: $concept})-[r:CO_OCCURS]->(b) "
            "RETURN b.word AS word, r.g2 AS g2, r.count AS count "
            "ORDER BY r.g2 DESC LIMIT $limit",
            concept=concept, limit=limit,
        )
        return [{"word": r["word"], "g2": r["g2"], "count": r["count"]} async for r in result]


async def _reachable_with_depth(concept: str, max_depth: int = 3) -> dict[str, int]:
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            "MATCH path = (a:Concept {word:$c1})-[:CO_OCCURS*1..%d]->(mid) "
            "RETURN mid.word AS word, min(length(path)) AS depth" % max_depth,
            c1=concept,
        )
        return {r["word"]: r["depth"] async for r in result}


async def discover(concept: str, concept2: str | None = None) -> dict:
    concept = concept.strip().lower()

    if not concept2:
        associations = await _top_associations(concept)
        if not associations:
            return {"concept": concept, "associations": [], "error": "No known associations yet — the brain hasn't learned this concept."}
        return {"concept": concept, "associations": associations}

    concept2 = concept2.strip().lower()
    reached_from_1 = await _reachable_with_depth(concept)
    reached_from_2 = await _reachable_with_depth(concept2)

    shared = set(reached_from_1) & set(reached_from_2)
    convergence_points = sorted(
        (
            {"concept": word, "depthFrom1": reached_from_1[word], "depthFrom2": reached_from_2[word],
             "combinedDepth": reached_from_1[word] + reached_from_2[word]}
            for word in shared
        ),
        key=lambda c: c["combinedDepth"],
    )

    if not convergence_points:
        return {"concept1": concept, "concept2": concept2, "convergencePoints": [],
                "error": "No convergence found yet within 3 hops of either concept."}

    return {"concept1": concept, "concept2": concept2, "convergencePoints": convergence_points}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_brain_service.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Add the three endpoints to `main.py`**

Modify `backend/main.py` — add near the existing `/api/tools/execute/stream`
endpoint (after it), a new section:

```python
# ── Brain Engine ────────────────────────────────────────────────────────────

@app.get("/api/brain/health")
async def brain_health():
    from backend.services import brain_service
    result = await brain_service.health()
    if not result["healthy"]:
        raise HTTPException(status_code=503, detail="Neo4j unreachable")
    return result


@app.get("/api/brain/status")
async def brain_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services import brain_service
    return await brain_service.get_status(db)


@app.post("/api/brain/discover")
async def brain_discover(
    body: BrainDiscoverRequest,
    current_user: User = Depends(get_current_user),
):
    from backend.services import brain_service
    return await brain_service.discover(body.concept, body.concept2)
```

Then add `BrainDiscoverRequest` to `backend/schemas.py`, right after
`ToolExecuteRequest`:

```python
class BrainDiscoverRequest(BaseModel):
    concept: str
    concept2: str | None = None
```

(`from backend.schemas import *` at `backend/main.py:192` already brings
this into scope — no new import needed in `main.py`.)

- [ ] **Step 6: Run the full backend test suite to confirm no regressions**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all tests across every prior task PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/brain_service.py backend/main.py backend/schemas.py backend/tests/test_brain_service.py
git commit -m "feat(brain): add query API (health, status, discover)"
```

---

### Task 8: Docker — Neo4j service and the crawler container

**Files:**
- Modify: `docker-compose.yml`
- Create: `Dockerfile.brain-crawler`
- Modify: `Dockerfile.backend` (Neo4j env vars only — no new packages needed, `backend` itself only queries Neo4j, doesn't crawl)

**Interfaces:**
- Produces: a `neo4j` service and a `brain-crawler` service in `docker-compose.yml`, reachable by `backend` at `bolt://neo4j:7687`.

- [ ] **Step 1: Add the `neo4j` service**

Modify `docker-compose.yml` — add this service, after the existing `db`
service and before the `networks:` section:

```yaml
  # ── Neo4j (Brain Engine knowledge graph) ──────────────────────────────────────
  neo4j:
    image: neo4j:5-community
    container_name: akki-neo4j
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
    ports:
      - "7474:7474"   # browser UI
      - "7687:7687"   # bolt protocol
    volumes:
      - neo4jdata:/data
    healthcheck:
      test: ["CMD-SHELL", "wget -O /dev/null -q http://localhost:7474 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
    restart: unless-stopped
    networks:
      - akki-net

  # ── Brain Crawler (always-on) ──────────────────────────────────────────────────
  brain-crawler:
    build:
      context: .
      dockerfile: Dockerfile.brain-crawler
    container_name: akki-brain-crawler
    environment:
      DATABASE_URL: postgresql://akki:${DB_PASSWORD:-changeme}@db:5432/akki_ai
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD:-changeme}
    depends_on:
      db:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - akki-net
```

- [ ] **Step 2: Add the `neo4jdata` volume**

Modify `docker-compose.yml` — change the `volumes:` section from:

```yaml
volumes:
  pgdata:
```

to:

```yaml
volumes:
  pgdata:
  neo4jdata:
```

- [ ] **Step 3: Give `backend` the Neo4j connection env vars**

Modify `docker-compose.yml` — in the `backend` service's `environment:`
block, add (after the existing `DATABASE_URL` line):

```yaml
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD:-changeme}
```

And add `neo4j` to `backend`'s `depends_on`:

```yaml
    depends_on:
      db:
        condition: service_healthy
      neo4j:
        condition: service_healthy
```

- [ ] **Step 4: Create the crawler's Dockerfile**

Create `Dockerfile.brain-crawler`:

```dockerfile
# ── AKKI Brain Crawler ────────────────────────────────────────────────────────
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -m spacy download en_core_web_sm

COPY backend/ ./backend/

CMD ["python", "-m", "backend.brain_crawler"]
```

- [ ] **Step 5: Build and verify**

Run: `docker compose build brain-crawler neo4j`
Expected: both images build successfully. If `en_core_web_sm` fails to
download during the build (network restrictions in the build environment),
pin and vendor the model wheel instead — check the spaCy download log for
the exact failure before assuming this is needed.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml Dockerfile.brain-crawler
git commit -m "build(brain): add Neo4j and brain-crawler Docker services"
```

---

### Task 9: Frontend — Brain page

**Files:**
- Create: `client/src/pages/brain.tsx`
- Modify: `client/src/AppWrapper.tsx`
- Modify: `client/src/components/layout/navigation-rail.tsx`

**Interfaces:**
- Consumes: `GET /api/brain/status`, `POST /api/brain/discover` (Task 7).
- Produces: a new route at `/brain`, a new nav entry.

- [ ] **Step 1: Create the page**

Create `client/src/pages/brain.tsx`:

```tsx
import { useEffect, useState } from "react";

interface BrainStatus {
  totalPages: number;
  totalSentences: number;
  conceptCount: number;
  edgeCount: number;
  frontierSize: number;
  updatedAt: string | null;
}

interface Association {
  word: string;
  g2: number;
  count: number;
}

interface ConvergencePoint {
  concept: string;
  depthFrom1: number;
  depthFrom2: number;
  combinedDepth: number;
}

export default function BrainPage() {
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [concept, setConcept] = useState("");
  const [concept2, setConcept2] = useState("");
  const [associations, setAssociations] = useState<Association[] | null>(null);
  const [convergencePoints, setConvergencePoints] = useState<ConvergencePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const authHeaders = () => {
    const token = localStorage.getItem("auth_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch("/api/brain/status", { headers: authHeaders() });
        if (res.ok) setStatus(await res.json());
      } catch {
        // status polling failure is non-fatal — just skip this tick
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const runDiscover = async () => {
    if (!concept.trim()) return;
    setLoading(true);
    setError(null);
    setAssociations(null);
    setConvergencePoints(null);
    try {
      const res = await fetch("/api/brain/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          concept: concept.trim(),
          concept2: concept2.trim() || null,
        }),
      });
      const data = await res.json();
      if (data.error) setError(data.error);
      if (data.associations) setAssociations(data.associations);
      if (data.convergencePoints) setConvergencePoints(data.convergencePoints);
    } catch {
      setError("Request failed — check your connection.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24, fontFamily: "monospace", color: "#fff", background: "#04080f", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 18, color: "#00d8ff", marginBottom: 4 }}>AKKI Brain</h1>
      <p style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginBottom: 20 }}>
        Always-on dependency-discovery engine — separate from chat, learns continuously in the background.
      </p>

      {status && (
        <div style={{ display: "flex", gap: 24, marginBottom: 24, fontSize: 12 }}>
          <div>Pages: <b style={{ color: "#00ff88" }}>{status.totalPages.toLocaleString()}</b></div>
          <div>Sentences: <b style={{ color: "#00ff88" }}>{status.totalSentences.toLocaleString()}</b></div>
          <div>Concepts: <b style={{ color: "#00ff88" }}>{status.conceptCount.toLocaleString()}</b></div>
          <div>Edges: <b style={{ color: "#00ff88" }}>{status.edgeCount.toLocaleString()}</b></div>
          <div>Frontier: <b style={{ color: "#00ff88" }}>{status.frontierSize.toLocaleString()}</b></div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          value={concept}
          onChange={(e) => setConcept(e.target.value)}
          placeholder="concept (e.g. fire)"
          style={{ padding: 8, background: "#0d1117", border: "1px solid rgba(0,216,255,0.3)", color: "#fff", borderRadius: 6 }}
        />
        <input
          value={concept2}
          onChange={(e) => setConcept2(e.target.value)}
          placeholder="optional second concept — what connects them?"
          style={{ padding: 8, background: "#0d1117", border: "1px solid rgba(0,216,255,0.3)", color: "#fff", borderRadius: 6, flex: 1 }}
        />
        <button
          onClick={runDiscover}
          disabled={!concept.trim() || loading}
          style={{ padding: "8px 16px", background: "#00d8ff", color: "#04080f", border: "none", borderRadius: 6, fontWeight: "bold", cursor: loading ? "not-allowed" : "pointer" }}
        >
          {loading ? "..." : "Discover"}
        </button>
      </div>

      {error && <p style={{ color: "#ff3868", fontSize: 12 }}>{error}</p>}

      {associations && (
        <div>
          <h3 style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>Top associations with "{concept}"</h3>
          {associations.map((a) => (
            <div key={a.word} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <span>{a.word}</span>
              <span style={{ color: "#00ff88" }}>G² {a.g2.toFixed(1)} (n={a.count})</span>
            </div>
          ))}
        </div>
      )}

      {convergencePoints && (
        <div>
          <h3 style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>Convergence points: "{concept}" ↔ "{concept2}"</h3>
          {convergencePoints.map((c) => (
            <div key={c.concept} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <span>{c.concept}</span>
              <span style={{ color: "#00ff88" }}>depth {c.depthFrom1} + {c.depthFrom2} = {c.combinedDepth}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Register the route**

Modify `client/src/AppWrapper.tsx` — add the lazy import alongside the
existing ones (after `const SigmaPage = lazy(() => import("@/pages/sigma"));`):

```typescript
const BrainPage             = lazy(() => import("@/pages/brain"));
```

And add the route alongside the existing `PrivateRoute` entries (after the
`/sigma` route):

```tsx
              <PrivateRoute path="/brain" component={BrainPage} />
```

- [ ] **Step 3: Add the nav entry**

Modify `client/src/components/layout/navigation-rail.tsx` — add this entry
to the nav array, after the `sigma` entry:

```typescript
  { id:"brain",     label:"Brain",     icon:"fas fa-brain",           path:"/brain",     hex:"#00ff88", rgb:"0,255,136"   },
```

- [ ] **Step 4: Typecheck**

Run: `pnpm check`
Expected: no TypeScript errors.

- [ ] **Step 5: Manual QA**

Run `pnpm dev:client` + `pnpm dev:server`, open `/brain`, confirm: the
status panel renders (even if all zeros before the crawler has run), typing
a concept and clicking Discover shows either results or the "hasn't learned
this concept yet" error, and typing a second concept switches to
convergence-point results.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/brain.tsx client/src/AppWrapper.tsx client/src/components/layout/navigation-rail.tsx
git commit -m "feat(brain): add frontend page and nav entry"
```

---

### Task 10: End-to-end verification

**Files:**
- None (verification-only task)

**Interfaces:**
- Consumes: everything from Tasks 1-9, running together via Docker Compose.

- [ ] **Step 1: Bring the full stack up, including the new services**

Run: `docker compose up -d`
Expected: `neo4j`, `brain-crawler`, `backend`, `db`, `frontend` all start;
`docker compose logs -f brain-crawler` shows "Brain crawler starting."
followed by page-crawl log lines.

- [ ] **Step 2: Confirm real data lands in Neo4j**

Run: `docker compose exec neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD:-changeme} "MATCH (c:Concept) RETURN count(c);"`
Expected: a non-zero count after a few minutes of crawling.

- [ ] **Step 3: Confirm the status endpoint reflects real progress**

Run: `curl -s http://localhost:5000/api/brain/status -H "Authorization: Bearer <token>"`
Expected: `totalPages`, `conceptCount`, `edgeCount` all non-zero and
increasing on repeated calls a few minutes apart.

- [ ] **Step 4: Confirm single-concept discovery returns real associations**

Run:
```bash
curl -s -X POST http://localhost:5000/api/brain/discover \
  -H "Content-Type: application/json" -H "Authorization: Bearer <token>" \
  -d '{"concept": "fire"}'
```
Expected: a non-empty `associations` list once the crawler has processed
the "fire" seed page (from `SEEDS` in `brain_crawler.py`), each with a `g2`
score.

- [ ] **Step 5: Confirm convergence queries work once enough pages are crawled**

Run the same request with both `concept` and `concept2` set to two of the
seed words (e.g. `fire` and `mathematics`). Expected: either a
`convergencePoints` list, or the "no convergence found yet" error if the
crawl hasn't gone deep enough yet — both are valid, correct responses; a
500 error is not.

- [ ] **Step 6: Confirm dead-lettering works**

Run: `docker compose exec db psql -U akki -d akki_ai -c "SELECT url, attempts FROM brain_dead_letters LIMIT 5;"`
Expected: query succeeds (table exists, may be empty if nothing has failed
3 times yet — that's fine).

- [ ] **Step 7: Report results to the user**

Summarize actual measured state after the smoke test: pages crawled,
concepts/edges in Neo4j, whether discover/convergence queries returned real
data, and any package-name or spaCy-model-download adjustments that were
needed in Task 8.
