import { useCallback, useEffect, useRef, useState } from "react";

// ── Ask-mode SSE client ──────────────────────────────────────────────────────
// Drives `POST /api/brain/ask`, which streams Server-Sent Events in the wire
// format `sse_starlette.EventSourceResponse` emits: `data: <json>\n\n` per
// event, no `event:` field. The exact stage payloads, in order, are:
//
//   1. {stage:"thinking", concept, plan:{intent, topics, wh}}
//   2. {stage:"gap", concept}                         — only if unknown concept
//   3. {stage:"learning", source}                      — only if gap
//   4. {stage:"grew", new_concepts, new_edges}          — only if gap, learn succeeded
//   5. {stage:"answer", concept, associations:[], inferred:[], note, answer:{...}}
//      — either the normal-path answer (`answer` present), or (if gap + learn
//      failed) an empty answer carrying a "couldn't learn that one" note and
//      NO `answer` object, followed immediately by done
//   6. {stage:"curious", concepts:[], queued}              — OPTIONAL, only if
//      the answer left something worth reading (own 2-hop guesses first, so
//      the brain checks its own inferences rather than just confirming them)
//   7. {stage:"done"}
//
// So a client sees one of three shapes: thinking→answer→[curious]→done (known
// concept), thinking→gap→learning→grew→answer→[curious]→done (learned
// successfully), or thinking→gap→learning→answer(empty+note)→done (learn
// failed, no `curious`). `curious` is always optional and always after
// `answer` — treat "answer landed" (stage `answer` or later) as the moment to
// render the summary, not stage === "answer" alone, or a `curious` event
// after a good answer will blank it back out.
//
// `plan` (on "thinking") is `backend/services/brain_query.py`'s parsed
// QueryPlan — the question run through spaCy (no LLM) and resolved to an
// intent (DEFINE/CAUSE/EFFECT/RELATE/EXPLORE) plus the topics it names.
// `answer` (on "answer", when the query succeeded) is
// `backend/services/brain_answer.py`'s composed Function-7 answer:
// `dependsOn`/`produces`/`convergences`/`derived` (the same kind of evidence
// as `associations`/`inferred`, just oriented per the intent — e.g. `dependsOn`
// reads the graph's in-edges, something nothing read before this), a
// deterministically templated `summary` sentence, an unprompted `observation`,
// an honest `gap`, a `confidence` score, which `sense` of the concept the
// answer settled on (null when it only has one known meaning — backend/
// services/brain_meaning.py's embedding+clustering "meaning layer"),
// whether that sense actually narrowed the evidence (`senseFiltered` --
// can be false with a `sense` present, since the graph is still
// single-sense today), and `provenance` (source URLs actually read).
// Every clause in it is composed
// from real graph edges —
// nothing in the answer path is LLM-generated. `associations` and `inferred`
// are unchanged and still come first in the payload, so any consumer that
// ignores `plan`/`answer` behaves exactly as before.
//
// `curious` (Function 8 — the loop closing) is `backend/services/
// brain_curiosity.py` queuing what the answer was least able to stand behind
// onto the crawl frontier: `concepts` is what it picked (ranked by weakness,
// capped at 3), `queued` how many actually got queued. This is the brain
// deciding to go read more on its own, not a request the UI made — a good
// moment to show "still exploring: X" rather than treat it as an error stage.
//
// Design choices (documented per the task brief's latitude grant):
//
//  - `learnedNodes` carries the `grew` event's counts (`newConcepts`/
//    `newEdges`), NOT synthesized graph nodes. The backend's `grew` payload
//    only ever reports counts — it does not name the newly-learned concepts
//    — so there is nothing for this generic, DOM/3D-agnostic hook to turn
//    into real `{id, label}` nodes. The consumer (`brain.tsx`) is expected to
//    use these counts to spawn anonymous "growth" placeholder neurons (a
//    visual "the brain is growing" cue), and separately use the `answer`
//    event's `associations`/`inferred` (which DO carry real concept names)
//    to append real, named nodes and flare the answer path gold. Keeping
//    that translation in `brain.tsx` (rather than here) keeps this hook free
//    of any `BrainScene`/Three.js coupling, so it stays trivially unit
//    testable in plain Node (see `useAskStream.test.ts`).
//  - `stage` is a plain string enum, not an object carrying per-stage
//    payload data (e.g. no `concept` on the "thinking" stage) — the queried
//    concept is already known to the caller (it's what was passed to
//    `ask()`), and every other per-stage detail the UI plausibly wants is
//    already exposed via `answer` (concept/associations/inferred/note) or
//    `learnedNodes` (counts). This keeps the returned shape close to the
//    brief's own sketch (`{ask, stage, answer, learnedNodes, aborting}`)
//    rather than inventing a richer, harder-to-consume shape.
//  - `aborting` is best-effort UI signal, true from the moment a newer
//    `ask()` call (or unmount) cancels an in-flight stream until that
//    specific stream's own cleanup has run. In practice, because `ask()`
//    resets `stage`/`answer`/`learnedNodes` synchronously for the *new*
//    query before the old stream's abort is even observed, a stale event
//    from the old stream can never overwrite the new query's state — but
//    exposing `aborting` still lets a caller suppress a mid-transition flash
//    (e.g. skip animating in a "couldn't learn" note that's about to be
//    replaced) if it wants to.

/** Reuses the exact auth pattern already established in client/src/pages/brain.tsx. */
function authHeaders(): Record<string, string> {
  try {
    const token = localStorage.getItem("auth_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

/** One parsed SSE `data:` JSON payload. Shape is stage-dependent — see file header. */
export type SSEEvent = Record<string, unknown>;

export interface SSEChunkParser {
  /** Feed one chunk of raw response text; returns any newly-completed events. */
  push(chunk: string): SSEEvent[];
}

/**
 * Creates a stateful parser for `data: <json>\n\n`-delimited SSE text.
 * Buffers partial input across `push()` calls so a chunk boundary landing
 * mid-JSON (or mid-`\n\n` separator) never drops or corrupts an event.
 * Malformed `data:` lines are skipped rather than thrown, so one bad line
 * can't kill the whole stream.
 */
export function parseSSEChunks(): SSEChunkParser {
  let buffer = "";
  return {
    push(chunk: string): SSEEvent[] {
      buffer += chunk;
      const events: SSEEvent[] = [];
      let sepIndex: number;
      // A complete event is terminated by a blank line ("\n\n"). Consume
      // every complete block found so far; whatever's left (no trailing
      // "\n\n" yet) stays buffered for the next push().
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        for (const line of block.split("\n")) {
          if (!line.startsWith("data:")) continue;
          const jsonText = line.slice("data:".length).trim();
          if (!jsonText) continue;
          try {
            events.push(JSON.parse(jsonText) as SSEEvent);
          } catch {
            // Ignore a malformed line rather than throwing.
          }
        }
      }
      return events;
    },
  };
}

export type AskStage =
  | "idle"
  | "thinking"
  | "gap"
  | "learning"
  | "grew"
  | "answer"
  | "curious"
  | "done"
  | "error";

export interface AskAssociation {
  word: string;
  g2: number;
  count: number;
}

export interface AskInferred {
  concept: string;
  via: string | null;
  strength: number;
  derived: true;
}

/** The question, understood — `backend/services/brain_query.py`'s QueryPlan. */
export interface AskPlan {
  intent: string;
  topics: string[];
  wh: string | null;
}

/** One convergence point (where otherwise-unrelated topics meet). */
export interface AskConvergence {
  concept: string;
  [key: string]: unknown;
}

/**
 * `backend/services/brain_answer.py`'s composed Function-7 answer — see the
 * file header for what each field means. Absent from `AskAnswer` only on the
 * "couldn't learn that one" empty-answer path (there's nothing to compose).
 */
export interface AskComposedAnswer {
  intent: string;
  topics: string[];
  wh: string | null;
  dependsOn: AskAssociation[];
  produces: AskAssociation[];
  convergences: AskConvergence[];
  derived: AskInferred[];
  summary: string;
  observation: string | null;
  gap: string | null;
  confidence: number;
  /**
   * Which meaning of the concept this answer is about, or null when the
   * concept has only one known sense. `label` names the sense (e.g. "heat,
   * fuel, combustion" vs "passion, desire"); `example` is one real sentence
   * it was drawn from. `observation` already says this in words when present
   * -- worth rendering distinctly anyway, since a confident answer about the
   * wrong sense of a word is the most misleading thing this brain can do.
   */
  sense: { sense: number; label: string[]; contextCount: number; example: string } | null;
  /**
   * Whether the evidence above was actually narrowed to `sense` (the graph
   * itself is still single-sense today, so this can be false even with a
   * `sense` present -- that's a real, expected state, not a bug: it means
   * the brain knows which meaning was asked about but couldn't yet narrow
   * the evidence to just that meaning). True is a stronger claim than a
   * label alone, worth distinguishing in the UI.
   */
  senseFiltered: boolean;
  provenance: string[];
}

export interface AskAnswer {
  concept: string;
  associations: AskAssociation[];
  inferred: AskInferred[];
  note?: string;
  answer?: AskComposedAnswer;
}

/** Counts from a `grew` event — see the "learnedNodes" design note above. */
export interface AskGrew {
  newConcepts: number;
  newEdges: number;
}

/** A `curious` event — the brain queuing its own weakest spots for later reading. */
export interface AskCuriosity {
  concepts: string[];
  queued: number;
}

export interface UseAskStreamResult {
  ask(concept: string): void;
  stage: AskStage;
  plan: AskPlan | null;
  answer: AskAnswer | null;
  learnedNodes: AskGrew | null;
  curiosity: AskCuriosity | null;
  aborting: boolean;
}

export function useAskStream(): UseAskStreamResult {
  const [stage, setStage] = useState<AskStage>("idle");
  const [plan, setPlan] = useState<AskPlan | null>(null);
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [learnedNodes, setLearnedNodes] = useState<AskGrew | null>(null);
  const [curiosity, setCuriosity] = useState<AskCuriosity | null>(null);
  const [aborting, setAborting] = useState(false);

  const controllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const pendingAbortsRef = useRef(0);

  const markAbortStart = useCallback(() => {
    pendingAbortsRef.current += 1;
    if (isMountedRef.current) setAborting(true);
  }, []);

  const markAbortSettled = useCallback(() => {
    pendingAbortsRef.current = Math.max(0, pendingAbortsRef.current - 1);
    if (isMountedRef.current) setAborting(pendingAbortsRef.current > 0);
  }, []);

  /** Aborts whatever request is currently in flight, if any. */
  const abortInFlight = useCallback(() => {
    const prev = controllerRef.current;
    if (!prev) return;
    controllerRef.current = null;
    markAbortStart();
    prev.abort();
  }, [markAbortStart]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortInFlight();
    };
  }, [abortInFlight]);

  const ask = useCallback(
    (rawConcept: string) => {
      const concept = rawConcept.trim();
      if (!concept) return;

      // Cancel any previous in-flight stream before starting a new one.
      abortInFlight();

      const controller = new AbortController();
      controllerRef.current = controller;

      setStage("thinking");
      setPlan(null);
      setAnswer(null);
      setLearnedNodes(null);
      setCuriosity(null);

      (async () => {
        let ownAbortSeen = false;
        try {
          const res = await fetch("/api/brain/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ concept }),
            signal: controller.signal,
          });

          if (!res.ok || !res.body) {
            if (!controller.signal.aborted && isMountedRef.current) setStage("error");
            return;
          }

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          const parser = parseSSEChunks();

          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            const events = parser.push(decoder.decode(value, { stream: true }));
            for (const evt of events) {
              if (controllerRef.current !== controller || !isMountedRef.current) continue;
              applyEvent(evt, concept);
            }
          }
        } catch {
          if (controller.signal.aborted) {
            ownAbortSeen = true;
          } else if (isMountedRef.current) {
            setStage("error");
          }
        } finally {
          if (ownAbortSeen) {
            markAbortSettled();
          } else if (controllerRef.current === controller) {
            // This request finished on its own (not superseded/aborted) —
            // release the slot so a later ask() doesn't try to abort a
            // dead controller.
            controllerRef.current = null;
          }
        }
      })();

      function applyEvent(evt: SSEEvent, queriedConcept: string) {
        const s = evt.stage;
        if (s === "thinking" || s === "gap" || s === "learning") {
          setStage(s);
          if (s === "thinking" && evt.plan && typeof evt.plan === "object") {
            setPlan(evt.plan as AskPlan);
          }
        } else if (s === "grew") {
          setStage("grew");
          setLearnedNodes({
            newConcepts: Number(evt.new_concepts ?? 0),
            newEdges: Number(evt.new_edges ?? 0),
          });
        } else if (s === "answer") {
          setStage("answer");
          setAnswer({
            concept: typeof evt.concept === "string" ? evt.concept : queriedConcept,
            associations: Array.isArray(evt.associations) ? (evt.associations as AskAssociation[]) : [],
            inferred: Array.isArray(evt.inferred) ? (evt.inferred as AskInferred[]) : [],
            note: typeof evt.note === "string" ? evt.note : undefined,
            answer: evt.answer && typeof evt.answer === "object" ? (evt.answer as AskComposedAnswer) : undefined,
          });
        } else if (s === "curious") {
          setStage("curious");
          setCuriosity({
            concepts: Array.isArray(evt.concepts) ? (evt.concepts as string[]) : [],
            queued: Number(evt.queued ?? 0),
          });
        } else if (s === "done") {
          setStage("done");
        } else if (s === "error") {
          setStage("error");
        }
      }
    },
    [abortInFlight, markAbortSettled]
  );

  return { ask, stage, plan, answer, learnedNodes, curiosity, aborting };
}
