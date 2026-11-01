# AKKI AI — Production-Readiness Audit Notes

**Scope:** `backend/` (Python/FastAPI, ~15.8k LOC) + `client/src/` (React/TS, ~24k LOC)
**Date:** 2026-09-05 · **Branch:** `feature/brain-engine`
**Method:** static sweep for bugs, placeholders/stubs, dead/unwanted code, and hygiene issues. Line numbers are anchors at time of audit.

Legend: 🔴 blocker · 🟠 should-fix before prod · 🟡 cleanup / tech-debt

---

## 🔴 Blockers (fix before any production deploy)

### B1. RAG retrieval is NOT scoped per-user — cross-tenant data leak
`backend/services/agent_service.py:224` `_get_rag_context_and_sources(self, query, session_id, top_k=4)`
- Takes **no `user_id`**. Comment at line 240–242 admits it: *"we'll check globally … In a more complete implementation, we'd extract user_id from session context."*
- The embedded-doc check (`:245`) queries `Document.embedded_at.isnot(None)` with **no owner filter**, and the retrieval call (`:257`) invokes `rag_service._retrieve_chunks(query, query_embedding, top_k)` **without `owner_id`**.
- The RAG layer already supports scoping — `rag_service.query(...)` has `user_id` (`rag_service.py:118`) and passes `owner_id=user_id` into `_retrieve_chunks` (`:164`). The agent path simply doesn't use it.
- **Impact:** any user's agent chat can retrieve and surface chunks from **every other user's uploaded documents**. Confidentiality breach.
- **Fix:** thread `user_id` from the request/session down through `run()` (`:432`) → `_get_rag_context_and_sources` → `_retrieve_chunks(..., owner_id=user_id)`, and scope the embedded-doc existence check with the same owner condition.

### B2. Real `JWT_SECRET` committed to the repo
- `.env` is **git-tracked** (`git ls-files` includes `.env`) and contains a live 64-char `JWT_SECRET`.
- Anyone with repo/history access can forge valid auth tokens for the whole platform.
- **Fix:** rotate the secret immediately; `git rm --cached .env`; add `.env` to `.gitignore`; purge from history (`git filter-repo` / BFG); keep only `.env.example` with empty placeholders.

---

## 🟠 Should-fix before production

### S1. TLS verification disabled on HTTP probe
`backend/services/tool_service.py:223` — `httpx.AsyncClient(..., verify=False)`.
- For a recon/scanner tool this *may* be intentional (probing hosts with bad certs), but it silences all cert errors and there's no flag/comment justifying it. At minimum document it; ideally make it opt-in per scan and never reuse this client for anything trust-sensitive.

### S2. Report generation ships empty section content
`client/src/pages/report-builder.tsx:118-124` — sections are sent with `content: ""` and the comment says *"we'll leave it empty and hope the backend can handle it."*
- Backend counterpart (`backend/main.py:1169-1174`) also comments *"Load template sections (implementation would fetch from database) — for now, we'll proceed with the provided sections."*
- Net effect: templated reports render blank sections. The template→data rendering step is unimplemented on both ends.

### S3. Workflow steps saved with empty prompt templates
`client/src/components/workflow-builder/WorkflowEditor.tsx:204` — `prompt_template: "", // TODO: Make this configurable`.
- Every saved workflow step has an empty prompt, so workflows can be created but won't execute meaningfully. Also `:231` — new workflow ID is never captured into URL/state after create (`// TODO`), so an immediate re-save creates a duplicate instead of updating.

### S4. Marketplace rating overwrites instead of aggregating
`backend/services/marketplace_service.py:296-301` — sets `marketplace_item.rating = rating` (last write wins). Comment: *"simplified … a proper implementation would have a separate ratings table."* Displayed rating is meaningless with >1 rater.

### S5. Personalization feedback loop is a no-op
`backend/services/personalization_service.py:363-375` — both the positive-feedback and (strong) negative-feedback branches end in `pass` (*"For now, we keep current preferences"* / *"Could implement avoided topics list"*). The feature computes a `feedback_signal` and then does nothing with it — the learning is not implemented.

### S6. `get_current_user` cache can serve a stale role for up to 10s
`backend/auth.py` `_user_cache` (10s TTL). If a user is demoted/banned, their cached `User` (incl. `role`) is honored for up to 10s. Token revocation is checked first (good), but role/permission changes are not. Acceptable for many apps; call it out for a security platform.

### S7. In-memory token revocation when Redis is down
`backend/auth.py` — if Redis is unreachable, revoked tokens live only in the current process's `_revoked_in_memory` set. In a multi-worker/multi-instance deploy, a logout on worker A does not revoke on worker B, and a restart clears all revocations. Fine for single-process dev; not for prod. Make Redis required in prod config.

---

## 🟡 Dead code / unwanted files / cleanup

### C1. Build artifacts committed — `client/.next/` (155 tracked files)
`git ls-files` tracks 155 files under `client/.next/` (webpack caches, `.pack.gz`, manifests, `.old` files). These are generated, churn constantly, and bloat the repo.
- **Fix:** `git rm -r --cached client/.next` and add `client/.next/` to `.gitignore` (currently only `node_modules`, `dist`, `server/public`, `vite.config.ts.*`, `*.tar.gz`, `.worktrees/` are ignored).

### C2. Stray files tracked at repo root
`tsc_errors.log`, `tsc_errors_full.log`, `tsc_server_errors.log` (compiler dumps) and `zipFile.zip` are committed. Remove and gitignore. `akki_ai.db` (0 bytes) and `test.ts` (root, 112 bytes) also look like leftovers — confirm and delete.

### C3. Legacy `server/` tree fully deleted but referenced
Git status shows the entire old Node `server/` implementation (`server/routes.ts`, `server/services/agents/*`, `server/db.ts`, `drizzle.config.ts`, `scripts/seed.ts`, `replit.md`) deleted on this branch — the Python `backend/` is the replacement. Ensure nothing (Makefile, docker-compose, package.json scripts, README) still points at the removed paths before merging.

### C4. Swallowed exceptions (`except Exception: pass`)
Multiple silent catches hide failures: `backend/auth.py:48,147`, `backend/main.py:57,73,623,1097,2701,2708`, `backend/services/agent_service.py:504`, `ai_service.py:1488`. Several are defensible (best-effort cache/telemetry), but at minimum log at debug level so prod failures aren't invisible. Audit each; the ones around auth (`auth.py:147` merge fallback) and request handling deserve a log line.

### C5. Loose typing / debug leftovers in client
- 47 occurrences of `: any` / `as any` across `client/src` — erodes type safety (spot-check `store/`, `lib/api.ts`).
- 7 `console.log`/`console.debug` calls left in `client/src` — strip or gate behind a debug flag for production builds.

### C6. Minor placeholders (low risk, track only)
- `client/src/components/ui/agent-plan-timeline.tsx:3` — *"Define a basic type for a plan step for now."* (loose local type).
- `backend/main.py:3263` — empty-report path returns `"aiNote": "Quota exceeded — empty report placeholder."` — intentional degraded response, fine but confirm the frontend renders it gracefully.
- `backend/services/agent_service.py:95,111,126` & `langgraph_agent_service.py:387` — "temporarily limited / CACHED MODE" quota-fallback copy. Intentional graceful degradation, not a bug — noted so it isn't mistaken for a stub.

---

## Notes on things that are FINE (so they aren't re-flagged)
- CORS (`backend/main.py:160`) is correctly restricted to explicit localhost origins, not `*`.
- Security headers middleware (`main.py:168+`) sets nosniff/frame/XSS/referrer/permissions — good. **But** CSP includes `'unsafe-inline' 'unsafe-eval'` in `script-src` — relax if the bundler allows (nonce/hash) for a hardened deploy.
- `JWT_SECRET` is required at startup (`auth.py` raises if unset) — good posture; the only problem is that a real one was committed (B2).
- No hardcoded API-key literals found in source; other `.env` keys (Gemini, GitHub, Shodan, ElevenLabs) are empty placeholders.
- `dangerouslySetInnerHTML` (`client/src/components/ui/chart.tsx:81`) is the standard shadcn chart-theme CSS injection — controlled input, not user data. OK.

---

## Suggested priority order
1. **B1** (data leak) and **B2** (secret) — before anything ships.
2. **S1, S6, S7** — security hardening.
3. **S2, S3** — otherwise reports/workflows are non-functional features.
4. **C1, C2, C3** — repo hygiene (quick wins, do in one cleanup commit).
5. **S4, S5, C4, C5, C6** — quality/tech-debt backlog.
