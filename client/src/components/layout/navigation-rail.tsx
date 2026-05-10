import { Link, useLocation } from "wouter";
import { useAuth } from "@/lib/auth";
import { useEmotionalStore } from "@/store/emotional-state";
import { useState, useEffect } from "react";
import { useVoice } from "@/hooks/use-voice";
import { useQuery } from "@tanstack/react-query";
import { useChat } from "@/store/chat";
import VoiceVisualizer from "@/components/ui/voice-visualizer";

interface Session {
  id: string;
  title: string;
  lastMessageAt?: string;
  startedAt: string;
}

const WORKSPACES = [
  { id: "chat",    name: "Chat / RAG",   icon: "fas fa-comments",       path: "/",        color: "text-cyan-400" },
  { id: "coding",  name: "Code Audit",   icon: "fas fa-code",           path: "/coding",  color: "text-green-400" },
  { id: "redteam", name: "Red Team",     icon: "fas fa-crosshairs",     path: "/redteam", color: "text-red-400" },
  { id: "osint",   name: "OSINT",        icon: "fas fa-satellite-dish", path: "/osint",   color: "text-amber-400" },
  { id: "reports", name: "Reports",      icon: "fas fa-file-code",      path: "/reports", color: "text-purple-400" },
  { id: "tutor",   name: "Tutor",        icon: "fas fa-graduation-cap", path: "/tutor",   color: "text-emerald-400" },
  { id: "agents",  name: "Agents",       icon: "fas fa-robot",          path: "/agents",  color: "text-blue-400" },
];

export default function NavigationRail() {
  const [location] = useLocation();
  const { user, logout } = useAuth();
  const emotionalState = useEmotionalStore((state) => state.emotionalState);
  const { activeAgent } = useChat();
  const [audioContext, setAudioContext] = useState<AudioContext | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && !audioContext) {
      try {
        setAudioContext(new (window.AudioContext || (window as any).webkitAudioContext)());
      } catch { /* ignore */ }
    }
    return () => { audioContext?.close(); };
  }, []);

  const { isListening, isActive } = useVoice(audioContext);

  const { data: recentSessions } = useQuery<Session[]>({
    queryKey: ["/api/protected/sessions"],
    staleTime: 60000,
    select: (data) => (Array.isArray(data) ? data.slice(0, 4) : []),
    initialData: [],
    enabled: !!localStorage.getItem("auth_token"),
  });

  const initials = (name: string) =>
    name.split(" ").map(n => n[0]).join("").toUpperCase().slice(0, 2);

  const timeAgo = (d: string) => {
    const diff = Math.floor((Date.now() - new Date(d).getTime()) / 60000);
    if (diff < 60) return `${diff}m`;
    if (diff < 1440) return `${Math.floor(diff / 60)}h`;
    return `${Math.floor(diff / 1440)}d`;
  };

  return (
    <div className="w-56 flex flex-col border-r border-white/5 bg-black/30 backdrop-blur-xl relative" data-testid="navigation-rail">
      {/* Top scanline accent */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent" />

      {/* ── Logo / Identity ─────────────────────────────── */}
      <div className="p-4 border-b border-white/5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500 to-green-500 flex items-center justify-center shadow-lg shadow-cyan-500/20 flex-shrink-0">
            <i className="fas fa-brain text-black text-base" />
          </div>
          <div>
            <h1 className="font-display text-sm font-black text-white tracking-wider">AKKI AI</h1>
            <p className="text-xs text-gray-600 font-mono">Cyber OS v2.0</p>
          </div>
        </div>

        {/* Voice Status */}
        <div className="glass-card rounded-lg p-2.5 border border-white/5">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-green-400 animate-pulse shadow-sm shadow-green-400" : "bg-gray-600"}`} />
              <span className="text-xs font-mono font-bold text-gray-300">
                {activeAgent ? activeAgent.agentName : "NEXUS"}
              </span>
            </div>
            <span className="text-xs text-gray-600 font-mono">
              {activeAgent?.agentRole?.slice(0, 12) || "Standby"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <VoiceVisualizer isActive={isListening} />
            <span className={`text-xs font-mono ${isListening ? "text-green-400" : isActive ? "text-cyan-400" : "text-gray-600"}`}>
              {isListening ? "Listening..." : isActive ? "Ready" : "Offline"}
            </span>
          </div>
        </div>
      </div>

      {/* ── Navigation ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-3">
        <p className="text-xs font-mono text-gray-600 uppercase tracking-widest mb-2 px-1">Workspaces</p>
        <nav className="space-y-0.5">
          {WORKSPACES.map((ws) => {
            const isActive = location === ws.path || (ws.path !== "/" && location.startsWith(ws.path));
            return (
              <Link
                key={ws.id}
                href={ws.path}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-all text-sm group ${
                  isActive
                    ? "bg-cyan-400/10 border border-cyan-400/25 text-white"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200 border border-transparent"
                }`}
                data-testid={`nav-${ws.id}`}
              >
                <i className={`${ws.icon} w-3.5 text-xs ${isActive ? ws.color : "opacity-60 group-hover:opacity-80"}`} />
                <span className={`font-mono text-xs ${isActive ? "font-bold" : ""}`}>{ws.name}</span>
                {isActive && (
                  <div className="ml-auto w-1 h-1 rounded-full bg-cyan-400" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Recent Sessions */}
        {recentSessions && recentSessions.length > 0 && (
          <>
            <p className="text-xs font-mono text-gray-600 uppercase tracking-widest mb-2 px-1 mt-5">Recent</p>
            <div className="space-y-0.5">
              {recentSessions.map((session, i) => (
                <div
                  key={session.id}
                  className="px-3 py-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors group"
                  data-testid={`session-recent-${i + 1}`}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-gray-400 group-hover:text-gray-200 truncate max-w-[120px] font-mono">
                      {session.title}
                    </p>
                    <span className="text-xs text-gray-600 flex-shrink-0 ml-1">
                      {timeAgo(session.lastMessageAt || session.startedAt)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* ── User Profile ─────────────────────────────────── */}
      <div className="p-3 border-t border-white/5">
        <div className="glass-card rounded-lg p-2.5 border border-white/5">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-pink-500 flex items-center justify-center flex-shrink-0">
              <span className="text-white text-xs font-bold" data-testid="user-initials">
                {user ? initials(user.username) : "U"}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-white font-mono truncate" data-testid="user-name">
                {user?.username || "Operator"}
              </p>
              <p className="text-xs text-gray-600 font-mono" data-testid="user-role">
                {user?.role === "owner" ? "Owner" : "Analyst"}
              </p>
            </div>
            <div className={`w-1.5 h-1.5 rounded-full ${emotionalState.bondLevel > 50 ? "bg-green-400" : "bg-cyan-400"} animate-pulse`} />
          </div>

          {/* Bond level */}
          <div className="mb-2">
            <div className="flex justify-between text-xs font-mono text-gray-600 mb-1">
              <span>Bond</span>
              <span data-testid="bond-level" className="text-cyan-400">{emotionalState.bondLevel}%</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-0.5">
              <div
                className="bg-gradient-to-r from-cyan-500 to-green-500 h-0.5 rounded-full transition-all duration-500"
                style={{ width: `${emotionalState.bondLevel}%` }}
              />
            </div>
          </div>

          <button
            onClick={logout}
            className="w-full py-1 text-xs font-mono text-gray-500 hover:text-gray-300 hover:bg-white/5 rounded transition-colors border border-white/5"
            data-testid="button-logout"
          >
            <i className="fas fa-sign-out-alt mr-1" /> Logout
          </button>
        </div>
      </div>
    </div>
  );
}
