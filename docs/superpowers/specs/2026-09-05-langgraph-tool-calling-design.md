# LangGraph Real Tool-Calling Core — Design Spec

Date: 2026-09-05
Status: Draft for user review (thread 3 of the session); no implementation plan yet

## Problem (verified in code, not assumed)

`backend/services/langgraph_agent_service.py` is the live agent path — it's
the only agent module `backend/main.py` imports (`from
backend.services.langgraph_agent_service import process_message`, used by the
chat endpoint and the workflow runner). `backend/services/agent_service.py` is
dead code, imported nowhere.

The live module **imports real LangGraph tool machinery and never wires it
up**:

- It defines `AKKITool` wrappers for all 11 recon tools + knowledge_base +
  sigma, and builds a `ToolNode` inside `create_agent_node()` — then discards
  it. `tool_node` is assigned and never added to the graph.
- `build_agent_graph()` adds one node per agent (`planner`, `defender`,
  `analyst`, …) and a single edge from each straight to `END`. There is **no
  tool node, no conditional edge, and no `bind_tools`/tool-execution step**.
- Each agent node calls `ai_service.chat_completion(...)` exactly once for a
  plain-text answer and returns. `AGENT_TOOL_MAPPING` and `get_tools_for_agent`
  are computed and fed nowhere that can execute a tool.

Net effect: **no agent has ever actually called a tool through the chat
pipeline.** The ReAct loop the vision docs describe ("Reason → Act → Observe →
Repeat") does not exist; it's a single-shot keyword-routed completion with
decorative tool scaffolding around it. This is true of all 7 personas, not
just the exploit one.

Two further real defects:

1. **The checkpointer is in-memory and per-process.** `build_agent_graph()`
   uses `MemorySaver()`, but the app runs `uvicorn --workers 2`. Any state
   that must survive across a request (an interrupt/resume, conversational
   memory keyed by `thread_id`) can be written by one worker and invisible to
   the other, and is lost entirely on restart.
2. **`ai_service.chat_completion` is text-in/text-out** (`-> str`) with no
   function-calling parameter, and fans out across three providers (Free
   Claude Code / Anthropic-compatible, Gemini, Ollama). There is no native
   tool-calling plumbing to lean on.

## Decision: provider-agnostic structured-output ReAct loop

Because the LLM layer must work across all three providers (and Ollama /
small local models have weak or no native function-calling), the tool-calling
loop is built on **structured text output**, not per-provider function-calling
APIs:

- The agent's system prompt is extended with the tool catalogue for that
  agent (name, description, params) and an instruction: to use a tool, reply
  with ONLY a JSON object `{"tool": "<name>", "args": {...}}`; to give a final
  answer, reply with normal prose (or `{"answer": "..."}`).
- A real LangGraph `tool_node` parses that JSON, executes the tool via the
  existing `run_tool()` dispatcher, appends the observation to the message
  state, and loops back to the agent node. A non-JSON (prose) reply, or a
  `{"answer": ...}`, ends the loop.
- A hard cap of **5 tool iterations per turn** prevents runaway loops; on the
  cap the agent is asked to answer from what it has.

This reuses the app's existing `json_mode` support and the existing
`run_tool()` real-tool executor — no new provider integration, works
identically for FCC/Gemini/Ollama.

## Interrupt-based authorization gate (ties into the exploit-tools plan)

The exploit-tools plan adds 6 active (attacking) tools gated by an
authorization attestation on `/api/tools/execute`. For agent-initiated calls,
the graph-native equivalent is a **LangGraph `interrupt_before` on the
tool node when the requested tool is in `ACTIVE_TOOLS`**: the graph pauses,
`process_message` returns a `pending_approval` state (tool + args + a
resume token = the `thread_id`), and a new `POST /api/chat/resume` endpoint
continues the graph only after the user approves. This is why the
checkpointer must be persistent (below) — an interrupt that can't be reliably
resumed across workers/restarts is worse than no interrupt.

Note: the exploit-tools plan's own spec chose UI-only invocation for the 6
active tools (never agent-callable), and its revised Task 5 adds a regression
guard enforcing exactly that. **These two designs must be reconciled before
implementation** — either (a) the 6 active tools stay strictly UI-only and the
agent interrupt gate applies only to a future, separate class of
agent-invokable active tools, or (b) the exploit tools become agent-invokable
*behind the interrupt gate* and the UI-only guard is relaxed. This spec does
not silently pick one; it's the first question for the user (see Open
Questions).

## Persistent checkpointer

Replace `MemorySaver()` with a Postgres-backed checkpointer
(`langgraph-checkpoint-postgres`, the official package) pointed at the app's
existing `DATABASE_URL`. This makes `thread_id`-keyed conversation state and
any interrupt/resume durable across both uvicorn workers and restarts. The
checkpointer's tables are created on startup alongside the app's own
`create_all` (or via the package's setup call).

## Architecture

```
process_message(message, session_id, user_id, ...)
        │
        ▼
  router (existing keyword router, unchanged) → picks agent
        │
        ▼
  agent_node ──emits {"tool":...}──▶ tool_node ──observation──┐
        │                                                     │
        │◀────────────────────────────────────────────────────┘  (loop, max 5)
        │
        └──emits prose / {"answer":...} / hits cap──▶ END
```

- **agent_node**: builds the message list (system prompt + tool catalogue +
  RAG context + prior observations), calls `chat_completion`, and classifies
  the reply as a tool-call or a final answer.
- **tool_node**: parses `{"tool", "args"}`, executes via `run_tool()`,
  appends `{"role":"tool", "content": <result json, truncated>}` to state.
  If the tool is in `ACTIVE_TOOLS`, this is where `interrupt_before` fires
  (pending reconciliation above).
- **conditional edge** from agent_node: `tool_node` if the reply parsed as a
  tool-call and the iteration cap isn't hit, else `END`.
- Existing `AGENT_TOOL_MAPPING` finally becomes load-bearing: it scopes which
  tools each agent's catalogue (and thus tool_node) will accept.

## Files (anticipated — the plan will finalize)

- Modify `backend/services/langgraph_agent_service.py`: real `tool_node`,
  conditional edge, ReAct loop, tool-catalogue prompt injection, iteration
  cap, `interrupt_before` for active tools, persistent checkpointer.
- Modify `backend/requirements.txt`: `langgraph-checkpoint-postgres`.
- Modify `backend/main.py`: new `POST /api/chat/resume` endpoint (note: this
  file carries heavy pre-existing uncommitted user WIP — same
  edit-but-don't-commit handling as the brain-engine plan's Tasks 7-9).
- Tests: ReAct loop (tool-call parsed → tool executed → observation fed back →
  final answer), iteration cap, active-tool interrupt fires, non-active tool
  runs without interrupt, malformed JSON tool-call falls back to treating the
  reply as a final answer (never crashes the graph).

## Error handling

- Malformed `{"tool":...}` JSON → treat the reply as a final prose answer
  (don't crash; don't retry infinitely).
- Unknown tool name / tool not in the agent's `AGENT_TOOL_MAPPING` scope →
  feed an error observation back to the agent, let it recover (counts against
  the iteration cap).
- Tool execution error (already handled by `run_tool`) → observation carries
  the error; agent decides how to proceed.
- Checkpointer/Postgres unreachable at startup → fail fast with a clear log
  (the agent path is core; unlike the brain crawler it shouldn't silently
  degrade).

## Testing strategy

Unit-test the loop with a fake `chat_completion` that returns a scripted
sequence (`{"tool":"dns_lookup","args":{"domain":"x"}}` then a prose answer)
and a patched `run_tool`, asserting: the tool was executed with the parsed
args, the observation was fed back, and the final state carries the prose
answer + a `toolCalls` record. Interrupt behavior tested against a real
Postgres checkpointer (docker-compose `db`) with an active-tool script.

## Out of scope (this iteration)

- No native per-provider function-calling (the structured-output loop is
  deliberately provider-agnostic).
- No change to the keyword router (it still picks the agent; only what
  happens *after* changes).
- No autonomous/background agent operation, texting/calling, or emotional
  state — those are separate vision-doc threads.

## Decisions log

- **2026-09-05 — LLM provider:** The user considered dropping all external
  LLM APIs (motivation for building the brain). After clarifying that the
  brain is non-generative and cannot produce conversational language, the
  user chose to **keep the external LLMs (Gemini / Free Claude Code) for
  now**, with the brain remaining a separate knowledge capability alongside
  them. Going fully local (Ollama) or brain-only is deferred, not chosen.
  This design's provider-agnostic ReAct loop already accommodates the current
  external providers unchanged, so no design change results from this
  decision — but a future "local-only" switch would pin the loop to Ollama
  and is explicitly a later option.

## Open questions for the user (must resolve before a plan is written)

1. **Active-tool reconciliation** (the important one): keep the 6 exploit
   tools strictly UI-only (interrupt gate reserved for a future agent-tool
   class), or make them agent-invokable behind the LangGraph interrupt gate
   and relax the UI-only guard? This changes both this design and the
   exploit-tools plan's Task 5.
2. Should conversation memory across turns (persistent `thread_id` state) be
   turned on now, or just the tool-calling loop + checkpointer plumbing, with
   memory as a follow-up?
3. Iteration cap of 5 — acceptable default, or different?
