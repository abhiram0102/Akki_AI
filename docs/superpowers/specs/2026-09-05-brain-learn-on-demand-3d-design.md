# AKKI Brain — Learn-on-Demand + Live 3D Holographic Brain

**Date:** 2026-09-05
**Status:** Design (awaiting user review)
**Branch:** feature/brain-engine

## 1. Summary

Turn the Brain Engine from a passive knowledge-graph lookup into an active,
self-teaching reasoning surface. When a user asks about a concept the brain
does not yet know well enough, the backend **learns it live from the web**,
wires the new knowledge into the Neo4j graph, and streams every step back to
the client. The frontend becomes a **live 3D holographic human brain** where
the reasoning path lights up and newly-learned neurons visibly grow in.

This is the first, visible core of the larger "Ultron-like" vision: *ask →
learn live → watch it think in 3D*. It is explicitly a reasoning/knowledge
engine, not an LLM and not RAG — the answer comes from real, traceable graph
connections, deterministic and explainable.

## 2. Goals

- Ask a concept the brain doesn't know → it fetches, extracts, and integrates
  that topic from the web in real time, then answers.
- Stream progress live (SSE) so the user watches the "thinking" and "learning".
- Render a real, anatomically-shaped 3D human brain (neurons on the true
  surface) that fires signals along the answer path and grows new neurons as
  learning streams in.
- Reuse the *exact* graph-write pipeline the background crawler already uses,
  so on-demand learning and background crawling produce identical graph quality.

## 3. Non-Goals (YAGNI — deferred to later phases)

- Autonomous curiosity (self-directed background gap-filling).
- Multiple collaborating agents exchanging graph fragments.
- Voice I/O.
- Any LLM in the answer path.
- Upgrading the app to React 19.

## 4. Architecture Overview

```
User asks ──▶ POST /api/brain/ask (SSE, auth)
                     │
                     ▼
        brain_service.ask()  ── checks graph strength
                     │
          knows enough? ──yes──▶ stream answer immediately
                     │no
                     ▼
        brain_learn.learn_concept(term)   ◀── shared engine
          fetch → extract → apply_to_graph        ▲
                     │                             │
                     ▼                    background crawler
        re-run discover() ──▶ stream answer + subgraph
                                     │
                                     ▼
        Frontend 3D brain: grow new neurons, fire signal path
```

## 5. Backend

### 5.1 New: `backend/services/brain_learn.py` (shared learn engine)

Extract the reusable heart of `brain_crawler.crawl_one_page` (currently lines
~99–191) into a service both the crawler and the on-demand path call:

- `fetch_and_extract(url, source_type, client) -> (sentences, pairs)`
  — the sentence split + `extract_dependencies` loop.
- `apply_to_graph(neo4j_session, word_freq, edge_counts) -> {new_concepts, new_edges}`
  — the exact concept/edge/G² upsert Cypher already in `crawl_one_page`
  (the three batched `session.run` calls). Returns counts of what was added.
- `resolve_wikipedia_title(term, client) -> str | None`
  — resolves an arbitrary user term to the best real article title via the
  MediaWiki search/opensearch API (`action=opensearch`), handling plurals,
  casing, synonyms, and disambiguation. Falls back to naive title-casing only
  if the API is unreachable. **Without this, learn-on-demand silently fails on
  a large fraction of natural inputs.**
- `learn_concept(term, client, neo4j_driver, follow_links=1) -> {term, resolved_title, new_concepts, new_edges, sources}`
  — resolves the term (above), fetches the article via the existing
  `fetch_wikipedia` (already has the browser User-Agent fix), extracts, applies
  to graph, optionally follows the top `follow_links` linked articles for
  depth, returns a summary of what was learned.

`brain_crawler.crawl_one_page` is refactored to call `fetch_and_extract` +
`apply_to_graph` instead of owning that logic. **No duplicated graph code.**

### 5.2 New: `POST /api/brain/ask` (streaming, auth-gated)

- Auth: `Depends(get_current_user)` (same gate as `/discover`).
- Request body: `{ "concept": str }` (new `BrainAskRequest` schema).
- Response: SSE via `sse-starlette`'s `EventSourceResponse` (handles framing,
  periodic keepalive pings, and client-disconnect for us) — preferred over a
  hand-rolled `StreamingResponse`. Headers include `X-Accel-Buffering: no` so
  the frontend proxy flushes events live.
- Async generator logic:
  1. Normalize concept. Emit `{stage:"thinking"}`.
  2. `assoc = _top_associations(concept)`. If `len(assoc) >= LEARN_THRESHOLD`
     (default 3), emit `{stage:"answer", associations, ...}` and `{stage:"done"}`.
  3. Else emit `{stage:"gap", concept}`, then `{stage:"learning", source:"Wikipedia"}`,
     call `learn_concept(...)` (blocking NLP runs via `run_in_threadpool`),
     emit `{stage:"grew", newConcepts, newEdges}`.
  4. Re-run `_top_associations`; also compute **inferred** links (§5.4). Emit
     `{stage:"answer", associations, inferred, path}` (or with `associations:[]`
     + `note:"still thin — crawler will deepen it"` when nothing was learned).
  5. Emit `{stage:"done"}`. `sse-starlette` sends keepalive pings during long
     fetches and stops the generator if the client disconnects.
- SSE payload: one JSON object per event (`data:`), framed by `sse-starlette`.

### 5.4 Inference layer (the reasoning step — what makes it not-RAG)

Retrieving a concept's stored neighbours is still retrieval. The engine must
also **derive** links no single source stated. In `brain_service`:

- `infer_links(concept, limit=5) -> list[{concept, via, strength, derived:true}]`
  — reuse `_reachable_with_depth(concept, max_depth=2)` to find concepts two
  hops away that are **not** direct neighbours of `concept`. For each, record
  the intermediate concept (`via`) and a strength = product/min of the two
  edge G² values along the path. Rank by strength, return the top `limit`.
- The `/ask` answer includes these as a separate `inferred` list, rendered
  distinctly in the UI ("derived — the brain reasoned this, no source said it
  directly"). This is the concrete, honest expression of "it thinks, not just
  looks up," and it costs almost nothing because the traversal already exists.

### 5.5 Config

- `LEARN_THRESHOLD` (int, default 3) — min strong associations to answer
  without learning.
- `LEARN_FOLLOW_LINKS` (int, default 1) — linked articles to follow for depth.
- Both env-overridable; documented in `.env.example`.

## 6. Frontend

### 6.1 3D holographic brain (`client/src/pages/brain.tsx` rewrite)

Replace the flat SVG neural field with a WebGL scene. **React-18-compatible
stack** (the app is on React 18.3.1; r3f v9 needs React 19, so we pin v8):

| Package | Version line | Note |
|---|---|---|
| `three` | `^0.170` | core |
| `@react-three/fiber` | `^8.17` | React 18 compatible |
| `@react-three/drei` | `^9.x` | OrbitControls, Points, MeshSurfaceSampler helpers |
| `@react-three/postprocessing` | `^2.x` | Bloom, ChromaticAberration |
| `postprocessing` | `^6.3x` | peer of the above |

(Exact resolved versions pinned at install; the constraint that fixes the line
is **r3f v8 for React 18.**)

- **Shape (real anatomical):** load a properly-licensed human-brain GLTF/GLB
  and use `MeshSurfaceSampler` to scatter N neuron points across its true
  surface. See §6.3 for model sourcing (gated on user approval).
- **Region-clustered placement:** map each concept to a brain region (stable
  hash of the concept, or a light category heuristic) and bias its neuron
  toward that lobe's surface area, using the region centroids from the
  research. Effect: different questions light up different *areas* of the
  brain, so it reads as a living organ rather than a uniform dust cloud.
- **Neurons:** `THREE.Points` + one `BufferGeometry` + custom additive glow
  `ShaderMaterial` — 50k–100k points in a single draw call. Per-point
  attributes: position, `spawnTime`, size, activation.
- **Signals:** shader-driven pulse along edges using a per-vertex arc-length
  attribute + single `uTime` uniform (all ambient edges in one draw call);
  the active answer path upgraded to `TubeGeometry` with scrolling emissive.
- **Hologram look:** `<Bloom mipmapBlur>` (HDR emissive > 1.0), fresnel rim in
  the material, subtle `<ChromaticAberration>`, optional scanline/noise.
- **Live growth:** on each SSE `grew`/`answer` event, append new points to
  pre-allocated buffers, bump `setDrawRange`, set `needsUpdate`; per-point
  `spawnTime` drives a GPU easeOut/elastic pop-in.
- **Camera/perf:** `<OrbitControls enableDamping autoRotate>`, `dpr={[1,2]}`,
  `<AdaptiveDpr>`, `frameloop="demand"` between queries, dispose all manually
  created GPU objects on unmount.
- **Graceful degradation:** if WebGL is unavailable or `prefers-reduced-motion`
  is set, fall back to a static/low-motion render (no auto-rotate, no signal
  animation); the existing 2D field is kept as the fallback component.

### 6.2 Query modes

Keep the existing three modes (Associations / Connect / Converge) and add a
new default **Ask** mode that drives `/api/brain/ask` via `fetch` +
`ReadableStream` (POST + `Authorization` header, buffered on `\n\n`), rendering
the streamed stages as live status + graph updates. An `AbortController`
cancels the stream on unmount or a new query.

### 6.3 Brain model sourcing (HARD GATE — user approval before download)

The real-anatomy option needs one 3D model file. **Prefer a CC0 model** (no
attribution/share-alike obligation) over CC-BY-SA (Z-Anatomy, BodyParts3D),
which would impose share-alike on the app. Before downloading anything, I will
present the **exact file, source URL, license, and size** and get explicit user
approval (per download-safety rule). The file lives under
`client/public/models/` and is loaded at runtime. Until it is approved, the
frontend renders the procedural-fallback brain so the build is never blocked.

## 7. Data Flow (learn-on-demand, unknown concept)

1. User types "quantum tunneling", Ask mode → POST `/api/brain/ask`.
2. Server: `thinking` → `gap` → `learning` → fetch Wikipedia → extract →
   `apply_to_graph` → `grew {newConcepts:41,newEdges:63}` → re-discover →
   `answer {associations:[…], path:[…]}` → `done`.
3. Client: shows status per stage; on `grew`, spawns 41 neurons that pop into
   the brain; on `answer`, fires a signal pulse along the path to the answer
   nodes, which flare gold.

## 8. Error Handling

- Fetch failure / robots disallow / non-existent Wikipedia page → emit
  `{stage:"answer", associations:[], note:"couldn't learn that one — try a
  broader term"}` then `done` (never hang).
- Neo4j unreachable → `{stage:"error", msg}` + HTTP-level 503 on health.
- Client stream error / abort → close reader, surface a quiet retry message.
- Blocking NLP wrapped in `run_in_threadpool` so the event loop never stalls.

## 9. Testing

- `test_brain_learn.py` — `apply_to_graph` writes concepts/edges/G² correctly
  (against a test Neo4j or a mocked session); `resolve_wikipedia_title` picks
  the right article (search API mocked, incl. plural/disambiguation cases);
  `learn_concept` resolves + returns counts (fetch mocked).
- `test_brain_inference.py` — `infer_links` returns only genuine 2-hop derived
  links (excludes direct neighbours), ranked by combined edge strength.
- `test_crawler_uses_learn_engine.py` — `crawl_one_page` still produces the same
  graph writes after refactor (regression guard).
- `test_brain_ask_endpoint.py` — SSE stream emits the expected stage sequence
  for (a) known concept (no learning) and (b) unknown concept (learns then
  answers); auth gate returns 401 unauthenticated.
- Frontend: a lightweight render/smoke test of the Ask mode SSE parser
  (buffer-across-chunks correctness) and graceful WebGL-absent fallback.

## 10. Build Plan (parallel agents)

- **Agent A (backend):** `brain_learn.py` extraction + crawler refactor +
  `/api/brain/ask` SSE + schema + tests.
- **Agent B (frontend):** 3D brain scene (r3f v8), Ask mode + SSE consumption,
  graceful fallback. Model wiring stubbed until the model file is approved.
- **Integration (me):** wire the model (after download approval), run tests,
  verify end-to-end against the live containers, commit discipline (only the
  feature's own files).

## 11. Risks & Open Items

- **Model download gate:** real-anatomy shape requires an approved model file
  (§6.3). Until approved, Agent B builds against the procedural fallback so it
  is never blocked.
- **React 18 vs r3f:** must pin r3f v8 line; verify the resolved versions
  install cleanly alongside the existing React 18 tree at build time.
- **New dependencies:** adds three/r3f/drei/postprocessing — a real dependency
  change, flagged and intended.
- **Dirty working tree:** the repo has extensive unrelated WIP; every commit
  for this feature must add only this feature's own files.
- **SSE through the frontend nginx/Vite proxy:** confirm `X-Accel-Buffering:no`
  and proxy config flush events live (test through port 80).
```
