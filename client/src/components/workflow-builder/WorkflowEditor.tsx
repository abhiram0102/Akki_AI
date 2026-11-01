import React, { useState, useCallback, useRef, useEffect } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "react-flow";
// import "react-flow/dist/style.css"; // CSS appears to be bundled or not needed in this version
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { motion, type Variants } from "framer-motion";

interface ExecutionResult {
  step_id: string | number;
  agent_type: string;
  output: string;
  status: string;
  timestamp: string | number;
}

const initialElements: any[] = [];

// Node types
const AgentNode = ({
  data,
  id,
  position,
  selected,
  sourcePosition,
  targetPosition,
}: {
  data: { agentType: string; label: string; config: Record<string, any>; status?: 'pending' | 'running' | 'done' | 'error' };
  id: string;
  position: { x: number; y: number };
  selected: boolean;
  sourcePosition: string;
  targetPosition: string;
}) => {
  const { agentType, label, config, status } = data;

  // Agent colors and icons
  const agentStyles: Record<string, { bg: string; color: string; icon: string }> = {
    planner: { bg: "from-cyan-500 to-teal-500", color: "text-cyan-400", icon: "fas fa-network-wired" },
    defender: { bg: "from-blue-500 to-indigo-500", color: "text-blue-400", icon: "fas fa-shield-alt" },
    analyst: { bg: "from-emerald-500 to-green-500", color: "text-emerald-400", icon: "fas fa-search" },
    researcher: { bg: "from-pink-500 to-rose-500", color: "text-pink-400", icon: "fas fa-atom" },
    creator: { bg: "from-amber-500 to-yellow-500", color: "text-amber-400", icon: "fas fa-paint-brush" },
    tutor: { bg: "from-emerald-500 to-green-500", color: "text-emerald-400", icon: "fas fa-user-graduate" },
    coding_assistant: { bg: "from-teal-500 to-cyan-500", color: "text-teal-400", icon: "fas fa-code" },
  };

  const style = agentStyles[agentType] || agentStyles.planner;

  // Node variants for motion
  const nodeVariants: Variants = {
    initial: { scale: 0.95, opacity: 0 },
    animate: { scale: 1, opacity: 1, transition: { type: "spring", stiffness: 300, damping: 20 } },
  };

  return (
    <motion.div
      className={`w-[180px] rounded-xl border-2 ${selected ? "border-indigo-400" : "border-white/20"} bg-black/30 p-4 relative`}
      style={{
        background: `linear-gradient(to bottom right, ${style.bg.replace("from-", "").replace(" to-", ", ")})`,
        borderColor: selected ? "#4f46e5" : "rgba(255, 255, 255, 0.1)"
      }}
      initial="initial"
      animate={selected ? "animate" : "initial"}
      variants={nodeVariants}
    >
      {/* Hover Preview */}
      <div className="absolute bottom-full left-0 right-0 mb-2 rounded-xl p-2 bg-black/80 text-white text-xs pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full flex items-center justify-center bg-white/20">
            <i className={`${style.icon} text-xs ${style.color}`} />
          </div>
          <div>
            <div className="font-mono">{label}</div>
            <div className="text-xs text-gray-300">{agentType}</div>
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full flex items-center justify-center bg-white/20">
            <i className={`${style.icon} text-xs ${style.color}`} />
          </div>
          <div>
            <div className="font-mono font-bold text-white">{label}</div>
            <div className="text-xs text-gray-400">{agentType}</div>
          </div>
        </div>
        <div className="text-xs text-indigo-400">
          ⚙️
        </div>
      </div>

      {/* Config Preview */}
      {Object.keys(config).length > 0 && (
        <div className="text-xs text-gray-400 mb-2">
          <div className="font-mono">Config:</div>
          <div className="space-y-1">
            {Object.entries(config).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span className="text-indigo-400">{key}:</span>
                <span className="text-gray-300">{typeof value === "string" ? value : JSON.stringify(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between text-xs">
        <span style={{ color: status === 'running' ? '#ffb700' : status === 'done' ? '#00ff88' : status === 'error' ? '#ff3868' : 'rgba(155,89,252,0.5)' }}>●</span>
        <span className="text-gray-400">
          {status === 'running' ? 'Running...' : status === 'done' ? 'Done' : status === 'error' ? 'Error' : 'Ready'}
        </span>
      </div>
    </motion.div>
  );
};

// Custom node types
const nodeTypes = {
  agent: AgentNode,
};

export default function WorkflowEditor({ workflowId = null }: { workflowId: string | null }) {
  const [elements, setElements] = useState(initialElements);
  const [workflowName, setWorkflowName] = useState("");
  const [workflowDescription, setWorkflowDescription] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [stepStatuses, setStepStatuses] = useState<Record<string, 'pending' | 'running' | 'done' | 'error'>>({});
  const [executionResults, setExecutionResults] = useState<ExecutionResult[] | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeData, setSelectedNodeData] = useState<any | null>(null);
  const { toast } = useToast();

  const reactFlowRef = useRef(null);
  const { getNodeDistance, fitView } = useReactFlow();

  // Load workflow if ID provided
  useEffect(() => {
    if (workflowId) {
      loadWorkflow(workflowId);
    }
  }, [workflowId]);

  const loadWorkflow = async (id: string) => {
    try {
      const response = await api.get(`/api/protected/workflows/${id}`);
      if (response) {
        setWorkflowName(response.name || "");
        setWorkflowDescription(response.description || "");

        // Convert workflow steps to react-flow elements
        const nodes = (response.steps || []).map((step: any, index: number) => ({
          id: `step-${step.id}`,
          type: "agent",
          position: { x: 100, y: 100 + index * 150 },
          data: {
            agentType: step.agent_type,
            label: step.agent_type.charAt(0).toUpperCase() + step.agent_type.slice(1),
            config: step.config || {},
          },
        }));

        const edges = (response.steps || []).map((step: any, index: number) => {
          if (index > 0) {
            return {
              id: `edge-${index-1}-to-${index}`,
              source: `step-${response.steps[index-1].id}`,
              target: `step-${step.id}`,
              type: "smoothstep",
              animated: true,
              style: { stroke: "#4f46e5", strokeWidth: 2 },
            };
          }
          return null;
        }).filter(Boolean);

        setElements([...nodes, ...edges]);
      }
    } catch (error: unknown) {
      toast({
        title: "Failed to load workflow",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  // Save workflow
  const saveWorkflow = async () => {
    if (!workflowName.trim()) return;

    setIsSaving(true);
    try {
      // Convert elements to workflow steps format
      const steps = elements
        .filter(el => el.type === "agent")
        .map((el, index) => ({
          agent_type: el.data.agentType,
          prompt_template: "", // TODO: Make this configurable
          config: el.data.config,
          step_order: index,
        }));

      const workflowData = {
        name: workflowName,
        description: workflowDescription,
        steps: steps,
      };

      let response;
      if (workflowId) {
        // Update existing workflow
        response = await api.put(`/api/protected/workflows/${workflowId}`, workflowData);
      } else {
        // Create new workflow
        response = await api.post("/api/protected/workflows", workflowData);
      }

      toast({
        title: "Workflow saved",
        description: "Your workflow has been saved successfully",
      });

      // If new workflow, update ID and load it
      if (!workflowId && response.id) {
        // TODO: Update URL or state with new workflow ID
      }
    } catch (error: unknown) {
      toast({
        title: "Failed to save workflow",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Execute workflow
  const executeWorkflow = async () => {
    if (!workflowId) {
      toast({ title: "Save workflow first", description: "Please save the workflow before executing", variant: "destructive" });
      return;
    }

    setIsRunning(true);
    setStepStatuses({});
    // Reset all node statuses to pending
    setElements(els => els.map(el =>
      el.type === 'agent' ? { ...el, data: { ...el.data, status: 'pending' } } : el
    ));

    const sessionId = Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);

    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      const response = await fetch(`/api/protected/workflows/${workflowId}/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ initial_input: '', session_id: sessionId }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }
      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === 'step_start') {
              setStepStatuses(prev => ({ ...prev, [evt.stepId]: 'running' }));
              setElements(els => els.map(el =>
                el.id === `step-${evt.stepId}` ? { ...el, data: { ...el.data, status: 'running' } } : el
              ));
            } else if (evt.type === 'step_done') {
              setStepStatuses(prev => ({ ...prev, [evt.stepId]: 'done' }));
              setElements(els => els.map(el =>
                el.id === `step-${evt.stepId}` ? { ...el, data: { ...el.data, status: 'done' } } : el
              ));
            } else if (evt.type === 'step_error') {
              setStepStatuses(prev => ({ ...prev, [evt.stepId]: 'error' }));
              setElements(els => els.map(el =>
                el.id === `step-${evt.stepId}` ? { ...el, data: { ...el.data, status: 'error' } } : el
              ));
            } else if (evt.type === 'done') {
              setIsRunning(false);
              toast({ title: "Workflow complete", description: `${evt.stepsExecuted ?? ''} step(s) executed` });
            }
          } catch {
            // ignore malformed SSE lines
          }
        }
      }
    } catch (error: unknown) {
      toast({
        title: "Workflow execution failed",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsRunning(false);
    }
  };

  // Add agent node
  const addAgentNode = (agentType: string) => {
    const newNode = {
      id: `agent-${Date.now()}`,
      type: "agent",
      position: { x: 100, y: 100 },
      data: {
        agentType: agentType,
        label: agentType.charAt(0).toUpperCase() + agentType.slice(1),
        config: {},
      },
    };

    setElements((els) => [...els, newNode]);
  };

  // Handle connection
  const onConnect = (connection: { source: string; target: string }) => {
    setElements((els) => {
      // Check if edge already exists
      const exists = els.some(
        (el) => el.id && el.id.startsWith("edge-") && el.source === connection.source && el.target === connection.target
      );

      if (!exists) {
        const newEdge = {
          id: `edge-${Date.now()}`,
          source: connection.source,
          target: connection.target,
          type: "smoothstep",
          animated: true,
          style: { stroke: "#4f46e5", strokeWidth: 2 },
        };
        return [...els, newEdge];
      }
      return els;
    });
  };

  return (
    <ReactFlowProvider>
      <div className="flex-1 flex flex-col bg-black/20">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-black/10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-indigo-500 to-blue-500">
              <i className="fas fa-diagram-project text-white text-sm" />
            </div>
            <div>
              <h1 className="font-display text-xl font-black text-white tracking-wider">
                {workflowId ? "Edit Workflow" : "Create Workflow"}
              </h1>
              <p className="text-sm text-gray-400 font-mono">
                Build custom multi-agent workflows
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={saveWorkflow}
              disabled={isSaving}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-bold text-sm rounded-lg disabled:opacity-50 hover:from-indigo-400 hover:to-blue-400 transition-colors"
            >
              {isSaving ? "Saving..." : "Save Workflow"}
            </button>

            <button
              onClick={executeWorkflow}
              disabled={elements.filter(el => el.type === "agent").length === 0 || isRunning}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-green-500 text-white font-bold text-sm rounded-lg disabled:opacity-50 hover:from-emerald-400 hover:to-green-400 transition-colors"
            >
              {isRunning ? "Executing..." : "Execute Workflow"}
            </button>

              <button
                onClick={() => fitView()}
                className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-white/5 transition-colors"
              >
                <i className="fas fa-expand-arrows-alt text-xs" />
              </button>
            </div>
          </div>
        {/* SSE progress bar — visible while workflow is streaming */}
        {isRunning && (
          <div style={{ position: 'relative', height: '3px', background: 'rgba(0,0,0,0.4)', overflow: 'hidden' }}>
            <motion.div
              style={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                width: '40%',
                background: 'linear-gradient(90deg, #00d8ff, #9b59fc)',
              }}
              animate={{ left: ['-40%', '100%'] }}
              transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
            />
          </div>
        )}

          {/* Workflow Info */}
          <div className="flex-1 px-6 py-4">
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-mono text-gray-400 mb-1">
                  Workflow Name
                </label>
                <input
                  type="text"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  placeholder="Enter workflow name"
                  className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-gray-400 mb-1">
                  Description
                </label>
                <textarea
                  value={workflowDescription}
                  onChange={(e) => setWorkflowDescription(e.target.value)}
                  rows={2}
                  placeholder="Describe what this workflow accomplishes..."
                  className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex">
          {/* Sidebar - Agent Palette */}
          <div className="w-64 border-r border-white/5 bg-black/30 p-4 overflow-y-auto">
            <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
              Agent Library
            </h2>

            <div className="space-y-3">
              {/* Agent Categories */}
              <div className="space-y-4">
                <div className="mb-2">
                  <h3 className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-1">Orchestration</h3>
                  <button
                    onClick={() => addAgentNode("planner")}
                    className="w-full text-left px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <i className="fas fa-network-wired text-indigo-400" />
                    <span>Planner</span>
                  </button>
                </div>

                <div className="mb-2">
                  <h3 className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-1">Analysis</h3>
                  <button
                    onClick={() => addAgentNode("defender")}
                    className="w-full text-left px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <i className="fas fa-shield-alt text-indigo-400" />
                    <span>Defender</span>
                  </button>
                  <button
                    onClick={() => addAgentNode("analyst")}
                    className="w-full text-left px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <i className="fas fa-search text-indigo-400" />
                    <span>Analyst</span>
                  </button>
                  <button
                    onClick={() => addAgentNode("researcher")}
                    className="w-full text-left px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <i className="fas fa-atom text-indigo-400" />
                    <span>Researcher</span>
                  </button>
                </div>

                <div className="mb-2">
                  <h3 className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-1">Creation</h3>
                  <button
                    onClick={() => addAgentNode("creator")}
                    className="w-full text-left px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <i className="fas fa-paint-brush text-indigo-400" />
                    <span>Creator</span>
                  </button>
                  <button
                    onClick={() => addAgentNode("coding_assistant")}
                    className="w-full text-left px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <i className="fas fa-code text-indigo-400" />
                    <span>Coding Assistant</span>
                  </button>
                </div>

                <div className="mb-2">
                  <h3 className="text-xs font-mono text-indigo-400 uppercase tracking-widest mb-1">Guidance</h3>
                  <button
                    onClick={() => addAgentNode("tutor")}
                    className="w-full text-left px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 hover:text-white transition-colors flex items-center gap-2"
                  >
                    <i className="fas fa-user-graduate text-indigo-400" />
                    <span>Tutor</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Workflow Canvas */}
          <div className="flex-1 p-4">
            <div className="bg-black/50 rounded-xl border border-white/5">
              <ReactFlow
                ref={reactFlowRef}
                elements={elements}
                onElementsChange={setElements}
                onConnect={onConnect}
                onInit={setElements}
                nodeTypes={nodeTypes}
                snapToGrid={true}
                snapGrid={[15, 15]}
                defaultPaneSize={1000}
                zoomOnPinch={true}
                zoomOnWheel={true}
                fitView
                minZoom={0.5}
                maxZoom={2}
                allowNewEdges={true}
                edgeTypes={{ smoothstep: "smoothstep" }}
                edgesEditable={true}
                deletionEnabled={true}
                enableContextMenu={false}
                paneActive={false}
                onNodeClick={(params: { node: { id: string; data: { agentType: string; label: string; config: Record<string, any> } } }) => {
                  setSelectedNodeId(params.node.id);
                  setSelectedNodeData(params.node.data);
                }}
                onBackgroundClick={() => {
                  setSelectedNodeId(null);
                  setSelectedNodeData(null);
                }}
                style={{
                  height: "100%",
                  minHeight: "600px"
                }}
                className="w-full h-full"
              >
                {/* Background gradient */}
                <div className="absolute inset-0 pointer-events-none">
                  <div className="absolute inset-0 bg-gradient-to-br from-indigo-950/20 to-black/30" />
                  <div className="absolute inset-0 bg-[url('data:image/svg+xml;utf8,<svg xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20width%3D%2240%22%20height%3D%2240%22%20viewBox%3D%220%200%2040%2040%3E%3Cpath%20d%3D%22M0%2040L40%200M20%200L20%2040M0%2020L40%2020%22%20stroke%3D%22%234f46e5%22%20stroke-width%3D%221%22%20stroke-opacity%3D%220.05%22/%3E%3C/svg%27)'] bg-[size:20px_20px]" />
                </div>
              </ReactFlow>
            </div>
          </div>
        </div>

        {/* Execution Results */}
        {executionResults && (
          <div className="border-t border-white/5 px-6 py-4 bg-black/10">
            <h2 className="font-mono font-bold text-emerald-400 text-lg mb-3">
              Execution Results
            </h2>
            <div className="space-y-3">
              {executionResults?.map((result: ExecutionResult, index: number) => (
                <div key={result.step_id} className="bg-black/30 rounded-xl p-4 border border-white/5">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-full flex items-center justify-center bg-indigo-500/20 text-indigo-400">
                        {index + 1}
                      </div>
                      <div>
                        <h3 className="font-mono font-bold text-white">{result.agent_type}</h3>
                        <p className="text-xs text-gray-400">Step {result.step_id}</p>
                      </div>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs ${result.status === "completed" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                      {result.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="text-sm text-gray-300 mb-2">
                    {result.output}
                  </div>

                  <div className="text-xs text-gray-500 border-t border-white/10 pt-3">
                    Executed at: {new Date(result.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
    </ReactFlowProvider>
  );
}

/* JSX Structure Fixed */

/* JSX Structure Fixed */