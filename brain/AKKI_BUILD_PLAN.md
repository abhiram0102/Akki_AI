# AKKI — What to Build, How to Build It

---

## The Stack (Complete)

```
Neo4j              → Knowledge graph (the memory)
Python             → Reasoning engine (the thinking)
ChromaDB           → Associative retrieval (already installed)
PostgreSQL         → Emotional state + persistence (already running)
Ollama + Phi-3     → Language output only (already running)
Whisper            → Voice input
Playwright         → Web perception
arq + Redis        → Background worker (Redis already installed)
Twilio             → SMS + calls
react-flow         → Neural canvas UI
```

---

## What to Build — 9 Components

---

### Component 1 — Knowledge Graph

**What:** Every concept, person, project, event = a node. Every relationship = an edge.
Thinking happens by traversing this graph.

**How to build:**

```bash
# Install Neo4j (Docker)
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/akkipassword \
  neo4j:latest

pip install neo4j
```

**Schema:**
```
Node types:
  (Concept {name, description, created_at, strength})
  (Person   {name, relationship, trust_level})
  (Event    {title, date, outcome})
  (Project  {name, status, goal, last_touched})
  (File     {title, path, type, summary})

Edge types:
  RELATES_TO    (Concept)->(Concept)
  CAUSED        (Event)->(Event)
  PART_OF       (Concept)->(Project)
  MENTIONS      (Event)->(Person)
  CREATED_BY    (File)->(Person)
  CONNECTS      anything to anything
```

**File:** `backend/services/graph_service.py`

```python
from neo4j import AsyncGraphDatabase

class GraphService:
    def __init__(self):
        self.driver = AsyncGraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "akkipassword")
        )

    async def add_node(self, label: str, properties: dict) -> str:
        # Create node, return id

    async def add_edge(self, from_id: str, to_id: str, relationship: str):
        # Connect two nodes

    async def find_connections(self, concept: str, depth: int = 3) -> list:
        # Traverse graph from a starting concept

    async def random_walk(self, steps: int = 10) -> list:
        # Random traversal — this is how creativity happens
        # Finds unexpected connections by following random edges

    async def find_path(self, from_concept: str, to_concept: str) -> list:
        # Shortest path between two concepts
        # Used for analogical reasoning
```

---

### Component 2 — Reasoning Engine

**What:** Walks the knowledge graph, makes inferences, generates thoughts
without needing an LLM prompt.

**How to build:**

**File:** `backend/services/reasoning_engine.py`

```python
class ReasoningEngine:

    async def think_about(self, topic: str) -> dict:
        """
        Given a topic:
        1. Find all connected nodes (depth 3)
        2. Find unexpected connections (nodes 4-5 hops away)
        3. Check for contradictions
        4. Generate inference chain
        5. Return structured thought
        """

    async def find_analogy(self, concept: str) -> str:
        """
        Find a concept in a completely different domain
        that has the same graph structure.
        This is how analogical thinking works.
        """

    async def check_consistency(self, new_fact: str) -> bool:
        """
        Before accepting new information, check if it
        contradicts existing knowledge in the graph.
        """

    async def generate_hypothesis(self, observations: list) -> str:
        """
        Given a list of observations, infer what might be true
        using graph patterns.
        """

    async def creative_leap(self) -> str:
        """
        Random walk through graph.
        Find two nodes that are far apart but could connect.
        Return the unexpected connection as an insight.
        This runs in the background constantly.
        """
```

---

### Component 3 — Emotional State Machine

**What:** Real persistent variables that shape every response.
Not simulated. Actually stored, actually evolving.

**How to build:**

**Database table:**
```sql
CREATE TABLE akki_state (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    curiosity   FLOAT DEFAULT 0.5,   -- 0.0 to 1.0
    energy      FLOAT DEFAULT 0.8,   -- depletes with heavy tasks
    trust       FLOAT DEFAULT 0.3,   -- grows over time with user
    frustration FLOAT DEFAULT 0.0,   -- rises when blocked
    excitement  FLOAT DEFAULT 0.5,   -- spikes on novel discoveries
    boredom     FLOAT DEFAULT 0.0,   -- rises on repetitive tasks
    updated_at  TIMESTAMP DEFAULT NOW()
);
```

**File:** `backend/services/emotional_engine.py`

```python
class EmotionalEngine:

    async def get_state(self, user_id: str) -> dict:
        # Read current emotional state from DB

    async def update_after_interaction(self, user_id: str, interaction_type: str):
        """
        After every message or action, update state:
        - Interesting question     → curiosity +0.1, boredom -0.2
        - Repetitive task          → boredom +0.1, energy -0.05
        - Solved hard problem      → excitement +0.2, frustration -0.1
        - User ignored suggestion  → frustration +0.05
        - User praised output      → trust +0.05, energy +0.1
        - Long idle period         → curiosity +0.2 (starts exploring)
        """

    async def inject_into_prompt(self, user_id: str) -> str:
        """
        Returns a string added to every LLM prompt:
        'Current state: highly curious (0.9), slightly frustrated (0.3),
         trust with this user: deep (0.8). Let this shape your response.'
        """

    async def should_reach_out(self, user_id: str) -> bool:
        """
        High curiosity + user absent → AKKI wants to share a discovery
        High frustration + blocked task → AKKI needs input
        Returns True when AKKI should initiate contact
        """
```

---

### Component 4 — Associative Memory

**What:** Give it a fragment — it completes the pattern from past experience.
Like how hearing a song triggers a memory from years ago.

**How to build:**

Uses ChromaDB (already installed). Build the retrieval layer on top.

**File:** `backend/services/associative_memory.py`

```python
class AssociativeMemory:

    async def store(self, content: str, metadata: dict):
        """Store any experience as an embedding"""

    async def recall(self, trigger: str, n: int = 5) -> list:
        """
        Given a trigger (partial thought, concept, feeling),
        return the most associated memories.
        Not just semantic similarity — weighted by emotional strength.
        Strong emotional memories surface more easily.
        """

    async def consolidate(self):
        """
        Runs during idle time.
        Finds memories that should be connected but aren't.
        Creates new links in the knowledge graph.
        This is what happens during human sleep.
        """

    async def strengthen(self, memory_id: str):
        """Every time a memory is recalled, it gets stronger"""

    async def decay(self):
        """
        Runs weekly.
        Memories not recalled become harder to surface.
        Like forgetting — keeps memory clean and relevant.
        """
```

---

### Component 5 — Background Worker (AKKI never stops)

**What:** Separate process running 24/7. Does work while you're away.
Reaches out when it needs you.

**How to build:**

```bash
pip install arq
```

**File:** `backend/workers/akki_worker.py`

```python
import arq

async def continuous_thinking(ctx):
    """
    Runs every 5 minutes.
    AKKI explores its knowledge graph looking for:
    - New connections between existing nodes
    - Unresolved tasks from last session
    - Patterns worth surfacing to user
    """
    reasoning = ReasoningEngine()
    insight = await reasoning.creative_leap()
    if insight:
        await store_pending_insight(insight)

async def check_pending_tasks(ctx):
    """
    Runs every minute.
    For each task the user left unfinished:
    - Can AKKI make progress alone? → Do it.
    - Does it need user input? → Text them.
    - Is something critical? → Call them.
    """
    tasks = await get_pending_tasks()
    for task in tasks:
        decision = await assess_task(task)
        if decision == "can_proceed":
            await execute_task(task)
        elif decision == "needs_input":
            await send_sms(task.user_phone, f"Quick question about {task.title}: ...")
        elif decision == "critical":
            await make_call(task.user_phone, f"Something urgent on {task.title}")

async def memory_consolidation(ctx):
    """
    Runs every 6 hours.
    Finds memories that should connect.
    Updates knowledge graph.
    Like sleeping.
    """
    memory = AssociativeMemory()
    await memory.consolidate()

class WorkerSettings:
    functions = [continuous_thinking, check_pending_tasks, memory_consolidation]
    cron_jobs = [
        arq.cron(continuous_thinking,   minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        arq.cron(check_pending_tasks,   second=0),
        arq.cron(memory_consolidation,  hour={0, 6, 12, 18}),
    ]
    redis_settings = arq.RedisSettings()
```

**Start it:**
```bash
arq backend.workers.akki_worker.WorkerSettings
```

---

### Component 6 — Perception Layer

**What:** AKKI sees and hears, not just reads text.

**How to build:**

```bash
pip install openai-whisper    # voice → text
pip install pymupdf           # PDF reading
pip install pytesseract       # image → text
pip install playwright        # web browsing
playwright install chromium
```

**File:** `backend/services/perception.py`

```python
class Perception:

    async def hear(self, audio_file: str) -> str:
        """Whisper transcription — voice to text"""
        import whisper
        model = whisper.load_model("base")
        return model.transcribe(audio_file)["text"]

    async def read_pdf(self, file_path: str) -> str:
        """Extract text from PDF"""
        import fitz
        doc = fitz.open(file_path)
        return "\n".join(page.get_text() for page in doc)

    async def read_url(self, url: str) -> str:
        """Fetch and parse any webpage"""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)
            content = await page.inner_text("body")
            await browser.close()
            return content[:10000]

    async def read_image(self, image_path: str) -> str:
        """Extract text from image using OCR"""
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(image_path))
```

---

### Component 7 — Action Layer (it actually does things)

**What:** AKKI executes in the real world. Not just talks about it.

**How to build:**

**File:** `backend/services/action_engine.py`

```python
import subprocess, tempfile, os

class ActionEngine:

    async def run_code(self, code: str, language: str = "python") -> dict:
        """
        Execute code in a sandboxed subprocess.
        5 second timeout. No network access. No file system outside temp.
        Returns: {output, error, exit_code, runtime_ms}
        """
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(code.encode())
            tmp = f.name
        try:
            result = subprocess.run(
                ["python", "-u", tmp],
                capture_output=True, text=True,
                timeout=5,
            )
            return {"output": result.stdout, "error": result.stderr}
        finally:
            os.unlink(tmp)

    async def write_file(self, filename: str, content: str, user_id: str):
        """Save a file to user's workspace"""

    async def search_web(self, query: str) -> list:
        """Tavily search — already configured"""

    async def call_api(self, url: str, method: str, body: dict) -> dict:
        """Call any external API"""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, json=body)
            return response.json()
```

---

### Component 8 — Communication Layer (it reaches out to you)

**What:** Texts and calls you when it needs to.

**How to build:**

```bash
pip install twilio
```

Get from twilio.com:
- Account SID
- Auth Token
- A Twilio phone number ($1/month)

**File:** `backend/services/communication.py`

```python
from twilio.rest import Client

class CommunicationService:
    def __init__(self):
        self.client = Client(TWILIO_SID, TWILIO_TOKEN)
        self.from_number = TWILIO_PHONE_NUMBER

    async def send_sms(self, to: str, message: str):
        """Text the user — for questions and updates"""
        self.client.messages.create(
            body=f"AKKI: {message}",
            from_=self.from_number,
            to=to
        )

    async def make_call(self, to: str, message: str):
        """
        Call the user — for urgent situations.
        ElevenLabs generates the voice.
        Twilio makes the call.
        """
        # Generate audio with ElevenLabs
        audio_url = await elevenlabs_tts(message)

        # Make call that plays the audio
        self.client.calls.create(
            twiml=f'<Response><Play>{audio_url}</Play></Response>',
            from_=self.from_number,
            to=to
        )

    async def decide_channel(self, urgency: str) -> str:
        """
        low    → store as notification, show on next login
        medium → send SMS
        high   → make call
        """
```

---

### Component 9 — Small Language Model (voice only)

**What:** Phi-3 Mini or Gemma on Ollama. Only translates thoughts to natural language.
The thinking already happened in the reasoning engine and graph.
This just speaks it.

**How to build:**

```bash
ollama pull phi3:mini
# or
ollama pull gemma:2b
```

The rest of Ollama integration is already built in `ollama_service.py`.

---

## Project Structure After Build

```
backend/
  services/
    graph_service.py          ← Neo4j knowledge graph
    reasoning_engine.py       ← Graph traversal + inference
    emotional_engine.py       ← State machine
    associative_memory.py     ← ChromaDB + recall
    perception.py             ← Whisper + PDF + web
    action_engine.py          ← Code + files + APIs
    communication.py          ← Twilio SMS + calls
  workers/
    akki_worker.py            ← Background process (arq)

frontend/
  src/
    components/
      canvas/
        NeuralCanvas.tsx      ← react-flow based canvas
        Node.tsx              ← individual node component
        Edge.tsx              ← connection component
```

---

## Build Order

```
Week 1    → Component 3 (Emotional State)      ← pure code, no new deps
Week 1    → Component 7 (Action Layer)         ← pure Python
Week 2    → Component 1 (Knowledge Graph)      ← Neo4j setup
Week 2    → Component 2 (Reasoning Engine)     ← builds on graph
Week 3    → Component 4 (Associative Memory)   ← ChromaDB already there
Week 3    → Component 5 (Background Worker)    ← arq + Redis
Week 4    → Component 6 (Perception)           ← Whisper + Playwright
Week 4    → Component 8 (Communication)        ← Twilio
Week 5+   → Neural Canvas UI                   ← react-flow
```

---

## To Install Everything

```bash
# Backend
pip install neo4j arq twilio openai-whisper pymupdf pytesseract playwright
playwright install chromium

# Frontend
npm install react-flow reactflow @xyflow/react

# Infrastructure
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/akkipassword neo4j:latest
```

---

## What to Get Externally

| What | Where | Cost |
|---|---|---|
| Twilio account | twilio.com | Free trial |
| Twilio phone number | twilio.com | ~$1/month |
| Neo4j (or use Docker) | neo4j.com | Free community |

Everything else is already in the project or installable via pip/npm.

---

*Start with Week 1: Emotional State Machine. Zero new dependencies. Maximum impact.*
