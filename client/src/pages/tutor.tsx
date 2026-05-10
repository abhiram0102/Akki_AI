import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";

// ── Types ──────────────────────────────────────────────────────────────────────
interface LearningModule {
  id: string;
  title: string;
  topics: string[];
  difficulty: number;
}

interface LearningPath {
  title: string;
  description: string;
  modules: LearningModule[];
}

interface LearningPaths {
  [key: string]: LearningPath;
}

interface QuizQuestion {
  q: string;
  a: string;
  options: string[];
  explanation?: string;
  difficulty?: number;
}

interface ChallengeData {
  title: string;
  scenario: string;
  objective: string;
  hints: string[];
  tools: string[];
  steps: string[];
  solution: string;
  learningObjectives: string[];
  estimatedTime: string;
  difficulty: number;
}

const DIFFICULTY_LABELS = ["", "Beginner", "Basic", "Intermediate", "Advanced", "Expert"];
const DIFFICULTY_COLORS = ["", "text-green-400", "text-cyan-400", "text-amber-400", "text-red-400", "text-purple-400"];

const TOPIC_SUGGESTIONS = [
  "SQL Injection", "XSS", "SSRF", "Buffer Overflow", "Active Directory",
  "Kerberoasting", "Privilege Escalation", "OSINT", "Malware Analysis",
  "Cryptography", "Network Security", "Reverse Engineering", "Web Security",
  "Cloud Security", "SIEM", "Threat Hunting",
];

export default function TutorPage() {
  const [activeTab, setActiveTab] = useState<"paths" | "quiz" | "explain" | "challenge">("paths");
  const [quizTopic, setQuizTopic] = useState("networking");
  const [quizAnswers, setQuizAnswers] = useState<Record<number, string>>({});
  const [quizResult, setQuizResult] = useState<Record<number, boolean>>({});
  const [showQuizResult, setShowQuizResult] = useState(false);
  const [explainTopic, setExplainTopic] = useState("");
  const [explainLevel, setExplainLevel] = useState("intermediate");
  const [challengeTopic, setChallengeTopic] = useState("");
  const [challengeDiff, setChallengeDiff] = useState(3);
  const [pathGoals, setPathGoals] = useState("");
  const [pathLevel, setPathLevel] = useState("beginner");
  const { toast } = useToast();

  // Fetch learning paths
  const { data: learningPaths, isLoading: pathsLoading } = useQuery<LearningPaths>({
    queryKey: ["/api/tutor/paths"],
  });

  // Quiz
  const quizMutation = useMutation({
    mutationFn: (data: { topic: string; difficulty: number }) =>
      apiRequest("POST", "/api/tutor/quiz", data),
  });

  // Explain
  const explainMutation = useMutation({
    mutationFn: (data: { topic: string; level: string }) =>
      apiRequest("POST", "/api/tutor/explain", data),
  });

  // Challenge
  const challengeMutation = useMutation({
    mutationFn: (data: { topic: string; difficulty: number }) =>
      apiRequest("POST", "/api/tutor/challenge", data),
  });

  // Path generator
  const pathMutation = useMutation({
    mutationFn: (data: { goals: string; currentLevel: string }) =>
      apiRequest("POST", "/api/tutor/path", data),
  });

  const handleQuizSubmit = () => {
    const questions: QuizQuestion[] = (quizMutation.data as any)?.questions || [];
    const results: Record<number, boolean> = {};
    questions.forEach((q, i) => {
      results[i] = quizAnswers[i] === q.a;
    });
    setQuizResult(results);
    setShowQuizResult(true);
    const correct = Object.values(results).filter(Boolean).length;
    toast({
      title: `Score: ${correct}/${questions.length}`,
      description: correct === questions.length ? "Perfect score!" : "Keep practicing!",
    });
  };

  const tabs = [
    { id: "paths", label: "Learning Paths", icon: "fas fa-map" },
    { id: "quiz", label: "Quiz", icon: "fas fa-brain" },
    { id: "explain", label: "Explain Topic", icon: "fas fa-chalkboard-teacher" },
    { id: "challenge", label: "Challenge", icon: "fas fa-trophy" },
  ] as const;

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-black/20">
      {/* Header */}
      <div className="border-b border-white/5 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center">
            <i className="fas fa-graduation-cap text-black text-sm" />
          </div>
          <div>
            <h2 className="font-display text-base font-black text-white tracking-wider">MENTOR</h2>
            <p className="text-xs text-gray-500 font-mono">Adaptive Cybersecurity Education Engine</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-gray-500">
          <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
          <span>TUTOR ACTIVE</span>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex border-b border-white/5 px-6">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-mono border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-emerald-400 text-emerald-400"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            <i className={tab.icon} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">

        {/* ── LEARNING PATHS ─────────────────────────────── */}
        {activeTab === "paths" && (
          <div className="space-y-6 max-w-4xl">
            {/* Standard paths */}
            {pathsLoading ? (
              <div className="flex items-center gap-2 text-gray-500 font-mono text-sm">
                <div className="w-4 h-4 border border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
                Loading paths...
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {Object.entries(learningPaths || {}).map(([key, path]) => (
                  <div key={key} className="glass-card rounded-xl border border-white/10 p-4 hover:border-emerald-400/30 transition-colors">
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="font-mono font-bold text-white text-sm">{path.title}</h3>
                        <p className="text-xs text-gray-500 mt-0.5">{path.description}</p>
                      </div>
                      <span className={`text-xs font-mono px-2 py-0.5 rounded border ${
                        key === "beginner" ? "border-green-400/30 text-green-400 bg-green-400/10" :
                        key === "intermediate" ? "border-cyan-400/30 text-cyan-400 bg-cyan-400/10" :
                        key === "advanced" ? "border-red-400/30 text-red-400 bg-red-400/10" :
                        "border-purple-400/30 text-purple-400 bg-purple-400/10"
                      }`}>
                        {key}
                      </span>
                    </div>
                    <div className="space-y-2">
                      {path.modules.slice(0, 3).map(mod => (
                        <div key={mod.id} className="flex items-center gap-2 text-xs text-gray-400 font-mono">
                          <i className="fas fa-chevron-right text-emerald-400 opacity-60" />
                          <span>{mod.title}</span>
                          <span className={`ml-auto ${DIFFICULTY_COLORS[mod.difficulty] || "text-gray-500"}`}>
                            {"●".repeat(mod.difficulty)}{"○".repeat(5 - mod.difficulty)}
                          </span>
                        </div>
                      ))}
                      {path.modules.length > 3 && (
                        <p className="text-xs text-gray-600 font-mono pl-4">+{path.modules.length - 3} more modules</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Custom path generator */}
            <div className="glass-card rounded-xl border border-emerald-400/20 p-5">
              <h3 className="font-mono font-bold text-emerald-400 text-sm mb-4 flex items-center gap-2">
                <i className="fas fa-magic" /> Generate Personalized Path
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-mono text-gray-400 mb-1 block">Your goals</label>
                  <textarea
                    value={pathGoals}
                    onChange={e => setPathGoals(e.target.value)}
                    placeholder="e.g. I want to pass OSCP, learn Active Directory attacks, and get into red teaming..."
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 font-mono focus:border-emerald-400/40 focus:outline-none resize-none"
                    rows={3}
                  />
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <label className="text-xs font-mono text-gray-400 mb-1 block">Current level</label>
                    <select
                      value={pathLevel}
                      onChange={e => setPathLevel(e.target.value)}
                      className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-emerald-400/40 focus:outline-none"
                    >
                      <option value="beginner">Beginner</option>
                      <option value="intermediate">Intermediate</option>
                      <option value="advanced">Advanced</option>
                    </select>
                  </div>
                  <div className="mt-5">
                    <button
                      onClick={() => pathMutation.mutate({ goals: pathGoals, currentLevel: pathLevel })}
                      disabled={!pathGoals.trim() || pathMutation.isPending}
                      className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-cyan-500 text-black font-bold text-xs font-mono rounded-lg hover:shadow-lg disabled:opacity-40 flex items-center gap-2"
                    >
                      {pathMutation.isPending ? <><div className="w-3 h-3 border border-black/40 border-t-black rounded-full animate-spin" /> Generating...</> : <><i className="fas fa-route" /> Generate</>}
                    </button>
                  </div>
                </div>
              </div>
              {pathMutation.data && (
                <div className="mt-4 p-4 bg-black/40 rounded-lg border border-emerald-400/20">
                  <h4 className="font-mono font-bold text-white text-sm mb-3">{(pathMutation.data as any).title}</h4>
                  <p className="text-xs text-gray-400 mb-3">{(pathMutation.data as any).estimatedTime}</p>
                  <div className="space-y-2">
                    {((pathMutation.data as any).phases || []).map((phase: any, i: number) => (
                      <div key={i} className="flex gap-3 text-xs font-mono">
                        <span className="text-emerald-400 font-bold min-w-[60px]">Phase {phase.phase}</span>
                        <div>
                          <p className="text-white font-bold">{phase.title}</p>
                          <p className="text-gray-500">{phase.milestone}</p>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {phase.topics?.map((t: string) => (
                              <span key={t} className="px-1.5 py-0.5 bg-emerald-400/10 border border-emerald-400/20 rounded text-emerald-400">{t}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── QUIZ ───────────────────────────────────────── */}
        {activeTab === "quiz" && (
          <div className="max-w-2xl space-y-4">
            <div className="glass-card rounded-xl border border-white/10 p-4">
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs font-mono text-gray-400 mb-1 block">Topic</label>
                  <input
                    value={quizTopic}
                    onChange={e => setQuizTopic(e.target.value)}
                    placeholder="e.g. networking, linux_privesc, active_directory..."
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 font-mono focus:border-cyan-400/40 focus:outline-none"
                  />
                </div>
                <div className="mt-5">
                  <button
                    onClick={() => { setQuizAnswers({}); setShowQuizResult(false); quizMutation.mutate({ topic: quizTopic, difficulty: 3 }); }}
                    disabled={quizMutation.isPending}
                    className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-500 text-black font-bold text-xs font-mono rounded-lg disabled:opacity-40 flex items-center gap-2"
                  >
                    {quizMutation.isPending ? <div className="w-3 h-3 border border-black/40 border-t-black rounded-full animate-spin" /> : <i className="fas fa-play" />}
                    Start Quiz
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {["networking", "web_security", "linux_privesc", "active_directory", "malware"].map(t => (
                  <button
                    key={t}
                    onClick={() => setQuizTopic(t)}
                    className="text-xs font-mono px-2 py-0.5 rounded border border-white/10 text-gray-400 hover:border-cyan-400/30 hover:text-cyan-400 transition-colors"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {quizMutation.data && (
              <div className="space-y-4">
                {((quizMutation.data as any).questions || []).map((q: QuizQuestion, i: number) => (
                  <div key={i} className={`glass-card rounded-xl border p-4 transition-colors ${
                    showQuizResult
                      ? quizResult[i] ? "border-green-400/30 bg-green-400/5" : "border-red-400/30 bg-red-400/5"
                      : "border-white/10"
                  }`}>
                    <div className="flex items-start gap-2 mb-3">
                      <span className="text-xs font-mono text-cyan-400 mt-0.5 flex-shrink-0">Q{i + 1}</span>
                      <p className="text-sm text-white font-mono">{q.q}</p>
                      {showQuizResult && (
                        <i className={`fas fa-${quizResult[i] ? "check-circle text-green-400" : "times-circle text-red-400"} ml-auto flex-shrink-0`} />
                      )}
                    </div>
                    <div className="space-y-2">
                      {(q.options || []).map(option => (
                        <button
                          key={option}
                          onClick={() => !showQuizResult && setQuizAnswers(p => ({ ...p, [i]: option }))}
                          className={`w-full text-left px-3 py-2 rounded-lg text-xs font-mono border transition-colors ${
                            showQuizResult
                              ? option === q.a ? "border-green-400/50 bg-green-400/10 text-green-400"
                              : quizAnswers[i] === option ? "border-red-400/50 bg-red-400/10 text-red-400"
                              : "border-white/5 text-gray-500"
                              : quizAnswers[i] === option ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-400"
                              : "border-white/10 text-gray-400 hover:border-white/20 hover:text-gray-300"
                          }`}
                        >
                          {option}
                        </button>
                      ))}
                    </div>
                    {showQuizResult && q.explanation && (
                      <div className="mt-3 p-2 bg-black/30 rounded border border-white/5 text-xs text-gray-400 font-mono">
                        <i className="fas fa-info-circle text-cyan-400 mr-1" />
                        {q.explanation}
                      </div>
                    )}
                  </div>
                ))}
                {!showQuizResult && (quizMutation.data as any).questions?.length > 0 && (
                  <button
                    onClick={handleQuizSubmit}
                    className="w-full py-3 bg-gradient-to-r from-cyan-500 to-blue-500 text-black font-bold text-sm font-mono rounded-xl hover:shadow-lg"
                  >
                    <i className="fas fa-check-double mr-2" /> Submit Answers
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── EXPLAIN ────────────────────────────────────── */}
        {activeTab === "explain" && (
          <div className="max-w-3xl space-y-4">
            <div className="glass-card rounded-xl border border-white/10 p-4">
              <div className="flex gap-3 flex-wrap">
                <div className="flex-1 min-w-48">
                  <label className="text-xs font-mono text-gray-400 mb-1 block">Topic to explain</label>
                  <input
                    value={explainTopic}
                    onChange={e => setExplainTopic(e.target.value)}
                    placeholder="e.g. Kerberoasting, XSS, Buffer Overflow..."
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 font-mono focus:border-cyan-400/40 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-mono text-gray-400 mb-1 block">Level</label>
                  <select
                    value={explainLevel}
                    onChange={e => setExplainLevel(e.target.value)}
                    className="bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-cyan-400/40 focus:outline-none"
                  >
                    <option value="beginner">Beginner</option>
                    <option value="intermediate">Intermediate</option>
                    <option value="advanced">Advanced</option>
                    <option value="expert">Expert</option>
                  </select>
                </div>
                <div className="mt-5">
                  <button
                    onClick={() => explainMutation.mutate({ topic: explainTopic, level: explainLevel })}
                    disabled={!explainTopic.trim() || explainMutation.isPending}
                    className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-cyan-500 text-black font-bold text-xs font-mono rounded-lg disabled:opacity-40 flex items-center gap-2"
                  >
                    {explainMutation.isPending ? <div className="w-3 h-3 border border-black/40 border-t-black rounded-full animate-spin" /> : <i className="fas fa-book-open" />}
                    Explain
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {TOPIC_SUGGESTIONS.slice(0, 8).map(t => (
                  <button
                    key={t}
                    onClick={() => setExplainTopic(t)}
                    className="text-xs font-mono px-2 py-0.5 rounded border border-white/10 text-gray-400 hover:border-emerald-400/30 hover:text-emerald-400 transition-colors"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {explainMutation.isPending && (
              <div className="glass-card rounded-xl border border-emerald-400/20 p-6 text-center">
                <div className="w-8 h-8 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-gray-500 font-mono">MENTOR is preparing your explanation...</p>
              </div>
            )}

            {explainMutation.data && (
              <div className="glass-card rounded-xl border border-emerald-400/20 p-6">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-6 h-6 rounded-lg bg-emerald-500/20 border border-emerald-400/30 flex items-center justify-center">
                    <i className="fas fa-graduation-cap text-emerald-400 text-xs" />
                  </div>
                  <span className="font-mono text-sm text-emerald-400 font-bold">MENTOR · {explainLevel}</span>
                </div>
                <div className="prose-cyber text-sm whitespace-pre-wrap leading-relaxed text-gray-200">
                  {(explainMutation.data as any).explanation}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── CHALLENGE ──────────────────────────────────── */}
        {activeTab === "challenge" && (
          <div className="max-w-3xl space-y-4">
            <div className="glass-card rounded-xl border border-white/10 p-4">
              <div className="flex gap-3 flex-wrap">
                <div className="flex-1 min-w-48">
                  <label className="text-xs font-mono text-gray-400 mb-1 block">Challenge topic</label>
                  <input
                    value={challengeTopic}
                    onChange={e => setChallengeTopic(e.target.value)}
                    placeholder="e.g. SQL Injection, Privilege Escalation..."
                    className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 font-mono focus:border-amber-400/40 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-mono text-gray-400 mb-1 block">Difficulty</label>
                  <select
                    value={challengeDiff}
                    onChange={e => setChallengeDiff(Number(e.target.value))}
                    className="bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-amber-400/40 focus:outline-none"
                  >
                    {[1, 2, 3, 4, 5].map(d => (
                      <option key={d} value={d}>{DIFFICULTY_LABELS[d]}</option>
                    ))}
                  </select>
                </div>
                <div className="mt-5">
                  <button
                    onClick={() => challengeMutation.mutate({ topic: challengeTopic, difficulty: challengeDiff })}
                    disabled={!challengeTopic.trim() || challengeMutation.isPending}
                    className="px-4 py-2 bg-gradient-to-r from-amber-500 to-red-500 text-black font-bold text-xs font-mono rounded-lg disabled:opacity-40 flex items-center gap-2"
                  >
                    {challengeMutation.isPending ? <div className="w-3 h-3 border border-black/40 border-t-black rounded-full animate-spin" /> : <i className="fas fa-trophy" />}
                    Generate
                  </button>
                </div>
              </div>
            </div>

            {challengeMutation.data && (() => {
              const ch = challengeMutation.data as unknown as ChallengeData;
              return (
                <div className="space-y-4">
                  <div className="glass-card rounded-xl border border-amber-400/20 p-5">
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <h3 className="font-mono font-bold text-white text-base">{ch.title}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`text-xs font-mono ${DIFFICULTY_COLORS[ch.difficulty]}`}>
                            {"●".repeat(ch.difficulty)}{"○".repeat(5 - ch.difficulty)} {DIFFICULTY_LABELS[ch.difficulty]}
                          </span>
                          <span className="text-gray-600">·</span>
                          <span className="text-xs text-gray-500 font-mono">
                            <i className="fas fa-clock mr-1" />{ch.estimatedTime}
                          </span>
                        </div>
                      </div>
                      <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-400/30 flex items-center justify-center">
                        <i className="fas fa-trophy text-amber-400" />
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div>
                        <p className="text-xs font-mono text-amber-400 font-bold mb-1">SCENARIO</p>
                        <p className="text-sm text-gray-300">{ch.scenario}</p>
                      </div>
                      <div>
                        <p className="text-xs font-mono text-amber-400 font-bold mb-1">OBJECTIVE</p>
                        <p className="text-sm text-gray-300 font-mono">{ch.objective}</p>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="glass-card rounded-xl border border-white/10 p-4">
                      <p className="text-xs font-mono text-cyan-400 font-bold mb-3">STEPS</p>
                      <ol className="space-y-1.5">
                        {ch.steps.map((step, i) => (
                          <li key={i} className="flex gap-2 text-xs font-mono text-gray-300">
                            <span className="text-cyan-400 font-bold min-w-[20px]">{i + 1}.</span>
                            {step}
                          </li>
                        ))}
                      </ol>
                    </div>

                    <div className="space-y-4">
                      <div className="glass-card rounded-xl border border-white/10 p-4">
                        <p className="text-xs font-mono text-green-400 font-bold mb-2">TOOLS</p>
                        <div className="flex flex-wrap gap-1.5">
                          {ch.tools.map(t => (
                            <span key={t} className="text-xs font-mono px-2 py-0.5 bg-green-400/10 border border-green-400/20 rounded text-green-400">{t}</span>
                          ))}
                        </div>
                      </div>

                      <div className="glass-card rounded-xl border border-white/10 p-4">
                        <p className="text-xs font-mono text-amber-400 font-bold mb-2">HINTS</p>
                        <ol className="space-y-1">
                          {ch.hints.map((h, i) => (
                            <li key={i} className="text-xs text-gray-400 font-mono">
                              <span className="text-amber-400 mr-1">💡</span>{h}
                            </li>
                          ))}
                        </ol>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
}
