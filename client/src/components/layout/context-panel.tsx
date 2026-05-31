import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useEmotionalState } from "@/store/emotional-state";
import { useChat } from "@/store/chat";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

interface Memory {
  id: string;
  type: 'procedural' | 'semantic' | 'episodic' | 'emotional';
  content: {
    summary: string;
  };
  strength: number;
  createdAt: string;
}

interface PendingToolRun {
  id: string;
  toolName: string;
  arguments: any;
  riskLevel: 'low' | 'medium' | 'high';
}

export default function ContextPanel() {
  const [showPanel, setShowPanel] = useState(true);
  const { emotionalState } = useEmotionalState();
  const { currentPlan, sendMessage } = useChat();
  const { toast } = useToast();

  const token = localStorage.getItem('auth_token');

  const { data: memoriesData } = useQuery<Memory[]>({
    queryKey: ["/api/protected/memory"],
    queryFn: () => api.get("/api/protected/memory"),
    enabled: !!token,
    refetchInterval: 30000,
    staleTime: 15000
  });
  const memories = memoriesData ?? [];

  const { data: pendingToolRunsData } = useQuery<PendingToolRun[]>({
    queryKey: ["/api/protected/tools/pending"],
    queryFn: () => api.get("/api/protected/tools/pending"),
    enabled: !!token,
    refetchInterval: 5000,
    staleTime: 2000
  });
  const pendingToolRuns = pendingToolRunsData ?? [];

  const handleQuickAction = async (action: string) => {
    try {
      switch (action) {
        case 'export-chat':
          toast({
            title: "Exporting chat",
            description: "Chat history export will be available soon"
          });
          break;
          
        case 'view-analytics':
          await sendMessage("Show me analytics for my recent cybersecurity activities");
          break;
          
        case 'mitre-map':
          await sendMessage("Generate a MITRE ATT&CK mapping for recent findings");
          break;
          
        case 'auto-report':
          await sendMessage("Create an automated security assessment report");
          break;
          
        default:
          console.log(`Unknown action: ${action}`);
      }
    } catch (error) {
      toast({
        title: "Action failed",
        description: error instanceof Error ? error.message : "An error occurred",
        variant: "destructive"
      });
    }
  };

  const handleFileUpload = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,.md,.txt,.log,.png,.jpg,.jpeg';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', file.name);
        formData.append('tags', JSON.stringify([]));

        await api.uploadFile('/api/protected/rag/ingest', file, {
          title: file.name,
          tags: []
        });
        
        toast({
          title: "Document uploaded",
          description: `${file.name} has been processed and added to the knowledge base`,
        });
      } catch (error) {
        toast({
          title: "Upload failed",
          description: error instanceof Error ? error.message : "Failed to upload document",
          variant: "destructive"
        });
      }
    };
    input.click();
  };

  if (!showPanel) {
    return (
      <div className="w-12 glass border-l border-white/10 flex items-center justify-center">
        <button
          onClick={() => setShowPanel(true)}
          className="p-2 rounded-lg hover:bg-white/5 transition-colors"
          data-testid="button-show-context-panel"
        >
          <i className="fas fa-chevron-left text-gray-400" />
        </button>
      </div>
    );
  }

  return (
    <div className="w-80 glass border-l border-white/10 flex flex-col" data-testid="context-panel">
      {/* Panel Header */}
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Context & Memory</h3>
          <button 
            onClick={() => setShowPanel(false)}
            className="p-1 hover:bg-white/5 rounded transition-colors"
            data-testid="button-close-context-panel"
          >
            <i className="fas fa-times text-gray-400" />
          </button>
        </div>
      </div>

      {/* Upload Section */}
      <div className="p-4 border-b border-white/10">
        <h4 className="text-sm font-medium mb-3">Quick Upload</h4>
        <div className="space-y-2">
          <div 
            onClick={handleFileUpload}
            className="glass rounded-lg p-3 border border-dashed border-white/30 text-center hover:border-cyber-blue/50 transition-colors cursor-pointer"
            data-testid="upload-area"
          >
            <i className="fas fa-cloud-upload-alt text-cyber-blue mb-2" />
            <p className="text-xs text-gray-400">Drop files or click to upload</p>
            <p className="text-xs text-gray-500">PDF, MD, logs, screenshots</p>
          </div>
        </div>
      </div>

      {/* Pending Tool Approvals */}
      {pendingToolRuns && pendingToolRuns.length > 0 && (
        <div className="p-4 border-b border-white/10">
          <h4 className="text-sm font-medium mb-3 text-cyber-amber">
            <i className="fas fa-exclamation-triangle mr-2" />
            Pending Approvals
          </h4>
          <div className="space-y-2">
            {pendingToolRuns.slice(0, 3).map((toolRun) => (
              <div key={toolRun.id} className="glass rounded-lg p-2 border border-cyber-amber/30">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium">{toolRun.toolName}</span>
                  <span className={`px-2 py-1 rounded ${
                    toolRun.riskLevel === 'high' ? 'bg-cyber-red/20 text-cyber-red' :
                    toolRun.riskLevel === 'medium' ? 'bg-cyber-amber/20 text-cyber-amber' :
                    'bg-cyber-green/20 text-cyber-green'
                  }`}>
                    {toolRun.riskLevel}
                  </span>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  {JSON.stringify(toolRun.arguments).substring(0, 50)}...
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Agent Planning */}
      {currentPlan && (
        <div className="p-4 border-b border-white/10">
          <h4 className="text-sm font-medium mb-3">Current Plan</h4>
          <div className="space-y-2">
            <div className="text-xs text-gray-400 mb-2">
              Goal: {currentPlan.goal}
            </div>
            {currentPlan.steps.slice(0, 4).map((step, index) => (
              <div key={step.id} className="flex items-center space-x-2 text-xs">
                <div className={`w-2 h-2 rounded-full ${
                  step.status === 'completed' ? 'bg-cyber-green' :
                  step.status === 'executing' ? 'bg-cyber-blue animate-pulse' :
                  step.status === 'failed' ? 'bg-cyber-red' : 'bg-gray-500'
                }`} />
                <span className={`flex-1 ${
                  step.status === 'completed' ? 'text-gray-300 line-through' : 'text-gray-400'
                }`}>
                  {step.description}
                </span>
                {(step as any).requiresApproval && (
                  <i className="fas fa-exclamation-triangle text-cyber-amber" />
                )}
              </div>
            ))}
            {currentPlan.steps.length > 4 && (
              <div className="text-xs text-gray-500">
                +{currentPlan.steps.length - 4} more steps
              </div>
            )}
          </div>
        </div>
      )}

      {/* Memory Timeline */}
      <div className="flex-1 p-4 overflow-y-auto">
        <h4 className="text-sm font-medium mb-3">Memory & Learning</h4>
        <div className="space-y-3">
          
          {/* Current Emotional State */}
          <div className="glass rounded-lg p-3" data-testid="memory-emotional">
            <div className="flex items-center space-x-2 mb-2">
              <i className="fas fa-heart text-pink-400 text-xs" />
              <span className="text-xs font-medium text-pink-400">Emotional Bond</span>
            </div>
            <p className="text-xs text-gray-300">
              Current mood: {emotionalState.currentMood}. 
              Trust level: {Math.round(emotionalState.trustLevel * 100)}%. 
              Bond strength: {emotionalState.bondLevel}%.
            </p>
            <span className="text-xs text-gray-500">Live</span>
          </div>

          {/* Display recent memories if available */}
          {memories.slice(0, 5).map((memory, index: number) => (
            <div key={memory.id} className="glass rounded-lg p-3" data-testid={`memory-${memory.type}-${index}`}>
              <div className="flex items-center space-x-2 mb-2">
                <i className={`text-xs ${
                  memory.type === 'procedural' ? 'fas fa-cog text-cyber-blue' :
                  memory.type === 'semantic' ? 'fas fa-brain text-cyber-green' :
                  memory.type === 'episodic' ? 'fas fa-history text-cyber-amber' :
                  'fas fa-heart text-pink-400'
                }`} />
                <span className={`text-xs font-medium ${
                  memory.type === 'procedural' ? 'text-cyber-blue' :
                  memory.type === 'semantic' ? 'text-cyber-green' :
                  memory.type === 'episodic' ? 'text-cyber-amber' :
                  'text-pink-400'
                }`}>
                  {memory.type === 'procedural' ? 'Learned Pattern' :
                   memory.type === 'semantic' ? 'Knowledge' :
                   memory.type === 'episodic' ? 'Session Context' :
                   'Emotional Bond'}
                </span>
                <div className="flex-1" />
                <span className="text-xs text-gray-500">
                  Strength: {Math.round((memory.strength || 1) * 100)}%
                </span>
              </div>
              <p className="text-xs text-gray-300">
                {memory.content?.summary || 'Processing memory...'}
              </p>
              <span className="text-xs text-gray-500">
                {new Date(memory.createdAt).toLocaleTimeString()}
              </span>
            </div>
          ))}

          {/* Placeholder if no memories */}
          {(!memories || memories.length === 0) && (
            <div className="glass rounded-lg p-3 text-center">
              <i className="fas fa-brain text-gray-500 mb-2" />
              <p className="text-xs text-gray-400">
                Building memories as we interact...
              </p>
            </div>
          )}

        </div>
      </div>

      {/* Quick Actions */}
      <div className="p-4 border-t border-white/10">
        <h4 className="text-sm font-medium mb-3">Quick Actions</h4>
        <div className="grid grid-cols-2 gap-2">
          <button 
            onClick={() => handleQuickAction('export-chat')}
            className="glass rounded-lg p-2 hover:border-cyber-blue/50 border border-white/20 transition-colors"
            data-testid="action-export-chat"
          >
            <i className="fas fa-file-export text-cyber-blue mb-1" />
            <span className="text-xs block">Export Chat</span>
          </button>
          <button 
            onClick={() => handleQuickAction('view-analytics')}
            className="glass rounded-lg p-2 hover:border-cyber-green/50 border border-white/20 transition-colors"
            data-testid="action-view-analytics"
          >
            <i className="fas fa-chart-line text-cyber-green mb-1" />
            <span className="text-xs block">View Analytics</span>
          </button>
          <button 
            onClick={() => handleQuickAction('mitre-map')}
            className="glass rounded-lg p-2 hover:border-cyber-amber/50 border border-white/20 transition-colors"
            data-testid="action-mitre-map"
          >
            <i className="fas fa-shield-alt text-cyber-amber mb-1" />
            <span className="text-xs block">MITRE Map</span>
          </button>
          <button 
            onClick={() => handleQuickAction('auto-report')}
            className="glass rounded-lg p-2 hover:border-purple-400/50 border border-white/20 transition-colors"
            data-testid="action-auto-report"
          >
            <i className="fas fa-magic text-purple-400 mb-1" />
            <span className="text-xs block">Auto-Report</span>
          </button>
        </div>
      </div>
    </div>
  );
}
