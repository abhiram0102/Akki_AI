import { useEffect, useState } from "react";

interface BrainStatus {
  totalPages: number;
  totalSentences: number;
  conceptCount: number;
  edgeCount: number;
  frontierSize: number;
  updatedAt: string | null;
}

interface Association {
  word: string;
  g2: number;
  count: number;
}

interface ConvergencePoint {
  concept: string;
  depthFrom1: number;
  depthFrom2: number;
  combinedDepth: number;
}

export default function BrainPage() {
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [concept, setConcept] = useState("");
  const [concept2, setConcept2] = useState("");
  const [associations, setAssociations] = useState<Association[] | null>(null);
  const [convergencePoints, setConvergencePoints] = useState<ConvergencePoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const authHeaders = (): Record<string, string> => {
    const token = localStorage.getItem("auth_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch("/api/brain/status", { headers: authHeaders() });
        if (res.ok) setStatus(await res.json());
      } catch {
        // status polling failure is non-fatal — just skip this tick
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const runDiscover = async () => {
    if (!concept.trim()) return;
    setLoading(true);
    setError(null);
    setAssociations(null);
    setConvergencePoints(null);
    try {
      const res = await fetch("/api/brain/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          concept: concept.trim(),
          concept2: concept2.trim() || null,
        }),
      });
      const data = await res.json();
      if (data.error) setError(data.error);
      if (data.associations) setAssociations(data.associations);
      if (data.convergencePoints) setConvergencePoints(data.convergencePoints);
    } catch {
      setError("Request failed — check your connection.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24, fontFamily: "monospace", color: "#fff", background: "#04080f", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 18, color: "#00d8ff", marginBottom: 4 }}>AKKI Brain</h1>
      <p style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginBottom: 20 }}>
        Always-on dependency-discovery engine — separate from chat, learns continuously in the background.
      </p>

      {status && (
        <div style={{ display: "flex", gap: 24, marginBottom: 24, fontSize: 12 }}>
          <div>Pages: <b style={{ color: "#00ff88" }}>{status.totalPages.toLocaleString()}</b></div>
          <div>Sentences: <b style={{ color: "#00ff88" }}>{status.totalSentences.toLocaleString()}</b></div>
          <div>Concepts: <b style={{ color: "#00ff88" }}>{status.conceptCount.toLocaleString()}</b></div>
          <div>Edges: <b style={{ color: "#00ff88" }}>{status.edgeCount.toLocaleString()}</b></div>
          <div>Frontier: <b style={{ color: "#00ff88" }}>{status.frontierSize.toLocaleString()}</b></div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          value={concept}
          onChange={(e) => setConcept(e.target.value)}
          placeholder="concept (e.g. fire)"
          style={{ padding: 8, background: "#0d1117", border: "1px solid rgba(0,216,255,0.3)", color: "#fff", borderRadius: 6 }}
        />
        <input
          value={concept2}
          onChange={(e) => setConcept2(e.target.value)}
          placeholder="optional second concept — what connects them?"
          style={{ padding: 8, background: "#0d1117", border: "1px solid rgba(0,216,255,0.3)", color: "#fff", borderRadius: 6, flex: 1 }}
        />
        <button
          onClick={runDiscover}
          disabled={!concept.trim() || loading}
          style={{ padding: "8px 16px", background: "#00d8ff", color: "#04080f", border: "none", borderRadius: 6, fontWeight: "bold", cursor: loading ? "not-allowed" : "pointer" }}
        >
          {loading ? "..." : "Discover"}
        </button>
      </div>

      {error && <p style={{ color: "#ff3868", fontSize: 12 }}>{error}</p>}

      {associations && (
        <div>
          <h3 style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>Top associations with "{concept}"</h3>
          {associations.map((a) => (
            <div key={a.word} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <span>{a.word}</span>
              <span style={{ color: "#00ff88" }}>G² {a.g2.toFixed(1)} (n={a.count})</span>
            </div>
          ))}
        </div>
      )}

      {convergencePoints && (
        <div>
          <h3 style={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>Convergence points: "{concept}" ↔ "{concept2}"</h3>
          {convergencePoints.map((c) => (
            <div key={c.concept} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <span>{c.concept}</span>
              <span style={{ color: "#00ff88" }}>depth {c.depthFrom1} + {c.depthFrom2} = {c.combinedDepth}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
