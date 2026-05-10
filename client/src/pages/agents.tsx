import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { useChat } from "@/store/chat";

interface Agent {
  id: string;
  name: string;
  role: string;
  color: string;
  status: string;
  description: string;
}

const AGENT_DETAILS: Record<string, {
  icon: string;
  borderColor: string;
  bgColor: string;
  textColor: string;
  capabilities: string[];
  tools: string[];
}> = {
  planner:  {
    icon: "fas fa-network-wired",
    borderColor: "border-cyan-400/40",
    bgColor: "bg-cyan-400/5",
    textColor: "text-cyan-400",
    capabilities: ["Task decomposition", "Agent orchestration", "Strategic planning", "Risk assessment", "Multi-agent coordination"],
    tools: ["All tools", "Agent routing", "Plan generation"],
  },
  recon: {
    icon: "fas fa-satellite-dish",
    borderColor: "border-green-400/40",
    bgColor: "bg-green-400/5",
    textColor: "text-green-400",
    capabilities: ["OSINT gathering", "DNS enumeration", "Subdomain discovery", "WHOIS analysis", "Google dorking", "GitHub intelligence"],
    tools: ["dns_lookup", "whois", "subdomain_enum", "http_probe", "ssl_analyze"],
  },
  exploit: {
    icon: "fas fa-bug",
    borderColor: "border-red-400/40",
    bgColor: "bg-red-400/5",
    textColor: "text-red-400",
    capabilities: ["CVE analysis", "Exploit generation", "Payload crafting", "MITRE mapping", "Vulnerability chains", "PoC development"],
    tools: ["http_probe", "port_scan"],
  },
  defense: {
    icon: "fas fa-shield-alt",
    borderColor: "border-blue-400/40",
    bgColor: "bg-blue-400/5",
    textColor: "text-blue-400",
    capabilities: ["Detection rules", "SIEM queries", "Hardening guidance", "YARA rules", "Sigma rules", "Incident response"],
    tools: ["ssl_analyze", "http_probe"],
  },
  malware: {
    icon: "fas fa-biohazard",
    borderColor: "border-amber-400/40",
    bgColor: "bg-amber-400/5",
    textColor: "text-amber-400",
    capabilities: ["Static analysis", "Dynamic analysis", "IOC extraction", "YARA generation", "Reverse engineering", "Persistence analysis"],
    tools: [],
  },
  tutor: {
    icon: "fas fa-graduation-cap",
    borderColor: "border-emerald-400/40",
    bgColor: "bg-emerald-400/5",
    textColor: "text-emerald-400",
    capabilities: ["Adaptive teaching", "Quiz generation", "Lab creation", "Cert prep", "Interview training", "Challenge design"],
    tools: [],
  },
  memory: {
    icon: "fas fa-database",
    borderColor: "border-purple-400/40",
    bgColor: "bg-purple-400/5",
    textColor: "text-purple-400",
    capabilities: ["Semantic search", "Context recall", "Knowledge synthesis", "Pattern recognition", "Session tracking"],
    tools: [],
  },
};

const DEMO_TOOL_QUERIES: Record<string, { tool: string; params: any; label: string }[]> = {
  recon: [
    { tool: "dns_lookup", params: { domain: "google.com" }, label: "DNS: google.com" },
    { tool: "subdomain_enum", params: { domain: "github.com" }, label: "Subdomains: github.com" },
    { tool: "http_probe", params: { url: "https://example.com" }, label: "HTTP: example.com" },
  ],
};

export default function AgentsPage() {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [toolQuery, setToolQuery] = useState("");
  const [toolTarget, setToolTarget] = useState("");
  const [selectedTool, setSelectedTool] = useState("dns_lookup");
  const [toolResult, setToolResult] = useState<any>(null);
  const { toast } = useToast();
  const { sendMessage } = useChat();

  const { data: agents, isLoading } = useQuery<Agent[]>({
    queryKey: ["/api/agents"],
  });

  const toolMutation = useMutation({
    mutationFn: (data: { toolName: string; params: any }) =>
      apiRequest("POST", "/api/tools/execute", data),
    onSuccess: (data) => {
      setToolResult(data);
      toast({ title: "Tool executed", description: `${selectedTool} completed successfully` });
    },
    onError: (error: Error) => {
      toast({ title: "Tool failed", description: error.message, variant: "destructive" });
    },
  });

  const TOOLS = [
    { id: "dns_lookup", label: "DNS Lookup", placeholder: "domain.com", paramKey: "domain" },
    { id: "whois", label: "WHOIS", placeholder: "domain.com or IP", paramKey: "target" },
    { id: "http_probe", label: "HTTP Probe", placeholder: "https://example.com", paramKey: "url" },
    { id: "port_scan", label: "Port Scan", placeholder: "hostname or IP", paramKey: "host" },
    { id: "subdomain_enum", label: "Subdomain Enum", placeholder: "domain.com", paramKey: "domain" },
    { id: "ssl_analyze", label: "SSL Analyze", placeholder: "domain.com", paramKey: "host" },
  ];

  const currentTool = TOOLS.find(t => t.id === selectedTool)!;

  const handleExecute = () => {
    if (!toolTarget.trim()) return;
    const params: any = {};
    params[currentTool.paramKey] = toolTarget.trim();
    toolMutation.mutate({ toolName: selectedTool, params });
  };

  const handleChatWithAgent = async (agentId: string, question: string) => {
    await sendMessage(`[Agent: ${agentId}] ${question}`, { useStream: true });
    toast({ title: `Message sent to ${agentId}`, description: "Check the Chat workspace for the response" });
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-black/20">
      {/* Header */}
      <div className="border-b border-white/5 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center">
            <i className="fas fa-robot text-white text-sm" />
          </div>
          <div>
            <h2 className="font-display text-base font-black text-white tracking-wider">AGENT NETWORK</h2>
            <p className="text-xs text-gray-500 font-mono">7 Specialist Agents · Real Tool Execution</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
          <span className="text-xs font-mono text-gray-500">{isLoading ? "..." : `${agents?.length || 0} AGENTS ONLINE`}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-5xl mx-auto space-y-6">
          {/* Agent grid */}
          <div>
            <h3 className="text-xs font-mono text-gray-500 uppercase tracking-widest mb-3">Specialist Agents</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {isLoading ? (
                Array(7).fill(0).map((_, i) => (
                  <div key={i} className="glass-card rounded-xl border border-white/5 p-4 animate-pulse">
                    <div className="w-8 h-8 bg-gray-700 rounded-lg mb-3" />
                    <div className="h-3 bg-gray-700 rounded mb-2 w-2/3" />
                    <div className="h-2 bg-gray-800 rounded w-full" />
                  </div>
                ))
              ) : (
                agents?.map(agent => {
                  const detail = AGENT_DETAILS[agent.id] || AGENT_DETAILS.planner;
                  const isSelected = selectedAgent === agent.id;
                  return (
                    <button
                      key={agent.id}
                      onClick={() => setSelectedAgent(isSelected ? null : agent.id)}
                      className={`glass-card rounded-xl border p-4 text-left transition-all hover:scale-[1.02] ${
                        isSelected ? `${detail.borderColor} ${detail.bgColor}` : "border-white/10 hover:border-white/20"
                      }`}
                    >
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 border ${detail.borderColor} ${detail.bgColor}`}>
                        <i className={`${detail.icon} text-sm ${detail.textColor}`} />
                      </div>
                      <p className={`font-mono font-black text-sm ${isSelected ? detail.textColor : "text-white"}`}>{agent.name}</p>
                      <p className="text-xs text-gray-500 mt-0.5 leading-tight">{agent.role}</p>
                      <div className={`mt-2 flex items-center gap-1 text-xs font-mono ${isSelected ? detail.textColor : "text-gray-600"}`}>
                        <div className="w-1.5 h-1.5 bg-green-400 rounded-full" />
                        {agent.status}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Agent detail panel */}
          {selectedAgent && (() => {
            const agent = agents?.find(a => a.id === selectedAgent);
            const detail = AGENT_DETAILS[selectedAgent] || AGENT_DETAILS.planner;
            if (!agent) return null;
            return (
              <div className={`glass-card rounded-xl border ${detail.borderColor} p-5 animate-slide-in-up`}>
                <div className="flex items-center gap-3 mb-4">
                  <div className={`w-10 h-10 rounded-xl border ${detail.borderColor} ${detail.bgColor} flex items-center justify-center`}>
                    <i className={`${detail.icon} ${detail.textColor}`} />
                  </div>
                  <div>
                    <h3 className={`font-mono font-black text-base ${detail.textColor}`}>{agent.name}</h3>
                    <p className="text-xs text-gray-400">{agent.role}</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className={`text-xs font-mono ${detail.textColor} font-bold mb-2`}>CAPABILITIES</p>
                    <div className="space-y-1">
                      {detail.capabilities.map(cap => (
                        <div key={cap} className="flex items-center gap-2 text-xs font-mono text-gray-400">
                          <span className={`text-xs ${detail.textColor}`}>▸</span>
                          {cap}
                        </div>
                      ))}
                    </div>
                  </div>
                  {detail.tools.length > 0 && (
                    <div>
                      <p className={`text-xs font-mono ${detail.textColor} font-bold mb-2`}>LIVE TOOLS</p>
                      <div className="flex flex-wrap gap-1.5">
                        {detail.tools.map(tool => (
                          <span key={tool} className={`text-xs font-mono px-2 py-0.5 rounded border ${detail.borderColor} ${detail.bgColor} ${detail.textColor}`}>
                            {tool}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-4 flex gap-2 flex-wrap">
                  <button
                    onClick={() => handleChatWithAgent(selectedAgent, `Tell me about your capabilities and how you can help with ${agent.role.toLowerCase()}`)}
                    className={`px-3 py-1.5 text-xs font-mono font-bold border ${detail.borderColor} ${detail.bgColor} ${detail.textColor} rounded-lg hover:opacity-80 transition-opacity`}
                  >
                    <i className="fas fa-comments mr-1" /> Chat with {agent.name}
                  </button>
                  {DEMO_TOOL_QUERIES[selectedAgent]?.map(q => (
                    <button
                      key={q.label}
                      onClick={() => { setSelectedTool(q.tool); setToolTarget(Object.values(q.params)[0] as string); toolMutation.mutate({ toolName: q.tool, params: q.params }); }}
                      className="px-3 py-1.5 text-xs font-mono font-bold border border-white/10 text-gray-400 rounded-lg hover:border-white/20 hover:text-gray-300 transition-colors"
                    >
                      <i className="fas fa-play mr-1" /> {q.label}
                    </button>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Tool Execution Console */}
          <div className="glass-card rounded-xl border border-white/10 p-5">
            <h3 className="font-mono font-bold text-white text-sm mb-4 flex items-center gap-2">
              <i className="fas fa-terminal text-cyan-400" />
              Live Tool Execution Console
              <span className="ml-auto text-xs text-gray-500 font-normal">Real execution on target</span>
            </h3>

            <div className="flex gap-3 mb-4 flex-wrap">
              <div className="flex gap-1 flex-wrap">
                {TOOLS.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setSelectedTool(t.id)}
                    className={`px-3 py-1.5 text-xs font-mono rounded-lg border transition-colors ${
                      selectedTool === t.id
                        ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-400"
                        : "border-white/10 text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <input
                value={toolTarget}
                onChange={e => setToolTarget(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleExecute()}
                placeholder={currentTool?.placeholder}
                className="flex-1 bg-black/50 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 font-mono focus:border-cyan-400/40 focus:outline-none"
              />
              <button
                onClick={handleExecute}
                disabled={!toolTarget.trim() || toolMutation.isPending}
                className="px-4 py-2 bg-gradient-to-r from-cyan-500 to-blue-500 text-black font-bold text-xs font-mono rounded-lg disabled:opacity-40 flex items-center gap-2"
              >
                {toolMutation.isPending ? (
                  <div className="w-3 h-3 border border-black/40 border-t-black rounded-full animate-spin" />
                ) : (
                  <i className="fas fa-play" />
                )}
                Execute
              </button>
            </div>

            {/* Tool Result */}
            {(toolMutation.isPending || toolResult) && (
              <div className="mt-4 bg-black/60 rounded-lg border border-cyan-400/20 overflow-hidden">
                <div className="flex items-center gap-2 px-3 py-2 border-b border-cyan-400/10 bg-black/40">
                  <div className={`w-2 h-2 rounded-full ${toolMutation.isPending ? "bg-amber-400 animate-pulse" : "bg-green-400"}`} />
                  <span className="text-xs font-mono text-cyan-400 font-bold">{selectedTool}</span>
                  {!toolMutation.isPending && toolResult && (
                    <span className="text-xs font-mono text-gray-500 ml-auto">
                      {toolResult.result?.elapsed ? `${toolResult.result.elapsed}s` : ""}
                    </span>
                  )}
                </div>
                {toolMutation.isPending ? (
                  <div className="p-4 text-xs text-green-400 font-mono animate-pulse">
                    <i className="fas fa-circle-notch fa-spin mr-2" />
                    Executing {selectedTool}...
                  </div>
                ) : (
                  <pre className="p-4 text-xs text-green-400 font-mono overflow-x-auto max-h-64 overflow-y-auto leading-relaxed">
                    {JSON.stringify(toolResult, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
