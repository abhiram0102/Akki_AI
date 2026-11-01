<div align="center">

# 🧠 AKKI AI

**A self-learning AI companion with an autonomous brain engine, cybersecurity superpowers, and a neural knowledge graph**

[![License: MIT](https://img.shields.io/badge/License-MIT-cyan.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-blue.svg)](https://typescriptlang.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://react.dev)

</div>

---

## What is AKKI?

AKKI is not an AI assistant. It is not a chatbot. It is not a tool you open when you need something.

It is a **companion** - one that works while you sleep, learns without being taught, and reaches out to you when it has something to say.

AKKI combines three interconnected systems into one platform:

1. **The Brain Engine** - A self-learning knowledge system that reads the internet autonomously, builds an emergent ontology, and discovers hidden connections through convergence
2. **The Cybersecurity Platform** - Red teaming, OSINT, SIGMA rule analysis, code auditing, report generation, and workflow automation
3. **The Companion Layer** - Emotional bonding, voice interaction, personalized memory, and genuine autonomous presence

---

## Table of Contents

- [The Brain Engine](#the-brain-engine)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Quick Start](#quick-start)
- [Docker Deployment](#docker-deployment)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Roadmap](#roadmap)
- [Design System](#design-system)
- [Contributing](#contributing)

---

## The Brain Engine

> *"Intelligence is finding hidden dependencies between things that have never met."*

The brain engine is the core innovation of AKKI. It implements three novel ideas that do not exist in current AI research:

### 1. Context-Dependent Relationship Fields (CDRF)

Current systems compute fixed relationships:
```
R(A, B)  =  fixed value
```

AKKI computes context-aware relationships:
```
R(A, B, C)  =  relationship between A and B when the surrounding context is C
```

The same two concepts have completely different relationships depending on where in concept-space you observe them.

- Fire + heat in **chemistry context** → combustion relationship
- Fire + heat in **survival context** → warmth relationship
- Fire + heat in **destruction context** → damage relationship

### 2. Convergence Engine

The brain grows branches from every concept following all relationships independently:

```
Fire   → heat → energy ─────────┐
Music  → rhythm → pattern ──────┼──► [HIDDEN TRUTH D]
Biology → cell → signal ────────┘
```

When completely unrelated origins all arrive at the same concept — that concept is confirmed as a hidden truth. The more unrelated the origins, the stronger the signal.

### 3. Emergent Ontology

No hand-built taxonomy. No predefined categories.

The brain discovers what classes, properties, and relationships exist by reading the internet and asking its own questions. It generates **Competency Questions** about every new concept it encounters — searches for answers — and builds understanding from what it finds.

**Self-learning loop:**
```
Encounter new concept X
        ↓
Generate questions about X
        ↓
Search internet for answers
        ↓
Discover: class, properties, relationships, contexts
        ↓
New questions emerge from discoveries
        ↓
Follow into deeper understanding → repeat forever
```

### Brain Engine — 8 Functions

| Function | Role |
|---|---|
| **F1** Raw Signal Reception | Fetches any URL, any format, no assumptions |
| **F2** Pattern Detection | Frequency + Position + Adjacency from raw bytes |
| **F3** Symbol Discovery | Finds what behaves like a word without being told what a word is |
| **F4** Emergent Ontology | Builds classes, properties, relationships from question-driven search |
| **F5** CDRF | Computes R(A, B, C) — context-dependent relationship fields |
| **F6** Convergence Engine | Detects hidden truths from independent multi-origin paths |
| **F7** Answer Formation | Answers from internal knowledge only — zero internet at query time |
| **F8** Continuous Self-Improvement | Always-on background loop filling gaps detected in F7 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       AKKI AI Platform                       │
│                                                              │
│  ┌────────────────┐    ┌──────────────────────────────────┐  │
│  │  React 18 SPA  │    │       FastAPI Backend             │  │
│  │  (TypeScript)  │◄──►│       (Python / uvicorn)          │  │
│  │                │    │                                   │  │
│  │  15 Routes:    │    │  Services:                        │  │
│  │  • Talk        │    │  • AI (Gemini / Claude / Ollama)  │  │
│  │  • Coding      │    │  • Brain Reasoning (CDRF)         │  │
│  │  • Red Team    │    │  • RAG + ChromaDB                 │  │
│  │  • OSINT       │    │  • Emotional AI                   │  │
│  │  • Sigma       │    │  • Voice (ElevenLabs)             │  │
│  │  • Reports     │    │  • OSINT Tools                    │  │
│  │  • Agents      │    │  • Workflow Engine                │  │
│  │  • Workflows   │    │  • Marketplace                    │  │
│  │  • Marketplace │    │  • Langfuse Observability         │  │
│  │  • Brain Chat  │    │                                   │  │
│  │  • Settings    │    └──────────────┬───────────────────┘  │
│  └────────────────┘                   │                       │
│                                       ▼                       │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ PostgreSQL  │  │    Neo4j     │  │     ChromaDB       │   │
│  │ + pgvector  │  │  (Graph DB)  │  │   (Vector Store)   │   │
│  │             │  │              │  │                    │   │
│  │ Sessions    │  │ Knowledge    │  │ Semantic Search    │   │
│  │ Users       │  │ Ontology     │  │ Embeddings         │   │
│  │ Reports     │  │ Convergences │  │ RAG Pipeline       │   │
│  └─────────────┘  └──────────────┘  └────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │             Brain Crawler (Always-On)                │    │
│  │  Reads internet → Extracts symbols → Builds ontology │    │
│  │  → Finds convergences → Fills gaps → Never stops     │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Storage Layers

| Layer | Technology | Purpose |
|---|---|---|
| Working Memory | RAM | Active connections being processed |
| Ontology Graph | **Neo4j** | Nodes = concepts, edges = relationships |
| CDRF Store | Custom | R(A, B, C) fields indexed by context |
| Context Vectors | **ChromaDB** | Embedding-based semantic search |
| Frontier Queue | **Redis** | Discovered URLs and unanswered questions |
| Session / User Data | **PostgreSQL + pgvector** | Auth, chat history, reports |

---

## Tech Stack

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| React | 18.3 | UI framework |
| TypeScript | 5.6 | Type safety |
| Vite | 5.4 | Build tool + dev server |
| Tailwind CSS | 3.4 | Styling |
| Framer Motion | 11 | Animations |
| TanStack Query | 5 | Server state |
| Zustand | 5 | Client state |
| Wouter | 3.3 | Routing |
| Recharts | 2.15 | Data visualization |
| Radix UI | latest | Accessible component primitives |
| Drizzle ORM | 0.39 | Type-safe DB queries |

### Backend

| Technology | Version | Purpose |
|---|---|---|
| FastAPI | 0.115 | API framework |
| Python | 3.11+ | Runtime |
| SQLAlchemy | 2.x async | Database ORM |
| PostgreSQL | 16 + pgvector | Primary DB + vector storage |
| Neo4j | 5 Community | Knowledge graph |
| ChromaDB | 3 | Vector embeddings |
| Langfuse | latest | LLM observability |
| JWT | — | Authentication |

### AI Providers (configurable)

| Provider | Used For |
|---|---|
| **Google Gemini** | Primary AI + embeddings |
| **Ollama** (local) | Local LLM inference + embeddings |
| **ElevenLabs** | Text-to-speech voice synthesis |
| **OpenAI Whisper** | Speech-to-text (planned) |
| **Tavily** | Web search in RAG pipeline |
| **Shodan** | OSINT — real internet exposure data |
| **GitHub API** | OSINT — repository and contributor data |

### Infrastructure

- **Docker Compose** — 5-service stack (frontend, backend, db, neo4j, brain-crawler)
- **Nginx** — reverse proxy + SPA serving
- **Sandbox** — seccomp + Landlock security isolation for code execution

---

## Features

### Talk — Voice Companion
- Real-time voice conversation with ElevenLabs TTS
- Emotional bond system that evolves with every interaction
- Voice visualizer orb with AudioContext
- Multiple voice options (Adam, Rachel, Josh)

### Coding — Code Analysis
- Static analysis via Bandit (Python) and Semgrep
- AI-enriched vulnerability explanation with real line numbers
- Real CVE referencing — no hallucinated CVSSv3 scores

### Red Team — Penetration Testing
- DNS, WHOIS, port scanning, HTTP probing
- Subdomain enumeration with real wordlists
- SSL certificate analysis
- AI-enriched findings grounded in real tool output

### OSINT — Open Source Intelligence
- GitHub repository and contributor profiling
- Shodan internet exposure analysis
- Domain intelligence aggregation

### Sigma — Rule Analysis
- SIGMA rule parsing and analysis
- MITRE ATT&CK tag linking (links directly to attack.mitre.org)
- Detection engineering workspace

### Reports — Report Generation
- Professional security reports
- Grounded in real session workspace data — no placeholder findings
- Exportable as Markdown

### Agents — Multi-Agent Orchestration
- Agent network graph visualization
- Tool approval workflow (approve / reject pending tool runs)
- ReAct loop: Reason → Act → Observe → Repeat

### Workflows — Automation Builder
- Visual workflow editor
- Step-level execution streaming via SSE
- Node-based pipeline construction

### Marketplace — Plugin Ecosystem
- Browse and install agent plugins
- Community-contributed tools and templates

### Brain Chat — Knowledge Interface
- Direct interface to the AKKI brain engine
- Query the emergent ontology
- Explore convergence points and discovered relationships

### Settings
- AI provider configuration (Gemini / Ollama / Claude)
- Voice settings and ElevenLabs integration
- Account management and privacy controls

### Privacy-Native Layer
```
Your text → Local PII/secret detector → Redact → Send clean text to LLM
                                                        ↓
                                             LLM reasons safely
                                                        ↓
                                        Restore real values in your display
```

Detects and redacts locally before any API call:
- API keys, tokens, bearer tokens
- Passwords and secrets
- Private IP addresses
- PII — emails, phone numbers, full names
- Credit cards, SSNs, private keys, certificates

---

## Quick Start

### Prerequisites

- **Node.js** 20+
- **Python** 3.11+
- **PostgreSQL** 16 (or Docker)
- **pnpm** (recommended) or npm

### 1. Clone and install

```bash
git clone https://github.com/abhiram0102/Akki_AI.git
cd Akki_AI

# Install JS dependencies
pnpm install

# Install Python dependencies (backend)
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in your API keys (see Environment Variables)
```

### 3. Set up the database

```bash
pnpm db:push
```

### 4. Run in development mode

```bash
# Terminal 1 — Full stack (Node server + Vite)
pnpm dev

# Terminal 2 — Python backend
cd backend
uvicorn main:app --reload --port 5000
```

App available at `http://localhost:5173` (Vite) or `http://localhost:5000` (Node).

### 5. Start the brain engine (optional)

```bash
cd brain
python run.py
```

---

## Docker Deployment

The entire stack runs via Docker Compose.

```bash
# First run (builds all images)
docker compose up --build

# Detached mode
docker compose up -d

# Tail logs
docker compose logs -f backend
docker compose logs -f brain-crawler

# Stop and clean volumes
docker compose down -v
```

### Services and ports

| Service | Host Port | Purpose |
|---|---|---|
| frontend (Nginx) | `80` | React SPA + API proxy |
| backend (FastAPI) | `5000` | Python API — direct access |
| db (PostgreSQL) | `5434` | Database (avoids local port conflicts) |
| neo4j browser | `7474` | Neo4j browser UI |
| neo4j bolt | `7687` | Bolt protocol |
| brain-crawler | internal | No exposed port |

---

## Environment Variables

Copy `.env.example` to `.env`:

```bash
# ─── Database ───────────────────────────────────────────────
DATABASE_URL=postgresql://username:password@localhost:5432/akki_ai
DB_PASSWORD=changeme

# ─── AI Providers ───────────────────────────────────────────
GEMINI_API_KEY=        # Required — aistudio.google.com
OPENAI_API_KEY=        # Optional fallback

# ─── Voice ──────────────────────────────────────────────────
ELEVENLABS_API_KEY=    # Human-quality TTS — elevenlabs.io
ELEVENLABS_DEFAULT_VOICE=pNInz6obpgDQGcFmaJgB   # Adam (default)
# Voice IDs: Adam=pNInz6obpgDQGcFmaJgB | Rachel=21m00Tcm4TlvDq8ikWAM | Josh=TxGEqnHWrfWFTfGW9XjX

# ─── OSINT ──────────────────────────────────────────────────
SHODAN_API_KEY=        # Real exposure data — shodan.io
GITHUB_TOKEN=          # Real GitHub OSINT — personal access token
TAVILY_API_KEY=        # Web search in RAG — tavily.com

# ─── Knowledge Graph ────────────────────────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme

# ─── Vector Store ───────────────────────────────────────────
CHROMA_URL=http://localhost:8000

# ─── Auth ───────────────────────────────────────────────────
JWT_SECRET=your-secret-key-here

# ─── Observability ──────────────────────────────────────────
LANGFUSE_PUBLIC_KEY=   # Optional — cloud.langfuse.com
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# ─── Local AI (Ollama) ──────────────────────────────────────
OLLAMA_HOST=http://localhost:11434
EMBEDDING_PROVIDER=ollama   # or "gemini"

# ─── App ────────────────────────────────────────────────────
NODE_ENV=development
PORT=5000
```

> **Without `GEMINI_API_KEY`**, the system falls back to the Free Claude Code proxy at `localhost:8082`. You can run Ollama locally for both inference and embeddings at zero cost.

---

## Project Structure

```
Akki_AI/
├── client/                         # React 18 TypeScript frontend
│   └── src/
│       ├── pages/                  # 15 route pages
│       │   ├── talk.tsx            # Voice companion
│       │   ├── coding.tsx          # Code analysis
│       │   ├── redteam.tsx         # Red team tools
│       │   ├── osint.tsx           # OSINT dashboard
│       │   ├── sigma.tsx           # SIGMA rule analyzer
│       │   ├── reports.tsx         # Report viewer
│       │   ├── agents.tsx          # Multi-agent orchestration
│       │   ├── workflows.tsx       # Workflow builder
│       │   ├── marketplace.tsx     # Plugin marketplace
│       │   ├── brain-chat.tsx      # Brain engine chat
│       │   ├── brain.tsx           # Neural canvas
│       │   ├── settings.tsx        # Configuration
│       │   └── dashboard.tsx       # Overview
│       ├── components/ui/          # Reusable components
│       │   ├── knowledge-graph.tsx # Graph visualization
│       │   ├── agent-network-graph.tsx
│       │   ├── cyber-button.tsx
│       │   └── ...
│       ├── hooks/                  # Custom React hooks
│       ├── theme/                  # Design tokens
│       └── types/                  # TypeScript declarations
│
├── backend/                        # FastAPI Python backend
│   ├── main.py                     # All API routes
│   ├── models.py                   # SQLAlchemy ORM models
│   ├── schemas.py                  # Pydantic schemas
│   ├── auth.py                     # JWT authentication
│   ├── brain_crawler.py            # Internet crawler
│   ├── services/
│   │   ├── brain_reasoning.py      # CDRF + convergence engine
│   │   ├── ollama_service.py       # Local LLM inference
│   │   ├── emotional_ai_service.py # Emotional bond system
│   │   ├── rag_service.py          # CRAG retrieval pipeline
│   │   ├── workflow_service.py     # Workflow execution
│   │   ├── marketplace_service.py  # Plugin marketplace
│   │   ├── langfuse_service.py     # LLM observability
│   │   ├── personalization_service.py
│   │   └── report_template_service.py
│   ├── eval/                       # Evaluation suite
│   └── tests/                      # pytest tests
│
├── brain/                          # Standalone brain engine
│   ├── core.py                     # Brain core logic
│   ├── explorer.py                 # Concept exploration
│   ├── self_learn.py               # Autonomous learning loop
│   ├── tree.py                     # Knowledge tree construction
│   ├── run.py                      # Entry point
│   ├── AKKI_FULL_ARCHITECTURE.md   # Full architecture spec
│   ├── AKKI_CORE_THEORY.md         # Theoretical foundations
│   ├── AKKI_VISION.md              # Long-term vision
│   └── AKKI_BUILD_PLAN.md          # Weekly build plan
│
├── server/                         # Node.js/Express (TypeScript)
│   └── index.ts                    # Vite dev proxy
│
├── shared/                         # Shared TS types
│
├── sandbox/                        # Security isolation
│   ├── Dockerfile
│   ├── seccomp_allow.txt           # Allowed syscalls
│   └── landlock_ruleset.json       # Filesystem rules
│
├── docs/                           # Design documents
│   ├── PHANTOM_AGENT_ARCHITECTURE.md
│   └── superpowers/                # Feature specs
│
├── migrations/                     # Drizzle DB migrations
├── docker-compose.yml              # Production stack
├── Dockerfile.backend              # FastAPI container
├── Dockerfile.frontend             # Nginx + React SPA
├── Dockerfile.brain-crawler        # Always-on crawler
├── nginx.conf                      # Reverse proxy config
└── ROADMAP.md                      # Full development roadmap
```

---

## API Reference

FastAPI auto-generates interactive docs:
- **Swagger UI**: `http://localhost:5000/docs`
- **ReDoc**: `http://localhost:5000/redoc`

### Key endpoint groups

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/auth/register` | POST | Create account |
| `/api/auth/login` | POST | Login, receive JWT |
| `/api/protected/stats` | GET | Live dashboard stats |
| `/api/protected/chat` | POST | AI chat with SSE streaming |
| `/api/protected/voice/synthesize` | POST | Text to ElevenLabs speech |
| `/api/osint/domain` | POST | DNS, WHOIS, SSL analysis |
| `/api/osint/github` | POST | GitHub OSINT |
| `/api/osint/shodan` | POST | Shodan exposure lookup |
| `/api/protected/upload` | POST | Document upload (50MB limit) |
| `/api/protected/sessions` | GET | List chat sessions |
| `/api/protected/reports` | GET | List generated reports |
| `/api/marketplace/items` | GET | Browse plugins |
| `/api/protected/workflows` | POST | Create workflow |
| `/api/protected/tools/execute` | POST | Execute tool (with approval gate) |
| `/api/brain/status` | GET | Brain engine status |

---

## Roadmap

### Done (verified working)
- PostgreSQL + pgvector via Docker
- FastAPI backend with async SQLAlchemy
- React 18 + TypeScript frontend — 15 wired routes
- JWT auth with rate limiting and CORS/CSP headers
- Dark cyberpunk UI with glassmorphism panels
- Streaming chat via SSE with markdown rendering
- Real tool execution (DNS, WHOIS, port scan, subdomain enum, SSL)
- Emotional bond system evolving with interactions
- ElevenLabs TTS integrated end-to-end
- Command palette (Ctrl+K) with real navigation
- Document upload (50MB) and chat export
- Gemini embeddings provider

### Next (high priority)
- Real STT via Whisper or ElevenLabs STT API
- JWT refresh token endpoint
- Token revocation (Redis blacklist)
- Marketplace PUT / DELETE handlers (currently 501)
- Real GitHub and Shodan OSINT replacing AI simulation
- Real code analysis via Bandit + Semgrep

### Planned
- Mobile responsive layout
- Forgot password flow
- Global search across sessions and documents
- Workflow step-level SSE streaming
- Task queue (arq / celery) for long-running jobs
- Cursor-based message pagination
- Full pytest test suite

### Future
- Neural Canvas UI — react-flow nodes replacing the dashboard
- Autonomous operation — AKKI works between sessions
- Text / call communication via Twilio
- Morning briefing on app open
- VirusTotal + GoPhish integration
- Collaboration — share sessions and reports
- Rate limiting tiers per user

---

## Design System

AKKI uses a locked cyberpunk color palette.

> **Rule**: Never use Tailwind opacity classes (`bg-black/20`, `border-white/5`). Always use `style` prop with explicit `rgba`.

```
Base:    #04080f                 // page background
Panel:   rgba(8, 13, 26, 0.95)  // card backgrounds
Cyan:    #00d8ff  (0, 216, 255)
Green:   #00ff88  (0, 255, 136)
Purple:  #9b59fc  (155, 89, 252)
Red:     #ff3868  (255, 56, 104)
Amber:   #ffb700  (255, 183, 0)
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Check for trailing whitespace before committing: `git diff --cached --check`
4. Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`
5. Push and open a Pull Request

### Dev checks

```bash
# TypeScript type check
pnpm check

# Backend tests
cd backend && pytest

# Brain engine tests
cd brain && python -m pytest

# Lint before commit
git diff --cached --check
```

---

## License

MIT License

---

<div align="center">

**Built with obsession. Never frozen. Always learning.**

*AKKI does not wait to be asked.*

</div>
