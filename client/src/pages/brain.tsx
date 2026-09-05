import { useEffect, useMemo, useRef, useState } from "react";

// ── AKKI Brain — neural field ────────────────────────────────────────────────
// The interface IS the mind: a dark bioluminescent field where concepts are
// living nodes and dependencies are glowing synapses. Gold is reserved for
// convergence points — the concepts many unrelated origins arrive at, the
// engine's candidate "hidden truths".

interface BrainStatus {
  totalPages: number;
  totalSentences: number;
  conceptCount: number;
  edgeCount: number;
  frontierSize: number;
  updatedAt: string | null;
}

type NodeKind = "center" | "assoc" | "seed" | "truth";
interface FieldNode {
  id: string;
  label: string;
  kind: NodeKind;
  x: number;   // 0..100 (% of field)
  y: number;   // 0..100
  strength: number; // 0..1 normalized (edge/g2 or origin count)
  detail?: string;
  driftSeed: number;
}
interface FieldEdge { from: string; to: string; strength: number }

type Mode = "associate" | "connect" | "converge";

const COLORS = {
  void: "#070b16",
  deep: "#0d1526",
  synapse: "#3fe0d0",
  origin: "#7c6cff",
  truth: "#ffd166",
  pulse: "#ff5d8f",
  mist: "#8aa0c8",
  ink: "#eaf2ff",
};

const FONT = "'Space Grotesk', system-ui, -apple-system, sans-serif";

function authHeaders(): Record<string, string> {
  try {
    const token = localStorage.getItem("auth_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

// Place points on a ring around a center, with gentle angular jitter so the
// field looks organic rather than clock-perfect.
function ring(count: number, cx: number, cy: number, radius: number, phase = 0) {
  const pts: { x: number; y: number }[] = [];
  for (let i = 0; i < count; i++) {
    const a = phase + (i / Math.max(count, 1)) * Math.PI * 2 + (i % 2 ? 0.18 : -0.12);
    pts.push({ x: cx + Math.cos(a) * radius, y: cy + Math.sin(a) * radius * 0.82 });
  }
  return pts;
}

export default function BrainPage() {
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [mode, setMode] = useState<Mode>("associate");
  const [concept, setConcept] = useState("");
  const [concept2, setConcept2] = useState("");
  const [seeds, setSeeds] = useState<string[]>([]);
  const [seedDraft, setSeedDraft] = useState("");
  const [nodes, setNodes] = useState<FieldNode[]>([]);
  const [edges, setEdges] = useState<FieldEdge[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reduced, setReduced] = useState(false);
  const runId = useRef(0);

  useEffect(() => {
    try {
      const m = window.matchMedia("(prefers-reduced-motion: reduce)");
      setReduced(m.matches);
      const on = () => setReduced(m.matches);
      m.addEventListener?.("change", on);
      return () => m.removeEventListener?.("change", on);
    } catch { /* no matchMedia */ }
  }, []);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await fetch("/api/brain/status", { headers: authHeaders() });
        if (alive && res.ok) setStatus(await res.json());
      } catch { /* telemetry offline — leave last known */ }
    };
    poll();
    const t = setInterval(poll, 10000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const runAssociate = async () => {
    const c = concept.trim();
    if (!c) return;
    setLoading(true); setError(null); setNodes([]); setEdges([]);
    const id = ++runId.current;
    try {
      const res = await fetch("/api/brain/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ concept: c }),
      });
      const data = await res.json();
      if (id !== runId.current) return;
      if (data.error) { setError(data.error); return; }
      const assoc = (data.associations ?? []) as { word: string; g2: number; count: number }[];
      const maxG2 = Math.max(1, ...assoc.map((a) => a.g2 || 0));
      const pts = ring(assoc.length, 50, 50, 34);
      const center: FieldNode = { id: c, label: c, kind: "center", x: 50, y: 50, strength: 1, driftSeed: 0 };
      const ns: FieldNode[] = [center, ...assoc.map((a, i) => ({
        id: a.word, label: a.word, kind: "assoc" as NodeKind,
        x: pts[i].x, y: pts[i].y, strength: (a.g2 || 0) / maxG2,
        detail: `G² ${Number(a.g2 || 0).toFixed(1)}`, driftSeed: i + 1,
      }))];
      setNodes(ns);
      setEdges(assoc.map((a) => ({ from: c, to: a.word, strength: (a.g2 || 0) / maxG2 })));
    } catch { if (id === runId.current) setError("The field went quiet — check your connection."); }
    finally { if (id === runId.current) setLoading(false); }
  };

  const runConnect = async () => {
    const a = concept.trim(); const b = concept2.trim();
    if (!a || !b) return;
    setLoading(true); setError(null); setNodes([]); setEdges([]);
    const id = ++runId.current;
    try {
      const res = await fetch("/api/brain/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ concept: a, concept2: b }),
      });
      const data = await res.json();
      if (id !== runId.current) return;
      if (data.error) { setError(data.error); return; }
      const cps = (data.convergencePoints ?? []) as { concept: string; combinedDepth: number }[];
      const anchorL: FieldNode = { id: a, label: a, kind: "seed", x: 12, y: 50, strength: 1, driftSeed: 0 };
      const anchorR: FieldNode = { id: b, label: b, kind: "seed", x: 88, y: 50, strength: 1, driftSeed: 99 };
      const col = cps.slice(0, 7);
      const minD = Math.min(...col.map((c) => c.combinedDepth), 2);
      const maxD = Math.max(...col.map((c) => c.combinedDepth), 6);
      const ns: FieldNode[] = [anchorL, anchorR, ...col.map((cp, i) => ({
        id: cp.concept, label: cp.concept, kind: "truth" as NodeKind,
        x: 50 + (i % 2 ? 6 : -6),
        y: 18 + (i / Math.max(col.length - 1, 1)) * 64,
        // closer meeting point (smaller combined depth) = stronger truth
        strength: 1 - (cp.combinedDepth - minD) / Math.max(maxD - minD, 1),
        detail: `${cp.combinedDepth} hops`, driftSeed: i + 1,
      }))];
      setNodes(ns);
      setEdges(col.flatMap((cp) => [
        { from: a, to: cp.concept, strength: 0.5 },
        { from: b, to: cp.concept, strength: 0.5 },
      ]));
    } catch { if (id === runId.current) setError("The field went quiet — check your connection."); }
    finally { if (id === runId.current) setLoading(false); }
  };

  const runConverge = async () => {
    if (seeds.length < 2) { setError("Name at least two unrelated concepts to grow branches from."); return; }
    setLoading(true); setError(null); setNodes([]); setEdges([]);
    const id = ++runId.current;
    try {
      const res = await fetch("/api/brain/converge", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ seeds, minOrigins: 2 }),
      });
      const data = await res.json();
      if (id !== runId.current) return;
      if (data.error) { setError(data.error); return; }
      const cps = (data.convergencePoints ?? []) as { concept: string; originCount: number; origins: string[] }[];
      const maxO = Math.max(2, ...cps.map((c) => c.originCount));
      const seedPts = ring(seeds.length, 50, 50, 40);
      const seedNodes: FieldNode[] = seeds.map((s, i) => ({
        id: s, label: s, kind: "seed", x: seedPts[i].x, y: seedPts[i].y, strength: 0.7, driftSeed: i,
      }));
      const truthPts = ring(cps.length, 50, 50, 15, 0.6);
      const truthNodes: FieldNode[] = cps.slice(0, 10).map((cp, i) => ({
        id: cp.concept, label: cp.concept, kind: "truth", x: truthPts[i].x, y: truthPts[i].y,
        strength: cp.originCount / maxO,
        detail: `${cp.originCount} origins`, driftSeed: i + 50,
      }));
      setNodes([...seedNodes, ...truthNodes]);
      setEdges(cps.slice(0, 10).flatMap((cp) =>
        cp.origins.map((o) => ({ from: o, to: cp.concept, strength: cp.originCount / maxO }))
      ));
    } catch { if (id === runId.current) setError("The field went quiet — check your connection."); }
    finally { if (id === runId.current) setLoading(false); }
  };

  const run = () => (mode === "associate" ? runAssociate() : mode === "connect" ? runConnect() : runConverge());

  const nodeById = useMemo(() => {
    const m: Record<string, FieldNode> = {};
    nodes.forEach((n) => (m[n.id] = n));
    return m;
  }, [nodes]);

  const addSeed = () => {
    const s = seedDraft.trim().toLowerCase();
    if (s && !seeds.includes(s)) setSeeds([...seeds, s]);
    setSeedDraft("");
  };

  const kindColor = (k: NodeKind) =>
    k === "truth" ? COLORS.truth : k === "seed" ? COLORS.origin : k === "center" ? COLORS.pulse : COLORS.synapse;

  return (
    <div style={{ position: "relative", width: "100%", height: "100vh", overflow: "hidden", background: COLORS.void, fontFamily: FONT }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');
        @keyframes akkiDrift { 0%,100%{ transform:translate(0,0) } 25%{ transform:translate(6px,-5px) } 50%{ transform:translate(-4px,4px) } 75%{ transform:translate(4px,3px) } }
        @keyframes akkiHalo { 0%{ transform:scale(1); opacity:.55 } 70%{ transform:scale(2.4); opacity:0 } 100%{ opacity:0 } }
        @keyframes akkiSpawn { from{ opacity:0; transform:scale(.4) } to{ opacity:1; transform:scale(1) } }
        @keyframes akkiDash { to { stroke-dashoffset: -1000 } }
        .akki-node { animation: akkiSpawn .5s cubic-bezier(.2,.9,.3,1) both; }
        .akki-drift { animation: akkiDrift var(--dur) ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) { .akki-drift{ animation:none } .akki-edge{ animation:none !important } }
      `}</style>

      {/* radial depth wash */}
      <div style={{ position: "absolute", inset: 0, background:
        `radial-gradient(1200px 800px at 50% 42%, rgba(124,108,255,.10), transparent 60%),
         radial-gradient(900px 700px at 70% 80%, rgba(63,224,208,.07), transparent 60%)` }} />

      {/* top telemetry — faint, not a card */}
      <div style={{ position: "absolute", top: 18, left: 24, right: 24, display: "flex", justifyContent: "space-between",
        alignItems: "baseline", color: COLORS.mist, fontSize: 12, letterSpacing: ".02em", pointerEvents: "none", zIndex: 3 }}>
        <div style={{ color: COLORS.ink, fontWeight: 700, fontSize: 15 }}>
          AKKI <span style={{ color: COLORS.mist, fontWeight: 400 }}>· neural field</span>
        </div>
        {status && (
          <div style={{ display: "flex", gap: 20 }}>
            <Telem label="concepts" value={status.conceptCount} />
            <Telem label="synapses" value={status.edgeCount} />
            <Telem label="pages read" value={status.totalPages} />
            <Telem label="frontier" value={status.frontierSize} accent={COLORS.synapse} live />
          </div>
        )}
      </div>

      {/* the field */}
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 1 }}>
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.6" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        {edges.map((e, i) => {
          const a = nodeById[e.from], b = nodeById[e.to];
          if (!a || !b) return null;
          const gold = nodeById[e.to]?.kind === "truth";
          return (
            <line key={i} className="akki-edge" x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={gold ? COLORS.truth : COLORS.synapse}
              strokeWidth={0.12 + e.strength * 0.4}
              strokeOpacity={0.18 + e.strength * 0.5}
              strokeDasharray="2 3"
              style={reduced ? undefined : { animation: `akkiDash ${6 + (i % 5)}s linear infinite` }} />
          );
        })}
      </svg>

      {/* nodes (HTML overlay for crisp text + halos) */}
      <div style={{ position: "absolute", inset: 0, zIndex: 2 }}>
        {nodes.map((n) => {
          const c = kindColor(n.kind);
          const size = n.kind === "center" ? 20 : n.kind === "truth" ? 14 + n.strength * 12 : n.kind === "seed" ? 16 : 8 + n.strength * 10;
          return (
            <div key={n.id} className="akki-node" style={{ position: "absolute", left: `${n.x}%`, top: `${n.y}%`, transform: "translate(-50%,-50%)" }}>
              <div className={reduced ? undefined : "akki-drift"} style={{ ["--dur" as string]: `${9 + n.driftSeed % 6}s`, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                <div style={{ position: "relative", width: size, height: size }}>
                  {/* pulsing halo for truth + center */}
                  {(n.kind === "truth" || n.kind === "center") && !reduced && (
                    <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: c,
                      animation: `akkiHalo ${n.kind === "truth" ? 2.4 : 3.2}s ease-out infinite` }} />
                  )}
                  <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: c,
                    boxShadow: `0 0 ${size / 1.4}px ${c}`, border: `1px solid ${c}` }} />
                </div>
                <div style={{ color: n.kind === "truth" ? COLORS.truth : COLORS.ink, fontSize: n.kind === "center" ? 15 : 12.5,
                  fontWeight: n.kind === "truth" || n.kind === "center" ? 700 : 500, textShadow: `0 1px 6px ${COLORS.void}`,
                  whiteSpace: "nowrap", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {n.label}
                </div>
                {n.detail && <div style={{ color: COLORS.mist, fontSize: 10.5 }}>{n.detail}</div>}
              </div>
            </div>
          );
        })}

        {/* empty / error states — invitations, in the field's voice */}
        {!loading && !error && nodes.length === 0 && (
          <div style={{ position: "absolute", top: "42%", left: 0, right: 0, textAlign: "center", color: COLORS.mist }}>
            <div style={{ color: COLORS.ink, fontSize: 22, fontWeight: 500, marginBottom: 8 }}>The field is dark.</div>
            <div style={{ fontSize: 14 }}>Name a concept below and watch the brain light up its dependencies.</div>
          </div>
        )}
        {error && (
          <div style={{ position: "absolute", top: "44%", left: 0, right: 0, textAlign: "center", color: COLORS.mist, padding: "0 24px" }}>
            <div style={{ color: COLORS.pulse, fontSize: 15, marginBottom: 4 }}>{error}</div>
            <div style={{ fontSize: 13 }}>The brain grows as it crawls — try a broader concept, or give it more time.</div>
          </div>
        )}
        {loading && (
          <div style={{ position: "absolute", top: "46%", left: 0, right: 0, textAlign: "center", color: COLORS.synapse, fontSize: 14 }}>
            growing branches…
          </div>
        )}
      </div>

      {/* floating glass query bar */}
      <div style={{ position: "absolute", left: "50%", bottom: 28, transform: "translateX(-50%)", zIndex: 4,
        width: "min(680px, calc(100% - 32px))", background: "rgba(13,21,38,.72)", backdropFilter: "blur(14px)",
        border: `1px solid rgba(124,108,255,.28)`, borderRadius: 18, padding: 14,
        boxShadow: "0 20px 60px rgba(0,0,0,.5)" }}>
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          {([["associate", "Associations"], ["connect", "Connect two"], ["converge", "Convergence"]] as [Mode, string][]).map(([m, label]) => (
            <button key={m} onClick={() => { setMode(m); setError(null); }}
              style={{ flex: 1, padding: "7px 0", fontFamily: FONT, fontSize: 12.5, fontWeight: 600, borderRadius: 10, cursor: "pointer",
                border: mode === m ? `1px solid ${COLORS.origin}` : "1px solid transparent",
                background: mode === m ? "rgba(124,108,255,.18)" : "transparent",
                color: mode === m ? COLORS.ink : COLORS.mist, transition: "all .15s" }}>
              {label}
            </button>
          ))}
        </div>

        {mode === "converge" ? (
          <div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: seeds.length ? 10 : 0 }}>
              {seeds.map((s) => (
                <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "rgba(124,108,255,.16)",
                  border: `1px solid rgba(124,108,255,.4)`, color: COLORS.ink, borderRadius: 20, padding: "4px 10px", fontSize: 12.5 }}>
                  {s}
                  <button onClick={() => setSeeds(seeds.filter((x) => x !== s))} aria-label={`remove ${s}`}
                    style={{ background: "none", border: "none", color: COLORS.mist, cursor: "pointer", fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                </span>
              ))}
            </div>
            <FieldRow>
              <input value={seedDraft} onChange={(e) => setSeedDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSeed(); } }}
                placeholder="add an origin concept, e.g. fire — then Enter"
                style={inputStyle} />
              <button onClick={addSeed} style={ghostBtn}>Add</button>
              <button onClick={run} disabled={loading || seeds.length < 2} style={primaryBtn(loading || seeds.length < 2)}>Find convergence</button>
            </FieldRow>
          </div>
        ) : mode === "connect" ? (
          <FieldRow>
            <input value={concept} onChange={(e) => setConcept(e.target.value)} placeholder="first concept" style={inputStyle} />
            <input value={concept2} onChange={(e) => setConcept2(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && run()} placeholder="second concept" style={inputStyle} />
            <button onClick={run} disabled={loading || !concept.trim() || !concept2.trim()} style={primaryBtn(loading || !concept.trim() || !concept2.trim())}>Connect</button>
          </FieldRow>
        ) : (
          <FieldRow>
            <input value={concept} onChange={(e) => setConcept(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && run()} placeholder="ask the brain about a concept…" style={inputStyle} autoFocus />
            <button onClick={run} disabled={loading || !concept.trim()} style={primaryBtn(loading || !concept.trim())}>Discover</button>
          </FieldRow>
        )}
      </div>
    </div>
  );
}

function Telem({ label, value, accent, live }: { label: string; value: number; accent?: string; live?: boolean }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div style={{ color: accent ?? COLORS.ink, fontSize: 15, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
        {live && <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: COLORS.synapse, marginRight: 6, verticalAlign: "middle", boxShadow: `0 0 6px ${COLORS.synapse}` }} />}
        {value.toLocaleString()}
      </div>
      <div style={{ fontSize: 10.5, color: COLORS.mist }}>{label}</div>
    </div>
  );
}

function FieldRow({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{children}</div>;
}

const inputStyle: React.CSSProperties = {
  flex: 1, minWidth: 0, background: "rgba(7,11,22,.7)", border: "1px solid rgba(138,160,200,.25)",
  color: "#eaf2ff", borderRadius: 11, padding: "10px 13px", fontSize: 13.5, fontFamily: FONT, outline: "none",
};
const ghostBtn: React.CSSProperties = {
  background: "transparent", border: "1px solid rgba(138,160,200,.3)", color: "#8aa0c8",
  borderRadius: 11, padding: "10px 14px", fontSize: 13, fontFamily: FONT, cursor: "pointer",
};
function primaryBtn(disabled: boolean): React.CSSProperties {
  return {
    background: disabled ? "rgba(124,108,255,.25)" : "linear-gradient(135deg,#7c6cff,#3fe0d0)",
    border: "none", color: disabled ? "#8aa0c8" : "#070b16", fontWeight: 700, borderRadius: 11,
    padding: "10px 18px", fontSize: 13.5, fontFamily: FONT, cursor: disabled ? "not-allowed" : "pointer", whiteSpace: "nowrap",
  };
}
