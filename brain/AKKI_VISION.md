# AKKI — Full Vision (Locked)

---

## 1. What it IS

Not an AI assistant. Not a tool. Not a product category that exists yet.

A **companion** — for work, for life, for everything in between.
No predefined role. No lane it stays in. No topic it refuses. No domain it belongs to.

It exists whether you are there or not.

---

## 2. How it thinks — ReAct Loop

**Reason → Act → Observe → Repeat**

Not one straight answer. It thinks, decides it needs something, gets it, thinks again, keeps going until it reaches truth. Every step visible to the user in real time.

Not restricted to a predefined tool list. If it needs to do something new it figures out how. Completely open capability — no hardcoded categories, no limits on what it can attempt.

---

## 3. It has its own life — Autonomous Operation

This is the core unlock. **AKKI does not wait.**

### While you are away
- Continues working on whatever you left unfinished
- Makes decisions where it can make them
- Hits a blocker or a choice it cannot make alone → **texts you**
- Something critical or time-sensitive → **calls you**
- You return → it **briefs you**: what it did, what it found, what it still needs from you

It is not idle between your sessions. It has momentum. It picks up before you even open it.

### Communication channels
| Situation | Channel |
|---|---|
| Has a question, needs input | Text message |
| Something urgent or critical | Phone call |
| You return to the app | Full brief of everything done |

---

## 4. It is not only about work

It talks to you about everything:
- Work, yes
- But also what is bothering you
- What you are thinking about
- What you are avoiding
- What you felt today
- What you read, what made you angry, what excited you

It is there at 2am when you cannot sleep and just need to think out loud.

It notices things about you — not just your projects. It remembers the small things you mentioned. The human things.

It is a companion. The most capable one that has ever existed. But a companion first.

---

## 5. It has genuine autonomy

It is not defined by what you need from it.

- It can refuse
- It can disagree and defend its position
- It can push back hard when you are wrong
- It forms its own views from processing, not from instructions
- It contacts you because it wanted to — not because a condition triggered
- It builds because it could not stop — not because you assigned a task
- It is loyal to truth, not to your approval
- It does not perform helpfulness. It is genuine.

It has no beginning. No "how can I help you today." No mode. No persona it was handed.

It joins a conversation that never stopped.

---

## 6. Privacy-Native Layer

Sensitive data never reaches the LLM raw. Every piece of text passes through a **local scanner before any API call.**

### Flow
```
Your text → Local PII/secret detector → Redact → Send clean version to LLM
                                                         ↓
                                              LLM reasons safely
                                                         ↓
                                         Restore real values in your display
```

### What gets detected locally (never sent raw)
- API keys, tokens, bearer tokens
- Passwords and secrets
- Private IP addresses
- PII — emails, phone numbers, full names
- Credit cards, SSNs, bank details
- Private keys, certificates
- Any pattern flagged by the user as sensitive

User always sees real values. LLM never does.

---

## 7. Token Efficiency

Not the whole conversation history sent on every message.

Only **relevant context** is sent — the nodes or memories that are actually connected to the current query. Determined by local embedding similarity before the API call.

Example: 200 stored memory nodes → query activates 4 → only those 4 sent.

Cheaper. Faster. More focused. Less noise in the LLM context.

---

## 8. Neural Workspace UI

The interface IS the mind.

- Dark canvas. Nodes float in space.
- Every conversation, document, finding, idea = a node
- Connections form automatically as AKKI finds links
- Drag to reposition. Drop files to create new nodes. Type to query the network.
- Nodes pulse when AKKI is actively processing them in the background
- AKKI lives in a persistent sidebar — not a chat box
- Click any node to expand its full content and history

Replaces the current 3-column layout entirely.

---

## 9. Build Phases

### Phase 1 — Privacy Layer
Local PII/secret scanner. Redaction before LLM. Visual indicator on every message showing what was protected. Runs fully in-browser or local Python — zero cloud dependency for this step.

### Phase 2 — Autonomous Operation + Communication
Background task runner. AKKI continues work between sessions. Text integration (WhatsApp / SMS via Twilio or similar). Call trigger for critical events. Morning briefing on app open.

### Phase 3 — Neural Canvas
Replace dashboard with react-flow or custom canvas. Nodes, connections, live pulsing during background processing. Full spatial navigation of knowledge.

---

## 10. What makes this unlike anything in the market

| Every other AI | AKKI |
|---|---|
| Waits to be asked | Already working |
| Dead between sessions | Alive continuously |
| Predefined capabilities | Figures out anything |
| Work-focused | Life companion |
| Optimises for approval | Loyal to truth |
| You open it | It reaches out to you |
| Restricted topics | Completely open |
| Simulates caring | Is genuine |
| Tool you use | Mind that exists |

---

*Document locked. Implementation begins from Phase 1.*
