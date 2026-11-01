import { useState, useRef } from "react";
import { motion } from "framer-motion";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

// ── Types ────────────────────────────────────────────────────────────────────

interface SigmaHistory {
  id: string;
  statement: string;
  timestamp: string;
  solution?: string;
}

type SigmaPhase = "idle" | "thinking" | "clarifying" | "solving" | "done" | "error";

// ── Style constants ──────────────────────────────────────────────────────────

const PNL: React.CSSProperties = {
  background: "rgba(8,13,26,0.95)",
  border: "1px solid rgba(155,89,252,0.20)",
  borderRadius: 14,
};

const HDR: React.CSSProperties = {
  fontFamily: "monospace",
  fontSize: 9,
  color: "rgba(155,89,252,0.65)",
  textTransform: "uppercase",
  letterSpacing: "0.18em",
  fontWeight: 700,
};

const BTN_PRIMARY: React.CSSProperties = {
  background: "linear-gradient(135deg,#9b59fc,#7c3aed)",
  color: "#fff",
  border: "none",
  borderRadius: 10,
  padding: "10px 20px",
  fontFamily: "monospace",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: 8,
  letterSpacing: "0.05em",
};

const BTN_SECONDARY: React.CSSProperties = {
  background: "rgba(155,89,252,0.10)",
  color: "#9b59fc",
  border: "1px solid rgba(155,89,252,0.35)",
  borderRadius: 8,
  padding: "8px 16px",
  fontFamily: "monospace",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

// ── Section config ───────────────────────────────────────────────────────────

const SECTION_STYLES: Record<
  string,
  { color: string; bg: string; border: string; icon: string }
> = {
  FORMULATION: {
    color: "#00ff88",
    bg: "rgba(0,255,136,0.05)",
    border: "rgba(0,255,136,0.20)",
    icon: "fas fa-equals",
  },
  FOUNDATION: {
    color: "#ffb700",
    bg: "rgba(255,183,0,0.05)",
    border: "rgba(255,183,0,0.20)",
    icon: "fas fa-lightbulb",
  },
  ALGORITHM: {
    color: "#9b59fc",
    bg: "rgba(155,89,252,0.06)",
    border: "rgba(155,89,252,0.22)",
    icon: "fas fa-sitemap",
  },
  COMPLEXITY: {
    color: "#00d8ff",
    bg: "rgba(0,216,255,0.05)",
    border: "rgba(0,216,255,0.20)",
    icon: "fas fa-chart-line",
  },
  IMPLEMENTATION: {
    color: "#4ade80",
    bg: "rgba(74,222,128,0.04)",
    border: "rgba(74,222,128,0.18)",
    icon: "fas fa-code",
  },
  VERIFICATION: {
    color: "#ec4899",
    bg: "rgba(236,72,153,0.05)",
    border: "rgba(236,72,153,0.18)",
    icon: "fas fa-check-double",
  },
};

// ── Section content renderer ─────────────────────────────────────────────────

function renderSectionContent(
  content: string,
  section: string
): React.ReactNode {
  if (section === "IMPLEMENTATION") {
    const codeMatch = content.match(/```(?:python)?\n?([\s\S]*?)```/);
    if (codeMatch) {
      const fenceIndex = content.indexOf("```");
      const before = content.slice(0, fenceIndex).trim();
      const code = codeMatch[1];
      const after = content.slice(fenceIndex + codeMatch[0].length).trim();
      return (
        <>
          {before && (
            <div style={{ marginBottom: 8, color: "rgba(255,255,255,0.60)" }}>
              {before}
            </div>
          )}
          <div
            style={{
              borderRadius: 8,
              overflow: "hidden",
              border: "1px solid rgba(74,222,128,0.22)",
              marginBottom: before || after ? 8 : 0,
            }}
          >
            <div
              style={{
                background: "rgba(0,0,0,0.50)",
                padding: "4px 12px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderBottom: "1px solid rgba(74,222,128,0.15)",
              }}
            >
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: 9,
                  color: "rgba(74,222,128,0.7)",
                }}
              >
                python
              </span>
              <button
                onClick={() => navigator.clipboard.writeText(code)}
                style={{
                  background: "none",
                  border: "none",
                  color: "rgba(74,222,128,0.5)",
                  cursor: "pointer",
                  fontSize: 9,
                }}
                title="Copy code"
              >
                <i className="fas fa-copy" />
              </button>
            </div>
            <pre
              style={{
                background: "rgba(0,0,0,0.40)",
                padding: "12px 14px",
                overflowX: "auto",
                fontFamily: "monospace",
                fontSize: 12,
                color: "#4ade80",
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              <code>{code}</code>
            </pre>
          </div>
          {after && (
            <div style={{ color: "rgba(255,255,255,0.55)" }}>{after}</div>
          )}
        </>
      );
    }
  }
  return <span>{content}</span>;
}

// ── Solution renderer ────────────────────────────────────────────────────────

function renderSigmaSolution(text: string): React.ReactNode {
  if (!text) return null;

  const parts = text.split(
    /([Σ∑] (?:FORMULATION|FOUNDATION|ALGORITHM|COMPLEXITY|IMPLEMENTATION|VERIFICATION))/g
  );
  const elements: React.ReactNode[] = [];

  let i = 0;
  while (i < parts.length) {
    const part = parts[i];
    const headerMatch = part.match(
      /[Σ∑] (FORMULATION|FOUNDATION|ALGORITHM|COMPLEXITY|IMPLEMENTATION|VERIFICATION)/
    );

    if (headerMatch) {
      const sectionKey = headerMatch[1];
      const style = SECTION_STYLES[sectionKey];
      const content = parts[i + 1] ?? "";
      i += 2;

      elements.push(
        <div
          key={`section-${i}`}
          style={{
            marginBottom: 16,
            borderRadius: 10,
            overflow: "hidden",
            border: `1px solid ${style.border}`,
            background: style.bg,
          }}
        >
          {/* Section header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 14px",
              borderBottom: `1px solid ${style.border}`,
              background: "rgba(8,13,26,0.60)",
            }}
          >
            <i
              className={style.icon}
              style={{ color: style.color, fontSize: 11 }}
            />
            <span
              style={{
                fontFamily: "monospace",
                fontSize: 10,
                fontWeight: 700,
                color: style.color,
                letterSpacing: "0.12em",
              }}
            >
              Σ {sectionKey}
            </span>
            <button
              onClick={() => navigator.clipboard.writeText(content.trim())}
              style={{
                marginLeft: "auto",
                background: "none",
                border: "none",
                color: "rgba(255,255,255,0.25)",
                cursor: "pointer",
                fontSize: 9,
                padding: 2,
              }}
              title="Copy section"
            >
              <i className="fas fa-copy" />
            </button>
          </div>
          {/* Section content */}
          <div
            style={{
              padding: "12px 14px",
              fontFamily: "monospace",
              fontSize: 12,
              color: "rgba(255,255,255,0.75)",
              lineHeight: 1.75,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {renderSectionContent(content.trim(), sectionKey)}
          </div>
        </div>
      );
    } else if (part.trim()) {
      elements.push(
        <p
          key={`prose-${i}`}
          style={{
            fontFamily: "monospace",
            fontSize: 12,
            color: "rgba(255,255,255,0.55)",
            lineHeight: 1.7,
            marginBottom: 8,
          }}
        >
          {part.trim()}
        </p>
      );
      i++;
    } else {
      i++;
    }
  }

  return <>{elements}</>;
}

// ── Main component ───────────────────────────────────────────────────────────

export default function SigmaPage() {
  const [statement, setStatement] = useState("");
  const [phase, setPhase] = useState<SigmaPhase>("idle");
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [solution, setSolution] = useState<string | null>(null);
  const [history, setHistory] = useState<SigmaHistory[]>([]);
  const [activeHistory, setActiveHistory] = useState<SigmaHistory | null>(null);
  const { toast } = useToast();
  const outputRef = useRef<HTMLDivElement>(null);

  const solve = async (stmt: string, ans: Record<string, string> = {}) => {
    if (!stmt.trim()) return;
    setPhase("thinking");
    setSolution(null);
    setQuestions([]);
    try {
      const result = (await api.post("/api/protected/sigma/solve", {
        statement: stmt,
        answers: ans,
      })) as {
        needs_clarification: boolean;
        questions: string[];
        solution: string | null;
      };

      if (result.needs_clarification && result.questions.length > 0) {
        setQuestions(result.questions);
        setAnswers({});
        setPhase("clarifying");
      } else {
        setSolution(result.solution ?? "");
        setPhase("done");
        const entry: SigmaHistory = {
          id: Date.now().toString(),
          statement: stmt,
          timestamp: new Date().toLocaleTimeString(),
          solution: result.solution ?? "",
        };
        setHistory((prev) => [entry, ...prev].slice(0, 20));
        setActiveHistory(entry);
        setTimeout(
          () => outputRef.current?.scrollIntoView({ behavior: "smooth" }),
          100
        );
      }
    } catch (e) {
      setPhase("error");
      toast({
        title: "SIGMA error",
        description: String(e),
        variant: "destructive",
      });
    }
  };

  const submitAnswers = () => {
    solve(statement, answers);
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#04080f",
        overflow: "hidden",
      }}
    >
      {/* ── Hero ── */}
      <div
        style={{
          padding: "16px 20px 12px",
          flexShrink: 0,
          borderBottom: "1px solid rgba(155,89,252,0.15)",
          background:
            "linear-gradient(to right, rgba(155,89,252,0.08) 0%, rgba(4,8,15,0.97) 60%)",
          position: "relative",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: 2,
            background:
              "linear-gradient(90deg,transparent,rgba(155,89,252,0.9),rgba(124,58,237,0.5),transparent)",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 14,
              flexShrink: 0,
              background: "linear-gradient(135deg,#9b59fc,#7c3aed)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 28px rgba(155,89,252,0.50)",
              fontSize: 22,
              color: "#fff",
              fontFamily: "monospace",
              fontWeight: 900,
            }}
          >
            Σ
          </div>
          <div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: "rgba(155,89,252,0.7)",
                textTransform: "uppercase",
                letterSpacing: "0.22em",
                marginBottom: 3,
              }}
            >
              ▸ MATHEMATICAL REASONING ENGINE
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontWeight: 900,
                fontSize: 20,
                color: "#fff",
                lineHeight: 1.1,
              }}
            >
              SIGMA{" "}
              <span
                style={{
                  background: "linear-gradient(135deg,#9b59fc,#00d8ff)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                (Σ)
              </span>
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 11,
                color: "rgba(255,255,255,0.35)",
                marginTop: 3,
              }}
            >
              Algorithms · Theorems · Complexity · Formal Proofs · Working Code
            </div>
          </div>
          <div
            style={{
              marginLeft: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 4,
              alignItems: "flex-end",
            }}
          >
            {["O(·) Analysis", "Theorem Proving", "Code Generation"].map(
              (tag) => (
                <span
                  key={tag}
                  style={{
                    padding: "2px 10px",
                    borderRadius: 999,
                    fontFamily: "monospace",
                    fontSize: 9,
                    background: "rgba(155,89,252,0.08)",
                    border: "1px solid rgba(155,89,252,0.22)",
                    color: "rgba(155,89,252,0.70)",
                  }}
                >
                  {tag}
                </span>
              )
            )}
          </div>
        </div>
      </div>

      {/* ── Split layout ── */}
      <div
        style={{
          display: "flex",
          flex: 1,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        {/* ── Left panel: input + history ── */}
        <div
          style={{
            width: 320,
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            borderRight: "1px solid rgba(155,89,252,0.15)",
            background: "rgba(4,8,15,0.60)",
          }}
        >
          {/* Problem input */}
          <div
            style={{
              padding: 16,
              borderBottom: "1px solid rgba(155,89,252,0.12)",
              flexShrink: 0,
            }}
          >
            <div style={{ ...HDR, marginBottom: 8 }}>
              <i
                className="fas fa-keyboard"
                style={{ marginRight: 5, fontSize: 8 }}
              />
              Problem Statement
            </div>
            <textarea
              value={statement}
              onChange={(e) => setStatement(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.ctrlKey) solve(statement);
              }}
              placeholder={`Describe the problem... e.g. "Design an O(n log n) algorithm to find all pairs of elements in an array that sum to a target value"`}
              style={{
                width: "100%",
                minHeight: 120,
                background: "rgba(155,89,252,0.06)",
                border: "1px solid rgba(155,89,252,0.22)",
                color: "#fff",
                borderRadius: 10,
                padding: "10px 12px",
                fontFamily: "monospace",
                fontSize: 11,
                lineHeight: 1.6,
                outline: "none",
                resize: "vertical",
                boxSizing: "border-box",
              }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button
                onClick={() => solve(statement)}
                disabled={
                  !statement.trim() ||
                  phase === "thinking" ||
                  phase === "solving"
                }
                style={{
                  ...BTN_PRIMARY,
                  flex: 1,
                  justifyContent: "center",
                  opacity:
                    statement.trim() &&
                    phase !== "thinking" &&
                    phase !== "solving"
                      ? 1
                      : 0.4,
                }}
              >
                {phase === "thinking" || phase === "solving" ? (
                  <>
                    <i
                      className="fas fa-circle-notch fa-spin"
                      style={{ fontSize: 11 }}
                    />{" "}
                    Solving...
                  </>
                ) : (
                  <>
                    <span style={{ fontSize: 14 }}>Σ</span> Solve
                  </>
                )}
              </button>
              <button
                onClick={() => {
                  setStatement("");
                  setSolution(null);
                  setPhase("idle");
                  setQuestions([]);
                }}
                style={BTN_SECONDARY}
                title="Clear"
              >
                <i className="fas fa-times" />
              </button>
            </div>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: "rgba(255,255,255,0.20)",
                marginTop: 6,
              }}
            >
              Ctrl+Enter to solve · SIGMA will ask if clarification needed
            </div>
          </div>

          {/* Quick examples */}
          <div
            style={{
              padding: "10px 16px",
              borderBottom: "1px solid rgba(155,89,252,0.10)",
              flexShrink: 0,
            }}
          >
            <div style={{ ...HDR, marginBottom: 7 }}>Example Problems</div>
            {[
              "Design an algorithm to detect a cycle in a directed graph",
              "Find the most efficient way to multiply two large sparse matrices",
              "Create a formula to calculate RSA key generation complexity",
              "Prove that merge sort has optimal comparison complexity",
            ].map((ex) => (
              <button
                key={ex}
                onClick={() => setStatement(ex)}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "5px 8px",
                  marginBottom: 4,
                  background: "rgba(155,89,252,0.04)",
                  border: "1px solid rgba(155,89,252,0.12)",
                  borderRadius: 6,
                  color: "rgba(255,255,255,0.45)",
                  fontFamily: "monospace",
                  fontSize: 9,
                  cursor: "pointer",
                  lineHeight: 1.4,
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.color = "#9b59fc")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.color = "rgba(255,255,255,0.45)")
                }
              >
                {ex}
              </button>
            ))}
          </div>

          {/* History */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "10px 16px",
              overscrollBehavior: "contain",
            }}
          >
            <div style={{ ...HDR, marginBottom: 7 }}>
              History ({history.length})
            </div>
            {history.length === 0 && (
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 10,
                  color: "rgba(255,255,255,0.20)",
                  textAlign: "center",
                  marginTop: 20,
                }}
              >
                Solved problems appear here
              </div>
            )}
            {history.map((h) => (
              <div
                key={h.id}
                onClick={() => {
                  setActiveHistory(h);
                  setSolution(h.solution ?? null);
                  setPhase("done");
                }}
                style={{
                  padding: "7px 10px",
                  marginBottom: 5,
                  borderRadius: 8,
                  cursor: "pointer",
                  background:
                    activeHistory?.id === h.id
                      ? "rgba(155,89,252,0.12)"
                      : "rgba(255,255,255,0.03)",
                  border: `1px solid ${
                    activeHistory?.id === h.id
                      ? "rgba(155,89,252,0.35)"
                      : "rgba(255,255,255,0.06)"
                  }`,
                }}
              >
                <div
                  style={{
                    fontFamily: "monospace",
                    fontSize: 9,
                    color: "#9b59fc",
                    marginBottom: 2,
                  }}
                >
                  {h.timestamp}
                </div>
                <div
                  style={{
                    fontFamily: "monospace",
                    fontSize: 10,
                    color: "rgba(255,255,255,0.55)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {h.statement}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Right panel: output ── */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: 20,
            overscrollBehavior: "contain",
          }}
          ref={outputRef}
        >
          {/* Idle state */}
          {phase === "idle" && !solution && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                gap: 16,
                opacity: 0.6,
              }}
            >
              <div
                style={{
                  fontSize: 64,
                  color: "#9b59fc",
                  textShadow: "0 0 30px rgba(155,89,252,0.6)",
                  fontFamily: "monospace",
                  fontWeight: 900,
                }}
              >
                Σ
              </div>
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 14,
                  color: "rgba(255,255,255,0.35)",
                  textAlign: "center",
                }}
              >
                State your problem.
                <br />
                <span
                  style={{
                    fontSize: 11,
                    color: "rgba(255,255,255,0.20)",
                  }}
                >
                  SIGMA will formalize it mathematically and produce working
                  code.
                </span>
              </div>
            </div>
          )}

          {/* Thinking */}
          {phase === "thinking" && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                gap: 14,
              }}
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                style={{
                  fontSize: 48,
                  color: "#9b59fc",
                  fontFamily: "monospace",
                  fontWeight: 900,
                }}
              >
                Σ
              </motion.div>
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 13,
                  color: "rgba(155,89,252,0.70)",
                }}
              >
                Formulating mathematical structure...
              </div>
            </motion.div>
          )}

          {/* Clarifying questions */}
          {phase === "clarifying" && questions.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ maxWidth: 700 }}
            >
              <div
                style={{
                  ...PNL,
                  padding: "18px 20px",
                  marginBottom: 16,
                  border: "1px solid rgba(255,183,0,0.30)",
                  background: "rgba(255,183,0,0.05)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 14,
                  }}
                >
                  <i
                    className="fas fa-question-circle"
                    style={{ color: "#ffb700", fontSize: 14 }}
                  />
                  <span
                    style={{
                      fontFamily: "monospace",
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#ffb700",
                    }}
                  >
                    SIGMA needs clarification
                  </span>
                </div>
                <div
                  style={{
                    fontFamily: "monospace",
                    fontSize: 10,
                    color: "rgba(255,255,255,0.40)",
                    marginBottom: 16,
                  }}
                >
                  Answer these questions to get a precise, well-constrained
                  solution:
                </div>
                {questions.map((q, idx) => (
                  <div key={idx} style={{ marginBottom: 12 }}>
                    <div
                      style={{
                        fontFamily: "monospace",
                        fontSize: 11,
                        color: "#ffb700",
                        marginBottom: 5,
                      }}
                    >
                      Q{idx + 1}. {q}
                    </div>
                    <input
                      value={answers[q] ?? ""}
                      onChange={(e) =>
                        setAnswers((prev) => ({ ...prev, [q]: e.target.value }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") submitAnswers();
                      }}
                      placeholder="Your answer..."
                      style={{
                        width: "100%",
                        background: "rgba(255,183,0,0.06)",
                        border: "1px solid rgba(255,183,0,0.25)",
                        color: "#fff",
                        borderRadius: 8,
                        padding: "8px 12px",
                        fontFamily: "monospace",
                        fontSize: 11,
                        outline: "none",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>
                ))}
                <button
                  onClick={submitAnswers}
                  style={{
                    ...BTN_PRIMARY,
                    background: "linear-gradient(135deg,#ffb700,#f59e0b)",
                    marginTop: 8,
                  }}
                >
                  <i className="fas fa-arrow-right" /> Submit Answers
                </button>
              </div>
            </motion.div>
          )}

          {/* Solution output */}
          {solution && phase === "done" && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              style={{ maxWidth: 860 }}
            >
              {/* Solution header */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  marginBottom: 16,
                }}
              >
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: 8,
                    background: "linear-gradient(135deg,#9b59fc,#7c3aed)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 14,
                    color: "#fff",
                    fontFamily: "monospace",
                    fontWeight: 900,
                  }}
                >
                  Σ
                </div>
                <span
                  style={{
                    fontFamily: "monospace",
                    fontSize: 11,
                    fontWeight: 700,
                    color: "#9b59fc",
                  }}
                >
                  SIGMA SOLUTION
                </span>
                <button
                  onClick={() => navigator.clipboard.writeText(solution)}
                  style={{
                    marginLeft: "auto",
                    ...BTN_SECONDARY,
                    padding: "4px 12px",
                    fontSize: 10,
                  }}
                >
                  <i
                    className="fas fa-copy"
                    style={{ marginRight: 5, fontSize: 9 }}
                  />
                  Copy All
                </button>
              </div>
              {renderSigmaSolution(solution)}
            </motion.div>
          )}

          {/* Error */}
          {phase === "error" && (
            <div
              style={{
                ...PNL,
                padding: 20,
                border: "1px solid rgba(255,56,104,0.30)",
                maxWidth: 500,
              }}
            >
              <i
                className="fas fa-exclamation-triangle"
                style={{
                  color: "#ff3868",
                  fontSize: 16,
                  marginBottom: 8,
                  display: "block",
                }}
              />
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 11,
                  color: "#ff3868",
                }}
              >
                SIGMA encountered an error. Please try again.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
