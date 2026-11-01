# AKKI AI — Complete Development Roadmap

## ✅ DONE (verified working)

### Infrastructure
- PostgreSQL + pgvector running via Docker Compose
- FastAPI backend with async SQLAlchemy
- Vite + React 18 + TypeScript frontend
- JWT authentication (login, register)
- Rate limiting on all public endpoints

### Frontend
- Dark cyberpunk UI with glassmorphism panels (inline rgba, not Tailwind opacity)
- 3-column layout: Nav rail | Main content | Context panel
- **All 15 routes wired** (Talk, Coding, RedTeam, OSINT, Tutor, Reports, Agents, Workflows, Marketplace, Settings, Demo)
- **PrivateRoute auth guard** on all non-login routes
- Chat interface with streaming SSE, markdown rendering, copy/regenerate buttons
- Dashboard with live stats from real DB queries (no more hardcoded numbers)
- **Settings page** with AI config, voice settings, account management
- **Command palette** (Ctrl+K) with real navigation + target-prompting commands
- Context panel with document upload, emotional state, pending tool approvals
- **Approve/Reject buttons** on pending tool runs (wired to real execution)
- **Export Chat** downloads real Markdown file
- Scroll-to-bottom FAB in chat
- Date separators in chat
- MITRE tags link to attack.mitre.org
- ElevenLabs TTS integrated (see setup below)
- Voice orb on Talk page functional end-to-end
- **AudioContext** created on nav rail mount (voice visualizer works)
- **Session URL params** load correct session on navigation
- **Bond level** actually evolves with chat interactions

### Backend
- **Real tool execution** — DNS, WHOIS, port scan, HTTP probe, subdomain enum, SSL (tool_service.py wired)
- **OSINT domain** uses real dig/whois/curl tools + AI enrichment
- **Emotional bond** updates on every chat interaction
- **Real stats endpoint** `/api/protected/stats`
- **No fake baseline findings** — only real user-generated data
- **No CVE-2023-XXXX placeholder** in reports
- Reports grounded in real session workspace data
- **CORS fixed** — no wildcard with credentials
- **CSP + HSTS headers** added
- **python-dotenv** in requirements.txt
- **50MB file upload limit** enforced
- **No debug print statements** in AI service
- **AI provider check** is instant (env-var based, no blocking HTTP ping)
- Gemini embeddings provider implemented

---

## ⚠️ REQUIRES YOUR API KEYS TO WORK

Add these to `C:/Users/abhir/Downloads/AKKI_AI/zip-repl/.env`:

```bash
# Required for ALL AI features
GEMINI_API_KEY=your-real-gemini-key-from-aistudio.google.com

# Required for human-quality voice
ELEVENLABS_API_KEY=your-real-elevenlabs-key  (already set)

# Enables web search in CRAG RAG pipeline
TAVILY_API_KEY=your-tavily-key-from-tavily.com

# Enables real Shodan OSINT
SHODAN_API_KEY=your-shodan-key-from-shodan.io

# Enables real GitHub OSINT
GITHUB_TOKEN=your-github-personal-access-token
```

Without GEMINI_API_KEY, the entire AI system falls back to the Free Claude Code proxy (localhost:8082) which must be running separately.

---

## 🔴 REMAINING CRITICAL (high impact, implement next)

### 1. Real STT (Speech-to-Text)
**Current**: `/api/protected/voice/transcribe` returns hardcoded string. Frontend bypasses it using browser SpeechRecognition.
**Fix**: Wire to OpenAI Whisper or ElevenLabs STT API. Browser SpeechRecognition is fine for now since it's actually working.

### 2. Real GitHub OSINT
**Current**: `/api/osint/github` — AI hallucinating repos and emails
**Fix**: PyGithub library + GITHUB_TOKEN env var → real repo/contributor data

### 3. Real Shodan OSINT  
**Current**: `/api/osint/shodan` — AI simulating with RFC 5737 IPs
**Fix**: shodan Python library + SHODAN_API_KEY → real internet exposure data

### 4. Real Code Analysis
**Current**: AI inventing line numbers and CVSSv3 scores
**Fix**: Run `bandit` (Python) or `semgrep` before AI call, feed real output to AI for explanation

### 5. Token refresh endpoint
**Current**: No `/api/auth/refresh`. After 7 days, silent logout.
**Fix**: Add refresh token endpoint, frontend auto-refreshes before expiry

### 6. JWT revocation
**Current**: Tokens irrevocable — stolen token valid for 7 days
**Fix**: Redis-based token blacklist, or short-lived tokens with refresh

### 7. Marketplace CRUD
**Current**: PUT and DELETE marketplace items return HTTP 501
**Fix**: Implement the update/delete handlers in marketplace_service.py

---

## 🟠 HIGH PRIORITY (next sprint)

### Frontend
- [ ] Forgot password flow (requires email/SMTP config)
- [ ] Global search (sessions, documents, findings)
- [ ] Mobile responsive layout
- [ ] Code splitting — routes as `React.lazy()` + `Suspense` 
- [ ] Rreplace hard-coded `window.prompt` in command palette with a proper inline input
- [ ] Tool results injectable into agent chat ("Send to agent" button)
- [ ] Workflow execution streaming (SSE per step)
- [ ] Session rename/delete from sidebar
- [ ] Message pagination (cursor-based instead of limit=100)

### Backend
- [ ] Workflow step-level timeout (asyncio.wait_for)
- [ ] Task queue (arq or celery) for long-running jobs
- [ ] Langfuse observability working in production (key only in root .env)
- [ ] User cache TTL enforcement in auth.py
- [ ] Remove `include_password` footgun from user_to_dict
- [ ] Cursor-based message pagination
- [ ] Test suite (pytest + pytest-asyncio)

---

## 🟡 MEDIUM PRIORITY

- [ ] Email notifications for completed scans/reports
- [ ] Collaboration — share sessions/reports with other users
- [ ] Bandit + Semgrep integration for real code analysis
- [ ] Real phishing campaign tracking (GoPhish integration)
- [ ] VirusTotal API integration for malware analysis
- [ ] Censys/Shodan search within chat via tool routing
- [ ] Rate limit tuning per user tier
- [ ] Error boundaries on all page components
- [ ] Lighthouse performance audit (aim for >90)

---

## Color / Design Tokens (for all future UI)

```
Base:   #04080f       // page background
Panel:  rgba(8,13,26,0.95) // card backgrounds  
Cyan:   #00d8ff / 0,216,255
Green:  #00ff88 / 0,255,136
Purple: #9b59fc / 155,89,252
Red:    #ff3868 / 255,56,104
Amber:  #ffb700 / 255,183,0
```

**Rule**: NEVER use Tailwind opacity classes (`bg-black/20`, `border-white/5`). Always use `style` prop with explicit rgba.

---

## ElevenLabs Setup

1. Get API key: elevenlabs.io → Profile → API Keys
2. Set in `.env`: `ELEVENLABS_API_KEY=sk_your_real_key`
3. Set voice: `ELEVENLABS_DEFAULT_VOICE=pNInz6obpgDQGcFmaJgB` (Adam)
4. Test: Go to `/talk` → click "Test ElevenLabs Voice"

**Voice IDs**: Adam=`pNInz6obpgDQGcFmaJgB` | Rachel=`21m00Tcm4TlvDq8ikWAM` | Josh=`TxGEqnHWrfWFTfGW9XjX`
