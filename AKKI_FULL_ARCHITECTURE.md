# AKKI Brain — Full Architecture v2
## Updated with Ontology + Question-Driven Learning + Research Foundation

---

## What We Stand On

These already exist in research. We use them as foundation:

| Existing Research | What it does | Our use |
|---|---|---|
| Competency Questions (CQ) | Questions that define ontology scope | Brain generates its own CQs autonomously |
| AutoSchemaKG / KGGen | LLM-driven knowledge graph from text | Foundation for our extraction layer |
| Distributional Semantics | Meaning from context distribution | Foundation for meaning discovery |
| Self-Supervised Learning | Pattern finding without labels | Foundation for symbol discovery |
| Graph Neural Networks | Structural reasoning on graphs | Foundation for convergence engine |

**What does NOT exist that we build:**
- Full zero-instruction system from start to finish
- Brain that generates its own questions and finds answers from internet itself
- Context-Dependent Relationship Fields (CDRF) — our new formula
- Convergence engine finding hidden truths from independent origins
- Continuous live learning — never frozen, always updating

---

## The Core Theory

**Intelligence is finding hidden dependencies between things that have never met.**

The click happens when two things that secretly depend on each other finally meet.

The brain finds that click — not by being told — but by:

1. Reading everything
2. Building an emergent ontology from what it reads
3. Asking its own questions to deepen understanding
4. Finding where independent branches converge

---

## The New Mathematical Formula

### Context-Dependent Relationship Fields (CDRF)

Current systems:
```
R(A, B) = fixed relationship between A and B
```

Our system:
```
R(A, B, C) = relationship between A and B when context is C
```

Where C is the **center of gravity** of surrounding concepts at the moment of observation.

Same two concepts — completely different relationship depending on where in concept space you observe them.

Fire and heat in chemistry context → combustion relationship
Fire and heat in survival context → warmth relationship
Fire and heat in destruction context → damage relationship

**The convergence engine finds:**
```
The value of C where R(A, B, C) = R(X, Y, C) = R(P, Q, C)
```
The context where completely unrelated relationships have the same value.
That context C is the hidden truth. The convergence point.

---

## The Emergent Ontology Layer

Not hand-built. Not defined by humans. Discovered by the brain.

### Three things the ontology discovers on its own:

**Classes** — what categories of things exist
Not told. Discovered from how the internet groups things.
Fire belongs to: {process, phenomenon, chemical reaction, metaphor, symbol}
Discovered because the internet uses fire in all these ways.

**Properties** — what characteristics describe each thing
Not told. Discovered from how the internet describes things.
Fire has: {temperature, color, duration, intensity, danger, beauty}
Discovered because those words consistently appear when describing fire.

**Relationships** — how things connect with direction and strength
Not told. Discovered from convergence across independent sources.
Fire → heat confirmed in chemistry, cooking, physics, survival, poetry
All independently. All saying the same thing. Therefore real.

---

## Question-Driven Self-Learning

The brain generates its own questions about every concept it encounters.

### The question types it learns to generate:

```
What is X?              → discovers class
What does X need?       → discovers dependencies
What does X produce?    → discovers effects
Where does X appear?    → discovers contexts
What is X similar to?   → discovers class membership
Why does X exist?       → discovers purpose
What would happen without X? → discovers necessity
How does X change?      → discovers dynamics
What created X?         → discovers origins
```

### The self-learning loop:

```
Brain encounters new concept X
        ↓
Generates questions about X
        ↓
Searches internet for answers to each question
        ↓
Answers reveal: class, properties, relationships, contexts
        ↓
Builds ontological entry for X
        ↓
New questions emerge from what it just learned
        ↓
Those questions reveal new concepts
        ↓
Repeat forever
```

### Key point:
Early questions come from LLM guidance.
After enough learning — brain generates its own questions.
Questions nobody thought of. Revealing connections nobody found before.

---

## The Eight Functions — Final Design

---

### Function 1 — Raw Signal Reception

**Input:** Any address on the internet
**Output:** HTTP response (status + headers + body)
**Storage:** Temporary buffer only — discarded after processing

```
Step 1: Receive starting URL from LLM (Phase 1 only)
Step 2: Send HTTP request to that URL
Step 3: Receive: status code + response headers + body bytes
Step 4: Store temporarily in processing buffer
Step 5: Pass to Function 2
Step 6: From what Function 2 discovers — find new addresses
Step 7: Follow those addresses autonomously — Phase 2 onwards
```

**What makes it genuine:**
No format assumptions. No Wikipedia hardcoding.
Any URL. Any response type. Any language. Any format.
Brain handles it all through Functions 2 and 3.

---

### Function 2 — Pattern Detection

**Input:** Raw bytes from Function 1
**Output:** Pattern clusters with frequency, position, adjacency data
**Storage:** Pattern inventory — grows continuously

Three signals only:
```
Frequency  → what appears often = important unit
Position   → where it appears = structural role  
Adjacency  → what appears next to what = relationship signal
```

**LLM role (Phase 1 only):**
LLM labels the first clusters: content / structure / addresses / metadata
After 1000 responses — brain labels its own clusters. LLM steps back.

---

### Function 3 — Symbol Discovery

**Input:** Pattern clusters from Function 2
**Output:** Symbol inventory with frequencies
**Storage:** Symbol table — every unique unit the brain has seen

```
Step 1: Find patterns that behave as atomic units
        (appear as wholes, combine with other wholes, repeat as wholes)
Step 2: These ARE symbols — words, numbers, tags, URLs
Step 3: Record every unique symbol with frequency
Step 4: Record what other symbols appear near each symbol
Step 5: Mark high-frequency symbols as core vocabulary
Step 6: Mark low-frequency symbols as rare — needs more confirmation
```

**Key:** Brain does not know what a word is. It discovers what behaves like a word.

---

### Function 4 — Emergent Ontology Construction

**Input:** Symbols from Function 3 + question answers from internet
**Output:** Living ontology — classes, properties, relationships for every concept
**Storage:** Ontology graph — grows and updates continuously

```
Step 1: For every symbol — generate questions about it
Step 2: Search internet for answers to those questions
Step 3: Cluster the answers by context
Step 4: From clusters discover:
        - What class this symbol belongs to
        - What properties describe it
        - What it depends on
        - What it produces
        - Where it appears
Step 5: Build ontological entry
Step 6: New questions emerge from discoveries
Step 7: Follow those questions into deeper understanding
```

**When brain does not understand something:**
Goes back to internet. Finds more examples. Clusters them.
Never asks us. Never asks LLM after Phase 1.
Internet is its teacher. Questions are its method.

---

### Function 5 — Context-Dependent Relationship Fields (CDRF)

**Input:** Ontological entries from Function 4
**Output:** Relationship fields — R(A, B, C) for every concept pair
**Storage:** Relationship field database — updatable, not fixed

This is the new formula. Does not exist anywhere.

```
Step 1: Take two concepts A and B
Step 2: Find every sentence where both appear
Step 3: For each appearance:
        - Record which came first (direction)
        - Record surrounding concepts (context C)
        - Calculate center of gravity of context (C as single point)
Step 4: Build the field R(A, B, C):
        - For each context point C — what is the strength and direction?
Step 5: Three filters must pass before relationship is stored as real:
        Filter 1: Direction consistent (position statistics)
        Filter 2: Independent sources confirm (source diversity check)
        Filter 3: Repetition across unrelated domains (convergence count)
Step 6: Store as: (A, B, context_point, strength, direction, source_count)
```

**What makes it not just counting:**
Direction + Independence + Repetition — all three required.
Not one filter. Three.

---

### Function 6 — Convergence Engine

**Input:** Relationship fields from Function 5
**Output:** Convergence points — hidden truths from independent origins
**Storage:** Convergence registry — the most important part of the brain

This is the core intelligence function. Does not exist properly anywhere.

```
Step 1: Pick any concept — grow branches following all relationships
        Concept → A → B → C → D (path 1)
        Concept → X → Y → Z → D (path 2, different)
        Concept → P → Q → R → D (path 3, completely different)
        D reached from 3 independent paths → convergence candidate

Step 2: Start from completely different seed concepts
        Fire → heat → energy → D
        Music → rhythm → pattern → D
        Biology → cell → signal → D
        All unrelated origins → all reaching D

Step 3: D is confirmed convergence point
        Strength = number of independent origins that reached it
        The more unrelated the origins — the stronger the truth

Step 4: D is stored as hidden truth
        Nobody programmed it. Nobody told the brain about D.
        It emerged from independent paths all arriving at the same place.

Step 5: D becomes a new seed
        Grow branches from D
        Find what converges toward D from deeper levels
        The convergence points of convergence points
        Deepest truths emerge
```

**The click:**
When a convergence point is found for the first time —
Two paths from completely unrelated origins meeting —
That IS the moment of intelligence.

---

### Function 7 — Answer Formation

**Input:** Question in any form
**Output:** Answer from internal knowledge only
**Storage:** None — answer built fresh each time

```
Step 1: Question arrives
Step 2: Identify concepts in question
Step 3: Determine which meaning cluster is being asked about
        (which context — philosophical fire? physical fire? emotional fire?)
Step 4: Activate all relationships of those concepts in CDRF
Step 5: Find convergence points related to the question
Step 6: Build answer from:
        - What this concept depends on
        - What it produces
        - Hidden convergences from unrelated origins
        - Connections nobody usually makes
Step 7: Validate: does answer correctly address what was asked?
        Yes → speak it
        No → go deeper, try again
Step 8: Gap detected → add to reading queue for Function 8
```

**Zero internet at answer time. Pure internal knowledge.**

---

### Function 8 — Continuous Self-Improvement

**Input:** Gaps detected in Function 7 + new addresses from Function 1
**Output:** Stronger connections, better ontology, deeper convergences
**Storage:** Updates all previous storage layers

```
Background (always running):
  Read new pages from frontier queue
  Extract new symbols
  Generate new questions
  Search answers
  Update ontology
  Strengthen confirmed relationships
  Weaken unconfirmed ones over time
  Find new convergences

Foreground (triggered by questions):
  When answer reveals a gap
  Gap added to priority reading queue
  Brain reads specifically to fill that gap
  Next time same question asked — better answer

The self-improvement loop:
Question → Answer → Gap → Read → Better Answer → Better Gap Detection
```

**Never frozen. Never stops. Always smarter than yesterday.**

---

## Storage Architecture

```
Layer 1 — Working Memory (RAM)
  Active connections being processed right now
  Instant access. Lost on shutdown. Feeds Layer 2.

Layer 2 — Ontology Graph (Neo4j)
  Every symbol = node with class + properties
  Every relationship = directed weighted edge
  Every convergence point = specially marked node
  Permanent. Grows forever.

Layer 3 — CDRF Store (Custom)
  R(A, B, C) field values for every concept pair
  Indexed by context point C
  Queryable by context region
  This is the new data structure nobody has built

Layer 4 — Context Vectors (ChromaDB)
  Every concept as mathematical vector
  Enables meaning-based search
  "Find concepts similar to growth" works even without the word

Layer 5 — Frontier Queue (Redis)
  All discovered addresses not yet visited
  All questions not yet answered
  Persists between runs. Never truly empty.

Layer 6 — Raw Buffer (Temporary)
  Current page being processed
  Discarded after extraction
  Content forgotten. Understanding kept.
```

---

## LLM Integration — Phases

### Phase 1 — Guided Entry
LLM provides first URL.
LLM labels first pattern clusters.
LLM gives first set of question templates.
Brain absorbs and begins.

### Phase 2 — Occasional Verification
Brain explores independently.
When uncertain — asks LLM to verify a specific connection.
Not for knowledge. For confidence calibration.
LLM does not explain. Just confirms or corrects.

### Phase 3 — Full Autonomy
Brain makes every decision.
Generates its own questions.
Finds its own answers.
Verifies its own connections through convergence.
LLM disconnected.

**Transition trigger:**
When brain correctly generates questions we never gave it.
When it finds convergences we did not predict.
When it navigates to addresses it discovered entirely on its own.

---

## Build Order — Week by Week

```
Week 1 — Function 1 + 2
  Real HTTP reception from any URL
  Pattern detection from raw bytes
  No format assumptions

Week 2 — Function 3
  Symbol discovery from patterns
  Symbol inventory with frequencies

Week 3 — Function 4 Part A
  Question generation
  Internet search for answers
  Answer clustering

Week 4 — Function 4 Part B
  Emergent ontology construction
  Class, property, relationship discovery

Week 5 — Function 5
  CDRF implementation
  Context-Dependent Relationship Fields
  Three-filter validation

Week 6 — Function 6
  Convergence engine
  Hidden truth detection
  Convergence registry

Week 7 — Function 7
  Answer formation
  Gap detection
  Self-validation

Week 8 — Function 8 + Integration
  Continuous learning loop
  All functions connected
  Full system running
```

---

## What We Build Today

**Function 1 — Raw Signal Reception**

Properly. Genuinely. No assumptions.

Any URL. Any response. Status + headers + body.
Temporary buffer. Passes to Function 2.
Discovers new addresses from what it learns.

That is all. Clean. Simple. Real.

---

*Architecture v2 complete.*
*Foundation: existing research.*
*New: CDRF + Convergence Engine + Zero-instruction emergent ontology.*
*Build starts today. Function 1.*
