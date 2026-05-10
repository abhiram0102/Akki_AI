import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useChat, type Message, type AgentInfo } from "@/store/chat";
import { useAuth } from "@/lib/auth";
import MessageInput from "./message-input";
import { Button } from "@/components/ui/button";

// ── Agent badge configuration ─────────────────────────────────────────────────
const AGENT_STYLES: Record<string, { border: string; glow: string; bg: string; dot: string }> = {
  planner:  { border: "border-cyan-400/40",   glow: "shadow-cyan-400/20",  bg: "bg-cyan-400/10",   dot: "bg-cyan-400" },
  recon:    { border: "border-green-400/40",  glow: "shadow-green-400/20", bg: "bg-green-400/10",  dot: "bg-green-400" },
  exploit:  { border: "border-red-400/40",    glow: "shadow-red-400/20",   bg: "bg-red-400/10",    dot: "bg-red-400" },
  defense:  { border: "border-blue-400/40",   glow: "shadow-blue-400/20",  bg: "bg-blue-400/10",   dot: "bg-blue-400" },
  malware:  { border: "border-amber-400/40",  glow: "shadow-amber-400/20", bg: "bg-amber-400/10",  dot: "bg-amber-400" },
  tutor:    { border: "border-emerald-400/40",glow: "shadow-emerald-400/20",bg:"bg-emerald-400/10",dot: "bg-emerald-400" },
  memory:   { border: "border-purple-400/40", glow: "shadow-purple-400/20",bg: "bg-purple-400/10", dot: "bg-purple-400" },
};

const AGENT_ICONS: Record<string, string> = {
  planner: "fas fa-network-wired",
  recon:   "fas fa-search",
  exploit: "fas fa-bug",
  defense: "fas fa-shield-alt",
  malware: "fas fa-biohazard",
  tutor:   "fas fa-graduation-cap",
  memory:  "fas fa-database",
};

// ── Helper: render markdown-ish text ─────────────────────────────────────────
function renderContent(text: string) {
  if (!text) return null;

  // Split into lines and process
  const lines = text.split("\n");
  const elements: JSX.Element[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <div key={i} className="my-3 rounded-md overflow-hidden border border-cyan-400/20">
          {lang && (
            <div className="bg-black/50 px-3 py-1 text-xs font-mono text-cyan-400/70 border-b border-cyan-400/20 flex items-center justify-between">
              <span>{lang}</span>
              <i className="fas fa-code text-xs opacity-50" />
            </div>
          )}
          <pre className="bg-black/40 px-4 py-3 overflow-x-auto text-sm font-mono text-green-400 leading-relaxed">
            <code>{codeLines.join("\n")}</code>
          </pre>
        </div>
      );
      i++;
      continue;
    }

    // Heading
    if (line.startsWith("### ")) {
      elements.push(<h3 key={i} className="text-sm font-bold text-cyan-300 font-mono mt-3 mb-1">{line.slice(4)}</h3>);
    } else if (line.startsWith("## ")) {
      elements.push(
        <h2 key={i} className="text-sm font-bold text-cyan-400 font-mono mt-4 mb-2 border-b border-cyan-400/20 pb-1 uppercase tracking-wide">
          {line.slice(3)}
        </h2>
      );
    } else if (line.startsWith("# ")) {
      elements.push(<h1 key={i} className="text-base font-bold text-cyan-300 font-mono mt-3 mb-2">{line.slice(2)}</h1>);
    }
    // Blockquote
    else if (line.startsWith("> ")) {
      elements.push(
        <div key={i} className="border-l-2 border-cyan-400/50 pl-3 my-1 text-gray-400 italic text-sm">
          {line.slice(2)}
        </div>
      );
    }
    // Bullet list
    else if (line.startsWith("- ") || line.startsWith("* ")) {
      elements.push(
        <div key={i} className="flex items-start gap-2 my-0.5 text-sm">
          <span className="text-cyan-400 mt-1 text-xs">▸</span>
          <span className="text-gray-200">{formatInline(line.slice(2))}</span>
        </div>
      );
    }
    // Numbered list
    else if (/^\d+\.\s/.test(line)) {
      const num = line.match(/^(\d+)\.\s/)?.[1] || "1";
      elements.push(
        <div key={i} className="flex items-start gap-2 my-0.5 text-sm">
          <span className="text-cyan-400 font-mono text-xs mt-1 min-w-[18px]">{num}.</span>
          <span className="text-gray-200">{formatInline(line.replace(/^\d+\.\s/, ""))}</span>
        </div>
      );
    }
    // Bold header line (like "**Section:**")
    else if (line.startsWith("**") && line.endsWith("**")) {
      elements.push(
        <p key={i} className="font-bold text-white text-sm mt-2 mb-1 font-mono">
          {line.slice(2, -2)}
        </p>
      );
    }
    // Horizontal rule
    else if (line === "---" || line === "===") {
      elements.push(<hr key={i} className="border-cyan-400/20 my-3" />);
    }
    // Empty line
    else if (line.trim() === "") {
      elements.push(<div key={i} className="h-1" />);
    }
    // Normal text
    else {
      elements.push(
        <p key={i} className="text-sm text-gray-200 leading-relaxed my-0.5">
          {formatInline(line)}
        </p>
      );
    }
    i++;
  }

  return <>{elements}</>;
}

function formatInline(text: string): React.ReactNode {
  // Handle **bold**, `code`, and plain text
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={i} className="bg-cyan-400/10 border border-cyan-400/20 text-green-400 font-mono text-xs px-1.5 py-0.5 rounded">
              {part.slice(1, -1)}
            </code>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

// ── Welcome Screen ─────────────────────────────────────────────────────────────
const WelcomeScreen = () => (
  <div className="flex items-center justify-center h-full">
    <div className="text-center max-w-lg px-6">
      {/* Animated logo */}
      <div className="relative mb-8">
        <div className="w-20 h-20 mx-auto rounded-full bg-gradient-to-br from-cyan-500 to-green-500 flex items-center justify-center animate-pulse shadow-lg shadow-cyan-500/30">
          <i className="fas fa-brain text-black text-3xl" />
        </div>
        <div className="absolute -inset-3 rounded-full border border-cyan-400/20 animate-ping" style={{ animationDuration: "3s" }} />
      </div>

      <h2 className="font-display text-2xl font-black text-white mb-1 tracking-wider">
        AKKI AI
      </h2>
      <p className="text-cyan-400 font-mono text-xs tracking-widest uppercase mb-6">
        Autonomous Cybersecurity Operating System
      </p>

      {/* Agent grid */}
      <div className="grid grid-cols-4 gap-2 mb-6">
        {[
          { id: "planner", name: "NEXUS", icon: "fas fa-network-wired", desc: "Orchestrator" },
          { id: "recon",   name: "GHOST", icon: "fas fa-search",        desc: "OSINT" },
          { id: "exploit", name: "PHANTOM",icon: "fas fa-bug",          desc: "Exploit" },
          { id: "defense", name: "SENTINEL",icon: "fas fa-shield-alt",  desc: "Defense" },
          { id: "malware", name: "DISSECT",icon: "fas fa-biohazard",    desc: "Malware" },
          { id: "tutor",   name: "MENTOR", icon: "fas fa-graduation-cap",desc: "Tutor" },
          { id: "memory",  name: "ARCHIVE",icon: "fas fa-database",     desc: "Memory" },
          { id: "live",    name: "TOOLS",  icon: "fas fa-terminal",     desc: "Live Tools" },
        ].map((agent) => {
          const style = AGENT_STYLES[agent.id] || AGENT_STYLES.planner;
          return (
            <div key={agent.id} className={`glass-card rounded-lg p-2 border ${style.border} text-center`}>
              <i className={`${agent.icon} text-sm mb-1 block`} style={{ color: "var(--cyber-blue)" }} />
              <p className="text-xs font-mono text-white font-bold leading-none">{agent.name}</p>
              <p className="text-xs text-gray-500 mt-0.5">{agent.desc}</p>
            </div>
          );
        })}
      </div>

      <p className="text-gray-500 text-sm font-mono">
        Ask anything — AKKI routes your query to the right specialist agent automatically.
      </p>
      <div className="mt-4 text-xs text-gray-600 font-mono space-y-1">
        <p>Try: <span className="text-cyan-400">"DNS lookup for google.com"</span></p>
        <p>Try: <span className="text-green-400">"Explain SQL injection step by step"</span></p>
        <p>Try: <span className="text-red-400">"What is Kerberoasting?"</span></p>
      </div>
    </div>
  </div>
);

// ── Agent Badge ────────────────────────────────────────────────────────────────
const AgentBadge = ({ agentInfo }: { agentInfo: AgentInfo }) => {
  const style = AGENT_STYLES[agentInfo.agent] || AGENT_STYLES.planner;
  const icon = AGENT_ICONS[agentInfo.agent] || "fas fa-robot";
  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono border ${style.border} ${style.bg} mb-2`}>
      <div className={`w-1.5 h-1.5 rounded-full ${style.dot} animate-pulse`} />
      <i className={`${icon} text-xs`} />
      <span className="font-bold tracking-wide">{agentInfo.agentName}</span>
      <span className="text-gray-500">·</span>
      <span className="text-gray-400">{agentInfo.agentRole}</span>
    </div>
  );
};

// ── Tool Call Display ──────────────────────────────────────────────────────────
const ToolCallDisplay = ({ toolCalls }: { toolCalls: any[] }) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      {toolCalls.map((tc) => (
        <div key={tc.id} className="tool-panel rounded-md overflow-hidden">
          <div
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-cyan-400/5 transition-colors"
            onClick={() => setExpanded(p => ({ ...p, [tc.id]: !p[tc.id] }))}
          >
            <div className={`w-2 h-2 rounded-full ${tc.status === "success" ? "bg-green-400" : tc.status === "running" ? "bg-yellow-400 animate-pulse" : "bg-red-400"}`} />
            <i className="fas fa-terminal text-cyan-400 text-xs" />
            <span className="text-cyan-300 text-xs font-mono font-bold">{tc.name}</span>
            <span className="text-gray-500 text-xs">·</span>
            <span className="text-gray-400 text-xs">{tc.displayName || tc.name}</span>
            <span className="ml-auto text-gray-600 text-xs">
              <i className={`fas fa-chevron-${expanded[tc.id] ? "up" : "down"}`} />
            </span>
          </div>
          {expanded[tc.id] && tc.result && (
            <div className="px-3 pb-3">
              <pre className="text-xs text-green-400 font-mono overflow-x-auto bg-black/30 rounded p-2 max-h-48 overflow-y-auto">
                {JSON.stringify(tc.result?.result || tc.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

// ── Chat Message ───────────────────────────────────────────────────────────────
const ChatMessage = ({ message }: { message: Message }) => {
  const { user } = useAuth();

  const timeAgo = (d: string) => {
    const diff = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  if (message.role === "assistant") {
    const agentStyle = AGENT_STYLES[message.agentInfo?.agent || "planner"] || AGENT_STYLES.planner;
    const agentIcon = AGENT_ICONS[message.agentInfo?.agent || "planner"] || "fas fa-brain";

    return (
      <div className="flex gap-3 animate-slide-in-up group">
        {/* Agent avatar */}
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border ${agentStyle.border} ${agentStyle.bg} shadow-sm`}>
          <i className={`${agentIcon} text-xs`} style={{ color: "var(--cyber-blue)" }} />
        </div>

        <div className="flex-1 min-w-0">
          {/* Agent badge */}
          {message.agentInfo && <AgentBadge agentInfo={message.agentInfo} />}

          {/* Message bubble */}
          <div className={`glass-card rounded-xl rounded-tl-sm p-4 border ${agentStyle.border} shadow-sm ${agentStyle.glow} relative overflow-hidden`}>
            {/* Top scanline */}
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent" />

            {/* Content */}
            <div className="prose-cyber">
              {message.isStreaming && !message.content ? (
                <div className="flex items-center gap-2 text-cyan-400 text-sm font-mono">
                  <div className="flex gap-1">
                    {[0, 1, 2].map(i => (
                      <div key={i} className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }} />
                    ))}
                  </div>
                  <span className="text-xs opacity-70">Processing...</span>
                </div>
              ) : (
                <>
                  {renderContent(message.content)}
                  {message.isStreaming && (
                    <span className="inline-block w-0.5 h-4 bg-cyan-400 ml-0.5 animate-pulse align-middle" />
                  )}
                </>
              )}
            </div>

            {/* Tool calls */}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <ToolCallDisplay toolCalls={message.toolCalls} />
            )}
          </div>

          <div className="text-xs text-gray-600 mt-1 ml-1 font-mono">
            {timeAgo(message.createdAt)}
          </div>
        </div>
      </div>
    );
  }

  // User message
  return (
    <div className="flex gap-3 justify-end animate-slide-in-up">
      <div className="flex-1 max-w-2xl">
        <div className="glass rounded-xl rounded-tr-sm p-4 border border-white/10 ml-12">
          <p className="text-sm text-gray-100 leading-relaxed">{message.content}</p>
          <div className="text-xs text-gray-600 mt-2 text-right font-mono">
            {timeAgo(message.createdAt)}
          </div>
        </div>
      </div>
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-pink-500 flex items-center justify-center flex-shrink-0">
        <span className="text-white text-xs font-bold">
          {user ? user.username.charAt(0).toUpperCase() : "U"}
        </span>
      </div>
    </div>
  );
};

// ── Main Chat Interface ────────────────────────────────────────────────────────
interface ChatInterfaceProps {
  onInitAudio: () => void;
  audioInitialized: boolean;
  audioContext: AudioContext | null;
}

export default function ChatInterface({ onInitAudio, audioInitialized, audioContext }: ChatInterfaceProps) {
  const { currentSessionId, messages, isLoading, isStreaming } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { data: sessionMessages, isLoading: sessLoading } = useQuery({
    queryKey: ["/api/protected/sessions", currentSessionId, "messages"],
    enabled: !!currentSessionId && !!localStorage.getItem("auth_token"),
    refetchInterval: isStreaming ? false : 3000,
    staleTime: 1000,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sessionMessages, messages]);

  const allMessages: Message[] = messages.length > 0
    ? messages
    : (Array.isArray(sessionMessages) ? sessionMessages : []);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
        {sessLoading && currentSessionId && messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin mx-auto mb-3" />
              <p className="text-gray-500 text-sm font-mono">Loading session...</p>
            </div>
          </div>
        ) : allMessages.length === 0 ? (
          <WelcomeScreen />
        ) : (
          allMessages.map((msg: Message) => (
            <ChatMessage key={msg.id} message={msg} />
          ))
        )}

        {/* Loading pulse when waiting for response */}
        {(isLoading && !isStreaming) && (
          <div className="flex gap-3 animate-fade-in">
            <div className="w-8 h-8 rounded-lg glass-card border border-cyan-400/20 flex items-center justify-center">
              <i className="fas fa-network-wired text-xs text-cyan-400" />
            </div>
            <div className="glass-card rounded-xl rounded-tl-sm p-4 border border-cyan-400/20">
              <div className="flex items-center gap-2 text-cyan-400">
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div key={i} className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
                </div>
                <span className="text-xs font-mono opacity-70">AKKI is thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <MessageInput audioInitialized={audioInitialized} audioContext={audioContext} />
    </div>
  );
}
