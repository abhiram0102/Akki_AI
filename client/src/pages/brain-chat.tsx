import { useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import { parseSSEChunks } from "@/brain3d/useAskStream";

// ── AKKI Brain — chat ─────────────────────────────────────────────────────────
// Ask the brain a natural-language question. The graph reasons over its typed
// CAUSES/REQUIRES/PART_OF edges (shown as "what the graph knows"), and a local
// LLM rephrases ONLY those facts into fluent prose (streamed token by token).
// The grounded chains are always shown beside the prose so it is visible what
// the brain actually knew versus how it was worded.

function authHeaders(): Record<string, string> {
  try {
    const token = localStorage.getItem("auth_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

interface Chain {
  concept: string;
  depth: number;
  chain: string[];
  evidence: number;
  derived: boolean;
}

interface Grounded {
  relation?: string;
  results?: Chain[];
  path?: { chain: string[]; relation?: string };
  profile?: Record<string, Chain[]>;
  answered?: boolean;
}

interface Msg {
  role: "user" | "brain";
  text: string;
  grounded?: Grounded;
  intent?: string;
  topics?: string[];
  llm?: boolean;
  latencyMs?: number;
  loading?: boolean;
}

type StreamEvent =
  | { stage: "reasoning"; intent: string; topics: string[]; answer: Grounded }
  | { stage: "token"; text: string }
  | { stage: "answer"; text: string }
  | { stage: "done"; text?: string; llm?: boolean; latencyMs?: number };

const SUGGESTIONS = [
  "what does deforestation lead to",
  "what does inflation lead to",
  "what is photosynthesis",
  "how are stress and disease connected",
];

function GroundedView({ g }: { g?: Grounded }) {
  if (!g) return null;
  const chains: string[] = [];
  if (g.results) for (const r of g.results) chains.push(r.chain.join(" → "));
  if (g.path?.chain?.length) chains.push(g.path.chain.join(" → "));
  if (g.profile)
    for (const [rel, items] of Object.entries(g.profile))
      for (const r of items) chains.push(`${rel.toLowerCase()}: ${r.chain.join(" → ")}`);
  if (!chains.length) return null;
  return (
    <div className="mt-3 border-l-2 border-emerald-500/40 pl-3">
      <div className="text-[10px] uppercase tracking-widest text-emerald-400/70 mb-1">
        what the graph actually knows
      </div>
      <ul className="space-y-0.5">
        {chains.slice(0, 12).map((c, i) => (
          <li key={i} className="text-xs text-emerald-200/80 font-mono">
            {c}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function BrainChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(q: string) {
    const query = q.trim();
    if (!query || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: query }, { role: "brain", text: "", loading: true }]);
    setBusy(true);

    const patchLast = (fn: (m: Msg) => void) =>
      setMessages((m) => {
        const copy = m.slice();
        const i = copy.length - 1;
        const last = { ...copy[i] };
        fn(last);
        copy[i] = last;
        return copy;
      });

    try {
      const res = await fetch("/api/brain/chat-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ query }),
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const dec = new TextDecoder();
      const parser = parseSSEChunks();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Trusted: our own SSE contract from POST /api/brain/chat-stream.
        for (const raw of parser.push(dec.decode(value, { stream: true }))) {
          const ev = raw as unknown as StreamEvent;
          if (ev.stage === "reasoning") {
            patchLast((m) => {
              m.grounded = ev.answer;
              m.intent = ev.intent;
              m.topics = ev.topics;
              m.loading = true;
            });
          } else if (ev.stage === "token") {
            patchLast((m) => {
              m.text += ev.text;
              m.loading = false;
            });
          } else if (ev.stage === "answer") {
            patchLast((m) => {
              m.text = ev.text;
              m.loading = false;
            });
          } else if (ev.stage === "done") {
            patchLast((m) => {
              if (ev.text) m.text = ev.text;
              m.llm = ev.llm;
              m.latencyMs = ev.latencyMs;
              m.loading = false;
            });
          }
        }
      }
      // Stream closed without a usable answer: never leave the cursor spinning.
      patchLast((m) => {
        if (!m.text) m.text = "The brain didn't return an answer for that.";
        m.loading = false;
      });
    } catch {
      patchLast((m) => {
        m.text = "Could not reach the brain. Check that you are logged in and the backend is running.";
        m.loading = false;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-screen bg-black text-slate-200">
      {/* header */}
      <header className="flex items-center gap-3 px-6 py-4 border-b border-emerald-500/20">
        <span className="text-emerald-400 text-xl">🧠</span>
        <div>
          <h1 className="text-lg font-semibold text-emerald-300">Brain — Chat</h1>
          <p className="text-xs text-slate-500">
            Reasoning over the knowledge graph, worded by a local model — grounded in the graph's own facts.
          </p>
        </div>
        <Link href="/brain" className="ml-auto text-xs text-emerald-400/70 hover:text-emerald-300">
          ← 3D view
        </Link>
      </header>

      {/* messages */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="max-w-2xl mx-auto text-center mt-16">
            <p className="text-slate-400 mb-4">Ask the brain a question. Try:</p>
            <div className="flex flex-wrap gap-2 justify-center">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="px-3 py-1.5 rounded-full border border-emerald-500/30 text-sm text-emerald-200/80 hover:bg-emerald-500/10"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-2xl rounded-2xl px-4 py-3 ${
                m.role === "user"
                  ? "bg-emerald-600/20 border border-emerald-500/30"
                  : "bg-slate-900/70 border border-slate-700/50"
              }`}
            >
              {m.role === "brain" && (
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] uppercase tracking-widest text-emerald-400/70">brain</span>
                  {m.intent && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300/80">
                      {m.intent}
                      {m.topics?.length ? `: ${m.topics.join(", ")}` : ""}
                    </span>
                  )}
                </div>
              )}
              <div className="whitespace-pre-wrap leading-relaxed">
                {m.text}
                {m.loading && <span className="inline-block ml-1 animate-pulse text-emerald-400">▋</span>}
              </div>
              {m.role === "brain" && <GroundedView g={m.grounded} />}
              {m.role === "brain" && m.latencyMs != null && (
                <div className="mt-2 text-[10px] text-slate-500">
                  {m.llm ? "worded by local model" : "graph facts (no model)"} · {Math.round(m.latencyMs)}ms
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* input */}
      <div className="border-t border-emerald-500/20 px-4 py-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(input)}
            placeholder="Ask the brain… (e.g. what does deforestation lead to)"
            disabled={busy}
            className="flex-1 bg-slate-900/70 border border-slate-700/50 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-emerald-500/50 disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={busy || !input.trim()}
            className="px-5 py-3 rounded-xl bg-emerald-600/80 hover:bg-emerald-500 text-white text-sm font-medium disabled:opacity-40"
          >
            {busy ? "…" : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}
