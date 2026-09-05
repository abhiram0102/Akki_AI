# Brain Learn-on-Demand + Live 3D Holographic Brain — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Brain Engine learn unknown concepts live from the web (streamed), reason over the graph (inference, not just retrieval), and render it as a live 3D holographic human brain.

**Architecture:** Extract the crawler's graph-write pipeline into a shared `brain_learn` service; add an SSE `/api/brain/ask` endpoint that learns-then-answers with inferred links; rewrite the brain page as a react-three-fiber (v8, React-18-compatible) scene that scatters neurons on a real anatomical mesh (procedural fallback until the model is approved) and animates signals + neuron growth from the SSE stream.

**Tech Stack:** FastAPI, sse-starlette, asyncpg/psycopg, Neo4j (AsyncGraphDatabase), spaCy, React 18, react-three-fiber v8, three r0.170, @react-three/drei v9, @react-three/postprocessing v2.

**Spec:** `docs/superpowers/specs/2026-09-05-brain-learn-on-demand-3d-design.md`

## Global Constraints

- **React stays on 18.3.1** — pin r3f v8 / drei v9 / postprocessing v2. NEVER upgrade React to 19.
- **Commit discipline:** the repo working tree is heavily dirty with unrelated user WIP. Every commit must `git add` ONLY this feature's own explicit file paths — never `git add -A` / `git add .`.
- **No LLM in the answer path.** Answers come from the graph only.
- **Model download is a HARD GATE:** do not download the brain model; the frontend builds against the procedural fallback. Integration wires the real model only after the user approves the exact file/source/license/size.
- **Reuse, don't duplicate:** on-demand learning and the crawler must share the same graph-write code.
- Backend edge noise floor `MIN_EDGE_COUNT = 2` (already in `brain_service`).

---

## File Structure

- Create `backend/services/brain_learn.py` — shared fetch→extract→graph-write engine + Wikipedia title resolution + `learn_concept`.
- Modify `backend/brain_crawler.py` — `crawl_one_page` calls `brain_learn` instead of owning graph-write logic.
- Modify `backend/services/brain_service.py` — add `infer_links`.
- Modify `backend/main.py` — add `POST /api/brain/ask` (SSE).
- Modify `backend/schemas.py` — add `BrainAskRequest`.
- Modify `backend/requirements*.txt` — add `sse-starlette`.
- Modify `client/package.json` — add three/r3f/drei/postprocessing (v8 line).
- Create `client/src/brain3d/` — `BrainScene.tsx`, `NeuronField.tsx`, `Signals.tsx`, `proceduralBrain.ts`, `regions.ts`, `useAskStream.ts`, `shaders.ts`.
- Modify `client/src/pages/brain.tsx` — host the 3D scene + Ask mode; keep 2D field as fallback.
- Create backend tests: `backend/tests/test_brain_learn.py`, `test_brain_inference.py`, `test_brain_ask_endpoint.py`, `test_crawler_uses_learn_engine.py`.

---

## Task 1: `apply_to_graph` — extract the crawler's graph-write core

**Files:**
- Create: `backend/services/brain_learn.py`
- Test: `backend/tests/test_brain_learn.py`

**Interfaces:**
- Consumes: `backend.services.brain_stats_math.log_likelihood_ratio`.
- Produces: `async def apply_to_graph(session, word_freq: Counter, edge_counts: Counter) -> dict` returning `{"new_concepts": int, "new_edges": int}`. `session` is an open Neo4j async session. Contains the exact 3 batched Cypher calls currently in `brain_crawler.crawl_one_page` (concept/Meta upsert, edge upsert, G² writeback).

- [ ] **Step 1: Write the failing test** (mock the Neo4j session; assert the correct Cypher batches are issued and counts returned)

```python
# backend/tests/test_brain_learn.py
from collections import Counter
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.services import brain_learn

class _Result:
    def __init__(self, rows): self._rows = rows
    def __aiter__(self):
        async def gen():
            for r in self._rows: yield r
        return gen()

@pytest.mark.asyncio
async def test_apply_to_graph_upserts_and_returns_counts():
    session = MagicMock()
    # 1st run: concept upsert -> rows with word/frequency/total
    # 2nd run: edge upsert -> rows with cause/effect/count
    # 3rd run: g2 writeback -> no rows needed
    session.run = AsyncMock(side_effect=[
        _Result([{"word": "fire", "frequency": 3, "total": 10},
                 {"word": "heat", "frequency": 2, "total": 10}]),
        _Result([{"cause": "fire", "effect": "heat", "count": 2}]),
        _Result([]),
    ])
    out = await brain_learn.apply_to_graph(session, Counter({"fire": 1, "heat": 1}),
                                           Counter({("fire", "heat"): 1}))
    assert out["new_edges"] == 1
    assert session.run.await_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T backend python -m pytest backend/tests/test_brain_learn.py -q`
Expected: FAIL (`brain_learn` has no `apply_to_graph`).

- [ ] **Step 3: Implement `apply_to_graph`** by moving the graph-write block from `brain_crawler.crawl_one_page` (the `async with neo4j_driver.session()` body, lines ~114–171) into this function, taking an already-open `session`. Return `{"new_concepts": len(word_freq), "new_edges": len(edge_counts)}`. Keep the three batched `session.run` calls and the G² recompute using `log_likelihood_ratio` exactly as they are.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T backend python -m pytest backend/tests/test_brain_learn.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/brain_learn.py backend/tests/test_brain_learn.py
git commit -m "feat(brain): extract apply_to_graph into shared learn engine"
```

---

## Task 2: `resolve_wikipedia_title` + `learn_concept`

**Files:**
- Modify: `backend/services/brain_learn.py`
- Test: `backend/tests/test_brain_learn.py`

**Interfaces:**
- Consumes: `apply_to_graph` (Task 1); `backend.services.brain_fetchers.fetch_wikipedia`; `backend.services.brain_nlp.extract_dependencies`.
- Produces:
  - `async def resolve_wikipedia_title(term: str, client) -> str | None` — calls MediaWiki `https://en.wikipedia.org/w/api.php?action=opensearch&search=<term>&limit=1&format=json`, returns the first result title, or naive `term.strip().title().replace(" ", "_")` fallback on error.
  - `async def learn_concept(term, client, neo4j_driver, follow_links=1) -> dict` returning `{"term", "resolved_title", "new_concepts", "new_edges", "sources"}`.

- [ ] **Step 1: Write failing tests** (mock `client.get` for opensearch; mock `fetch_wikipedia`)

```python
@pytest.mark.asyncio
async def test_resolve_title_uses_opensearch():
    client = MagicMock()
    resp = MagicMock(); resp.json = MagicMock(return_value=["neuron", ["Neuron"], [""], ["url"]])
    resp.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=resp)
    assert await brain_learn.resolve_wikipedia_title("neurons", client) == "Neuron"

@pytest.mark.asyncio
async def test_resolve_title_falls_back_on_error():
    client = MagicMock(); client.get = AsyncMock(side_effect=Exception("net"))
    assert await brain_learn.resolve_wikipedia_title("quantum tunneling", client) == "Quantum_Tunneling"
```

- [ ] **Step 2: Run to verify fail.** Run: `docker compose exec -T backend python -m pytest backend/tests/test_brain_learn.py -q` → FAIL.

- [ ] **Step 3: Implement** `resolve_wikipedia_title` (opensearch call, `resp.json()[1][0]`, fallback) and `learn_concept` (resolve title → build `https://en.wikipedia.org/wiki/<title>` → `fetch_wikipedia(url, client)` → sentence split (≥3 words) → `extract_dependencies` per sentence → build `word_freq`/`edge_counts` Counters → open `neo4j_driver.session()` and call `apply_to_graph` → optionally follow top `follow_links` links repeating fetch+extract+apply → aggregate and return counts + `sources` list of URLs).

- [ ] **Step 4: Run to verify pass.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/brain_learn.py backend/tests/test_brain_learn.py
git commit -m "feat(brain): add Wikipedia title resolution and learn_concept"
```

---

## Task 3: Refactor `crawl_one_page` to use the shared engine

**Files:**
- Modify: `backend/brain_crawler.py:114-171` (replace the inline graph-write block with a call to `brain_learn.apply_to_graph`)
- Test: `backend/tests/test_crawler_uses_learn_engine.py`

**Interfaces:**
- Consumes: `brain_learn.apply_to_graph` (Task 1).

- [ ] **Step 1: Write the failing regression test** — patch `brain_learn.apply_to_graph` and assert `crawl_one_page` calls it with the word/edge Counters derived from a fixture page (mock `fetch_wikipedia`, mock robots `allowed`→True, mock limiter, mock pg_session).

```python
# backend/tests/test_crawler_uses_learn_engine.py — asserts crawl_one_page delegates graph writes
# (mock fetcher returns "Fire causes heat." ; assert apply_to_graph awaited once with a Counter containing ("fire","heat"))
```

- [ ] **Step 2: Run to verify fail** (it still uses the inline block; the patch on `apply_to_graph` isn't hit). Expected: FAIL.

- [ ] **Step 3: Refactor** — in `crawl_one_page`, after building `word_freq`/`edge_counts`, replace the `async with neo4j_driver.session() as session:` write block with:

```python
async with neo4j_driver.session() as session:
    await brain_learn.apply_to_graph(session, word_freq, edge_counts)
```
Add `from backend.services import brain_learn` at top. Delete the moved Cypher.

- [ ] **Step 4: Run tests** — new test PASSES and existing crawler tests still pass: `docker compose exec -T backend python -m pytest backend/tests/ -k crawler -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/brain_crawler.py backend/tests/test_crawler_uses_learn_engine.py
git commit -m "refactor(brain): crawler uses shared apply_to_graph (no dup graph code)"
```

---

## Task 4: `infer_links` — the reasoning step

**Files:**
- Modify: `backend/services/brain_service.py`
- Test: `backend/tests/test_brain_inference.py`

**Interfaces:**
- Consumes: existing `_reachable_with_depth`, `_top_associations`.
- Produces: `async def infer_links(concept: str, limit: int = 5) -> list[dict]` — each `{"concept", "via", "strength", "derived": True}`. A derived link is a concept reachable at depth 2 that is NOT a direct (depth-1) neighbour.

- [ ] **Step 1: Write failing test** — build a tiny in-memory expectation by mocking the two Cypher helpers: direct neighbours of `a` = {b}; 2-hop reachable = {b:1, c:2}; assert `infer_links("a")` returns `c` (via some node) and excludes `b`.

```python
# backend/tests/test_brain_inference.py
import pytest
from unittest.mock import AsyncMock, patch
from backend.services import brain_service

@pytest.mark.asyncio
async def test_infer_links_excludes_direct_neighbours():
    with patch.object(brain_service, "_top_associations", AsyncMock(return_value=[{"word":"b","g2":9,"count":3}])), \
         patch.object(brain_service, "_reachable_with_depth", AsyncMock(return_value={"b":1, "c":2})):
        out = await brain_service.infer_links("a")
    words = [d["concept"] for d in out]
    assert "c" in words and "b" not in words
    assert all(d["derived"] for d in out)
```

- [ ] **Step 2: Run to verify fail.** Expected: FAIL (no `infer_links`).

- [ ] **Step 3: Implement** `infer_links`: get direct neighbour words from `_top_associations(concept)`; get `reached = _reachable_with_depth(concept, max_depth=2)`; candidates = words in `reached` with depth==2 and not in direct set and != concept; strength ordered by `reached` proximity (lower depth first) then alphabetically for stability; attach `via=None` placeholder if intermediate not tracked (acceptable v1) — return top `limit` as dicts with `derived=True`.

- [ ] **Step 4: Run to verify pass.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/brain_service.py backend/tests/test_brain_inference.py
git commit -m "feat(brain): add infer_links reasoning step (2-hop derived links)"
```

---

## Task 5: `POST /api/brain/ask` SSE endpoint

**Files:**
- Modify: `backend/schemas.py` (add `BrainAskRequest`), `backend/main.py`, `backend/requirements.txt` (add `sse-starlette`)
- Test: `backend/tests/test_brain_ask_endpoint.py`

**Interfaces:**
- Consumes: `brain_service._top_associations`, `brain_service.infer_links`, `brain_learn.learn_concept`, `get_current_user`, `get_driver`.
- Produces: SSE stream of JSON events with `stage` in {thinking, gap, learning, grew, answer, done, error}.

- [ ] **Step 1: Add dependency.** Add `sse-starlette` to `backend/requirements.txt`. Rebuild backend image at end of task.

- [ ] **Step 2: Write failing test** — use FastAPI `TestClient`; override `get_current_user`; patch `_top_associations` to return `[]` first then a non-empty list, and patch `learn_concept`. Assert the streamed body contains `"stage": "gap"`, `"stage": "grew"`, and `"stage": "answer"`; and that unauthenticated (no override) returns 401.

```python
# backend/tests/test_brain_ask_endpoint.py
# Known-concept case: _top_associations returns non-empty -> body has "answer" but NOT "learning".
# Unknown case: first call [] then learn_concept patched, second call returns assoc -> body has gap+grew+answer.
```

- [ ] **Step 3: Run to verify fail.** Expected: FAIL (route missing).

- [ ] **Step 4: Implement** `BrainAskRequest {concept: str}` in schemas, and in `main.py`:

```python
from sse_starlette.sse import EventSourceResponse
import json

@app.post("/api/brain/ask")
async def brain_ask(body: BrainAskRequest, current_user: User = Depends(get_current_user)):
    from backend.services import brain_service, brain_learn
    from backend.services.neo4j_service import get_driver
    import httpx
    concept = body.concept.strip().lower()
    LEARN_THRESHOLD = int(os.getenv("LEARN_THRESHOLD", "3"))

    async def gen():
        yield {"data": json.dumps({"stage": "thinking", "concept": concept})}
        assoc = await brain_service._top_associations(concept)
        if len(assoc) < LEARN_THRESHOLD:
            yield {"data": json.dumps({"stage": "gap", "concept": concept})}
            yield {"data": json.dumps({"stage": "learning", "source": "Wikipedia"})}
            async with httpx.AsyncClient(timeout=30, headers=brain_learn.UA_HEADERS) as client:
                learned = await brain_learn.learn_concept(concept, client, get_driver())
            yield {"data": json.dumps({"stage": "grew", **{k: learned[k] for k in ("new_concepts","new_edges")}})}
            assoc = await brain_service._top_associations(concept)
        inferred = await brain_service.infer_links(concept)
        yield {"data": json.dumps({"stage": "answer", "concept": concept,
                                   "associations": assoc, "inferred": inferred})}
        yield {"data": json.dumps({"stage": "done"})}

    return EventSourceResponse(gen(), headers={"X-Accel-Buffering": "no"})
```
(Export `UA_HEADERS` from `brain_learn`; wrap the blocking spaCy work inside `learn_concept` with `run_in_threadpool`.)

- [ ] **Step 5: Rebuild + run tests.**

```bash
docker compose build backend && docker compose up -d backend
docker compose exec -T backend python -m pytest backend/tests/test_brain_ask_endpoint.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/schemas.py backend/main.py backend/requirements.txt backend/tests/test_brain_ask_endpoint.py
git commit -m "feat(brain): add streaming /api/brain/ask (learn-on-demand + inference)"
```

---

## Task 6: Frontend — install React-18-compatible 3D stack

**Files:**
- Modify: `client/package.json`

**Interfaces:** Produces the `three`, `@react-three/fiber`, `@react-three/drei`, `@react-three/postprocessing`, `postprocessing` modules for later tasks.

- [ ] **Step 1: Add deps** (exact v8 line for React 18):

```bash
cd client && pnpm add three@^0.170.0 @react-three/fiber@^8.17.10 @react-three/drei@^9.114.0 @react-three/postprocessing@^2.16.0 postprocessing@^6.36.0 && pnpm add -D @types/three
```

- [ ] **Step 2: Verify install resolves against React 18** — `pnpm ls react @react-three/fiber` shows react 18.x and fiber 8.x, no peer errors that block build. Run `pnpm build` (or `pnpm tsc --noEmit`) to confirm the tree compiles.

- [ ] **Step 3: Commit**

```bash
git add client/package.json client/pnpm-lock.yaml
git commit -m "build(brain): add react-three-fiber v8 stack (React 18 compatible)"
```

---

## Task 7: Procedural brain + neuron field (the fallback that always works)

**Files:**
- Create: `client/src/brain3d/proceduralBrain.ts`, `client/src/brain3d/regions.ts`, `client/src/brain3d/shaders.ts`, `client/src/brain3d/NeuronField.tsx`

**Interfaces:**
- Produces: `generateBrainPoints(count: number): Float32Array` (procedural two-hemisphere + cerebellum cloud per spec §6.1 / research Part 1.3); `REGIONS` map of region→centroid `[x,y,z]`; `<NeuronField points activations spawnTimes />` rendering `THREE.Points` with the additive glow ShaderMaterial (vertex sets `gl_PointSize` w/ spawn ease + distance LOD; fragment draws soft radial glow, additive blend, `depthWrite:false`).

- [ ] **Step 1:** Implement `proceduralBrain.ts` using the research recipe: sample sphere directions → ellipsoid radii `(0.42,0.55,0.75)` → hemisphere offset ±`rx*0.55` → medial-wall flatten → 3-octave simplex-noise normal displacement (folds) → denser cerebellum blob at `(0,-0.6,-0.7)` → stem capsule. Return interleaved xyz Float32Array. (Use a small inlined simplex/`Math.sin`-hash noise — no new dep.)

- [ ] **Step 2:** Implement `regions.ts` with the centroids table from research (frontal/parietal/temporal/occipital/cerebellum/stem, hemisphere-signed) and `regionForConcept(word): keyof REGIONS` = stable hash of the word mod region list.

- [ ] **Step 3:** Implement `shaders.ts` (vertex+fragment GLSL strings) and `NeuronField.tsx` (builds BufferGeometry with `position`, `aSpawnTime`, `aSize`, `aActivation` attributes, pre-allocated to a max count with `setDrawRange`; single `ShaderMaterial` with `uTime` uniform advanced in `useFrame`).

- [ ] **Step 4: Smoke-verify** — a temporary `<Canvas><NeuronField points={generateBrainPoints(20000)} /></Canvas>` renders a brain-shaped cloud (visual check at `/brain`).

- [ ] **Step 5: Commit**

```bash
git add client/src/brain3d/proceduralBrain.ts client/src/brain3d/regions.ts client/src/brain3d/shaders.ts client/src/brain3d/NeuronField.tsx
git commit -m "feat(brain): procedural brain point cloud + neuron glow field"
```

---

## Task 8: Signals + grow-in + holographic post-processing

**Files:**
- Create: `client/src/brain3d/Signals.tsx`, `client/src/brain3d/BrainScene.tsx`

**Interfaces:**
- Consumes: `NeuronField`, `regions`.
- Produces: `<Signals edges activePath />` (shader flow pulse along `Line2` edges via arc-length attribute + `uTime`; active path upgraded to emissive tube); `<BrainScene graph stream />` assembling Canvas + OrbitControls(autoRotate,damping) + `<EffectComposer><Bloom mipmapBlur/><ChromaticAberration/></EffectComposer>` + `AdaptiveDpr`, `dpr={[1,2]}`, `frameloop="demand"`.

- [ ] **Step 1:** Implement `Signals.tsx` — build line geometry from graph edges; per-vertex `aArc` (0..1); fragment brightness = gaussian pulse at `fract(uTime*speed - offset)`, additive. Active answer-path edges get `uActive` + tube upgrade.
- [ ] **Step 2:** Implement grow-in: when new nodes arrive, append to `NeuronField` buffers and set their `aSpawnTime = clock`; the shader eases size+opacity from 0.
- [ ] **Step 3:** Implement `BrainScene.tsx` with postprocessing + camera + reduced-motion guard (disable autoRotate + signal animation when `prefers-reduced-motion`).
- [ ] **Step 4: Visual verify** at `/brain` — neurons glow, edges pulse, bloom reads as hologram.
- [ ] **Step 5: Commit**

```bash
git add client/src/brain3d/Signals.tsx client/src/brain3d/BrainScene.tsx
git commit -m "feat(brain): signal flow, neuron grow-in, holographic post-processing"
```

---

## Task 9: Ask-mode SSE client hook + wire into the page

**Files:**
- Create: `client/src/brain3d/useAskStream.ts`
- Modify: `client/src/pages/brain.tsx`

**Interfaces:**
- Produces: `useAskStream()` → `{ ask(concept), stage, answer, learnedNodes, aborting }` using `fetch` + `ReadableStream` (POST `/api/brain/ask`, `Authorization` header, buffer on `\n\n`, `AbortController`).

- [ ] **Step 1: Write failing test** for the SSE parser's buffer-across-chunks correctness (pure function `parseSSEChunks`):

```ts
// feed "data: {\"stage\":\"grew\"}\n\ndata: {\"sta" then "ge\":\"done\"}\n\n"
// expect two events: grew, done
```

- [ ] **Step 2: Run to verify fail** (`pnpm test` / vitest). Expected: FAIL.
- [ ] **Step 3: Implement** `parseSSEChunks` + `useAskStream` (on each `answer`/`grew` event, push nodes to scene state; on unmount/new query, `abort()`).
- [ ] **Step 4: Wire** into `brain.tsx`: add an **Ask** mode (default) whose submit calls `ask(concept)`; render `<BrainScene>` with the live graph; keep the existing 3 modes calling their existing endpoints; keep the 2D field component as a `<BrainFieldFallback>` used when WebGL is unavailable.
- [ ] **Step 5: Run test to verify pass** + manual: ask a known and an unknown concept at `http://localhost/brain`, watch stages + neuron growth.
- [ ] **Step 6: Commit**

```bash
git add client/src/brain3d/useAskStream.ts client/src/pages/brain.tsx client/src/brain3d/*.test.ts
git commit -m "feat(brain): Ask mode with live SSE stream wired into 3D scene"
```

---

## Task 10: Graceful WebGL fallback + reduced-motion

**Files:**
- Modify: `client/src/pages/brain.tsx`

- [ ] **Step 1:** Detect WebGL support (`document.createElement('canvas').getContext('webgl2')`); if absent, render the existing 2D neural field (`BrainFieldFallback`) with the same query bar so the page still works.
- [ ] **Step 2:** Confirm `prefers-reduced-motion` disables autoRotate + signal/grow animations (nodes still appear, just static).
- [ ] **Step 3: Manual verify** in a WebGL-disabled context → 2D fallback renders and answers.
- [ ] **Step 4: Commit**

```bash
git add client/src/pages/brain.tsx
git commit -m "feat(brain): graceful WebGL + reduced-motion fallback"
```

---

## Task 11: Real anatomical model integration (GATED — after user approval)

**Files:**
- Create: `client/public/models/brain.glb` (only after approval), `client/src/brain3d/loadBrainMesh.ts`
- Modify: `client/src/brain3d/BrainScene.tsx`

- [ ] **Step 1: (INTEGRATOR, not a subagent)** present the exact model file, source URL, license (prefer CC0), and size to the user; get explicit approval; then download to `client/public/models/`.
- [ ] **Step 2:** Implement `loadBrainMesh.ts` — load the GLB via drei `useGLTF`, `MeshSurfaceSampler` to scatter N neuron positions on the real surface; replace `generateBrainPoints` output when the mesh is present, else keep procedural.
- [ ] **Step 3: Verify** the brain now matches real anatomy; procedural fallback still used if the model fails to load.
- [ ] **Step 4: Commit** (include model + attribution note if license requires):

```bash
git add client/public/models/brain.glb client/src/brain3d/loadBrainMesh.ts client/src/brain3d/BrainScene.tsx
git commit -m "feat(brain): scatter neurons on real anatomical mesh"
```

---

## Task 12: End-to-end verification (INTEGRATOR)

- [ ] **Step 1:** `docker compose exec -T backend python -m pytest backend/tests/ -q` — all brain tests pass.
- [ ] **Step 2:** Through `http://localhost/brain`: ask a KNOWN concept (`neuron`) → answers instantly, no learning stage. Ask an UNKNOWN concept → gap → learning → grew (neurons pop in) → answer with `inferred` links shown distinctly.
- [ ] **Step 3:** Verify graph grew (`MATCH (c:Concept) RETURN count(c)` before/after) and no orphan explosion.
- [ ] **Step 4:** Confirm SSE flushes live through the port-80 proxy (events arrive incrementally, not all at once).
- [ ] **Step 5:** Update the hive `memory.md` with the shipped result.

---

## Self-Review

**Spec coverage:** §5.1 apply_to_graph→T1, resolve_title/learn_concept→T2, crawler reuse→T3; §5.2 /ask SSE→T5; §5.4 infer_links→T4; §5.5 config (LEARN_THRESHOLD)→T5; §6.1 procedural+neurons+regions→T7, signals/grow/postfx→T8; §6.2 Ask mode+modes→T9; §6.3 real model gate→T11; §6.4 fallback→T10; §9 tests→T1,2,3,4,5,9; §7 data flow + §11 SSE-through-proxy→T12. All covered.

**Placeholder scan:** `via=None` in T4 is an explicit, documented v1 simplification (not a TODO). 3D shader/procedural bodies are described by concrete recipe + attributes rather than full GLSL — acceptable given the spec + research report travel with the plan; each has a visual verification step.

**Type consistency:** `apply_to_graph(session, word_freq, edge_counts)->{new_concepts,new_edges}` used consistently T1/T3/T5. `learn_concept(...)->{new_concepts,new_edges,...}` consumed in T5. `infer_links(concept,limit)->[{concept,via,strength,derived}]` consumed in T5. Ask stages consistent T5/T9.
