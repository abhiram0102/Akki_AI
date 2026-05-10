import { useLocation } from "wouter";
import { useVoice } from "@/hooks/use-voice";
import { useEmotionalState } from "@/store/emotional-state";
import { useChat } from "@/store/chat";
import ChatInterface from "@/components/chat/chat-interface";
import CodingPage from "@/pages/coding";
import RedTeamPage from "@/pages/redteam";
import OSINTPage from "@/pages/osint";
import ReportsPage from "@/pages/reports";
import TutorPage from "@/pages/tutor";
import AgentsPage from "@/pages/agents";

const WORKSPACE_META: Record<string, { title: string; icon: string; color: string; tagline: string }> = {
  "/":        { title: "Chat & RAG",    icon: "fas fa-comments",       color: "text-cyan-400",    tagline: "Multi-agent AI conversation with document intelligence" },
  "/coding":  { title: "Code Audit",    icon: "fas fa-code",           color: "text-green-400",   tagline: "AI-powered vulnerability analysis and exploit research" },
  "/redteam": { title: "Red Team",      icon: "fas fa-crosshairs",     color: "text-red-400",     tagline: "Attack simulation and adversarial operation planning" },
  "/osint":   { title: "OSINT",         icon: "fas fa-satellite-dish", color: "text-amber-400",   tagline: "Open-source intelligence and reconnaissance operations" },
  "/reports": { title: "Reports",       icon: "fas fa-file-code",      color: "text-purple-400",  tagline: "AI-generated security reports with MITRE ATT&CK mapping" },
  "/tutor":   { title: "Tutor",         icon: "fas fa-graduation-cap", color: "text-emerald-400", tagline: "Adaptive cybersecurity education and certification prep" },
  "/agents":  { title: "Agent Network", icon: "fas fa-robot",          color: "text-blue-400",    tagline: "7 specialist AI agents with live tool execution" },
};

export default function MainContent({
  onInitAudio,
  audioInitialized,
  audioContext,
}: {
  onInitAudio: () => void;
  audioInitialized: boolean;
  audioContext: AudioContext | null;
}) {
  const [location] = useLocation();
  const { toggleListening, isListening, isActive } = useVoice(audioContext);
  const { emotionalState } = useEmotionalState();
  const { currentPlan, activeAgent, isStreaming } = useChat();

  const meta = WORKSPACE_META[location] || WORKSPACE_META["/"];

  const renderWorkspace = () => {
    switch (location) {
      case "/coding":  return <CodingPage />;
      case "/redteam": return <RedTeamPage />;
      case "/osint":   return <OSINTPage />;
      case "/reports": return <ReportsPage />;
      case "/tutor":   return <TutorPage />;
      case "/agents":  return <AgentsPage />;
      default:         return <ChatInterface onInitAudio={onInitAudio} audioInitialized={audioInitialized} audioContext={audioContext} />;
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0" data-testid="main-content">
      {/* ── Top Header ─────────────────────────────────────── */}
      <header className="border-b border-white/5 px-5 py-3 flex items-center justify-between flex-shrink-0 bg-black/20 backdrop-blur-sm">
        {/* Left: Workspace info */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <i className={`${meta.icon} text-sm ${meta.color}`} />
            <span className="font-mono font-bold text-white text-sm">{meta.title}</span>
          </div>
          <span className="text-gray-700">·</span>
          <span className="text-xs text-gray-500 font-mono hidden md:block">{meta.tagline}</span>

          {/* Streaming indicator */}
          {isStreaming && (
            <div className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 ml-2">
              <div className="flex gap-0.5">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-1 h-3 bg-cyan-400 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 0.1}s` }} />
                ))}
              </div>
              <span>streaming</span>
            </div>
          )}

          {/* Active agent badge */}
          {activeAgent && location === "/" && (
            <div className="flex items-center gap-1.5 text-xs font-mono bg-cyan-400/10 border border-cyan-400/20 rounded-full px-2 py-0.5">
              <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />
              <span className="text-cyan-400 font-bold">{activeAgent.agentName}</span>
            </div>
          )}

          {/* Plan status */}
          {currentPlan && (
            <div className={`flex items-center gap-1.5 text-xs font-mono px-2 py-0.5 rounded-full border ${
              currentPlan.status === "executing" ? "border-cyan-400/30 text-cyan-400 bg-cyan-400/5" :
              currentPlan.status === "completed" ? "border-green-400/30 text-green-400 bg-green-400/5" :
              currentPlan.status === "failed" ? "border-red-400/30 text-red-400 bg-red-400/5" :
              "border-amber-400/30 text-amber-400 bg-amber-400/5"
            }`}>
              <div className={`w-1.5 h-1.5 rounded-full ${
                currentPlan.status === "executing" ? "bg-cyan-400 animate-pulse" :
                currentPlan.status === "completed" ? "bg-green-400" :
                currentPlan.status === "failed" ? "bg-red-400" : "bg-amber-400"
              }`} />
              {currentPlan.goal.slice(0, 25)}{currentPlan.goal.length > 25 ? "..." : ""}
            </div>
          )}
        </div>

        {/* Right: Controls */}
        <div className="flex items-center gap-2">
          {/* Voice */}
          <button
            onClick={toggleListening}
            className={`p-2 rounded-lg border text-xs transition-all ${
              isListening
                ? "border-green-400/50 bg-green-400/10 text-green-400 animate-pulse"
                : isActive
                ? "border-white/10 text-gray-400 hover:border-cyan-400/30 hover:text-cyan-400"
                : "border-white/10 text-gray-600 opacity-40 cursor-not-allowed"
            }`}
            disabled={!isActive}
            data-testid="button-voice-toggle"
            title={isListening ? "Stop listening" : "Voice input"}
          >
            <i className={`fas fa-microphone text-xs ${isListening ? "animate-pulse" : ""}`} />
          </button>

          {/* Audio init */}
          {!audioInitialized && location === "/" && (
            <button
              onClick={onInitAudio}
              className="px-3 py-1.5 text-xs font-mono border border-cyan-400/30 text-cyan-400 rounded-lg hover:bg-cyan-400/10 transition-colors"
            >
              <i className="fas fa-volume-up mr-1" /> Enable Audio
            </button>
          )}

          {/* System status */}
          <div className="flex items-center gap-1.5 text-xs font-mono text-gray-600 border border-white/5 rounded-lg px-2 py-1.5">
            <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
            <span>AKKI ONLINE</span>
          </div>
        </div>
      </header>

      {/* ── Workspace Content ─────────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {renderWorkspace()}
      </div>
    </div>
  );
}
