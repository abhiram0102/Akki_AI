import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import WorkflowEditor from "@/components/workflow-builder/WorkflowEditor";

interface Workflow {
  id: string;
  name: string;
  description?: string;
  steps?: unknown[];
  created_at: string;
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [workflowName, setWorkflowName] = useState("");
  const [workflowDescription, setWorkflowDescription] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const { toast } = useToast();

  // Fetch workflows
  const loadWorkflows = async () => {
    try {
      setLoading(true);
      const response = await api.get("/api/protected/workflows");
      setWorkflows(Array.isArray(response) ? response : [response]);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to load workflows",
        description: message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Create workflow
  const createWorkflow = async () => {
    if (!workflowName.trim()) return;

    setCreating(true);
    try {
      const response = await api.post("/api/protected/workflows", {
        name: workflowName,
        description: workflowDescription,
      });

      toast({
        title: "Workflow created",
        description: "Your workflow has been created successfully",
      });

      // Reset form
      setWorkflowName("");
      setWorkflowDescription("");
      setShowCreateForm(false);

      // Select the newly created workflow for editing
      setSelectedWorkflowId(response.id);

      // Reload workflows
      await loadWorkflows();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to create workflow",
        description: message,
        variant: "destructive",
      });
    } finally {
      setCreating(false);
    }
  };

  // Delete workflow
  const deleteWorkflow = async (id: string) => {
    try {
      await api.delete(`/api/protected/workflows/${id}`);
      toast({
        title: "Workflow deleted",
        description: "The workflow has been deleted",
      });

      if (selectedWorkflowId === id) {
        setSelectedWorkflowId(null);
      }

      await loadWorkflows();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to delete workflow",
        description: message,
        variant: "destructive",
      });
    }
  };

  // Run workflow
  const runWorkflow = async (workflowId: string) => {
    try {
      await api.post(`/api/protected/workflows/${workflowId}/execute`, {
        initial_input: 'Execute workflow',
      });
      toast({ title: 'Workflow started', description: 'Execution in progress' });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      toast({ title: 'Execution failed', description: msg, variant: 'destructive' });
    }
  };

  // Initial load
  useEffect(() => {
    loadWorkflows();
  }, []);

  return (
    <div className="flex-1 flex min-h-0" style={{ background: "rgba(0,0,0,0.25)" }}>
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <div className="w-80 flex-shrink-0 border-r border-white/5 flex flex-col bg-black/20">

        {/* Sidebar Header */}
        <div className="px-5 pt-5 pb-4 border-b border-white/5">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
                <i className="fas fa-diagram-project text-indigo-400 text-sm" />
              </div>
              <span className="font-mono font-black text-xl text-white tracking-tight">
                Workflow Orchestration
              </span>
            </div>
          </div>
          <p className="text-xs text-gray-500 font-mono mt-1 ml-11">
            Build &amp; automate multi-agent pipelines
          </p>

          {/* New Workflow button */}
          <button
            onClick={() => setShowCreateForm((v) => !v)}
            className="mt-4 w-full bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-mono text-sm px-4 py-2 rounded-xl flex items-center justify-center gap-2 hover:from-indigo-400 hover:to-blue-400 transition-all"
          >
            <i className="fas fa-plus text-xs" />
            New Workflow
          </button>
        </div>

        {/* Create Form (collapsed by default) */}
        {showCreateForm && (
          <div className="mx-4 mt-4 bg-black/30 border border-white/8 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <span className="font-mono font-bold text-indigo-400 text-sm uppercase tracking-widest">
                Create Workflow
              </span>
              <button
                onClick={() => setShowCreateForm(false)}
                className="text-gray-600 hover:text-gray-400 text-xs font-mono transition-colors"
              >
                <i className="fas fa-times" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-mono text-gray-500 mb-1.5">
                  Workflow Name
                </label>
                <input
                  type="text"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  placeholder="e.g. Web App Pentest"
                  className="bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:border-indigo-400/50 focus:outline-none font-mono text-sm w-full transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-gray-500 mb-1.5">
                  Description <span className="text-gray-700">(optional)</span>
                </label>
                <textarea
                  value={workflowDescription}
                  onChange={(e) => setWorkflowDescription(e.target.value)}
                  rows={3}
                  placeholder="What does this workflow accomplish?"
                  className="bg-black/50 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:border-indigo-400/50 focus:outline-none font-mono text-sm w-full transition-colors resize-none"
                />
              </div>

              <button
                onClick={createWorkflow}
                disabled={creating || !workflowName.trim()}
                className="w-full px-4 py-2.5 bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-mono font-bold text-sm rounded-xl disabled:opacity-40 hover:from-indigo-400 hover:to-blue-400 transition-all flex items-center justify-center gap-2"
              >
                {creating ? (
                  <>
                    <i className="fas fa-circle-notch animate-spin text-xs" />
                    Creating...
                  </>
                ) : (
                  <>
                    <i className="fas fa-plus text-xs" />
                    Create Workflow
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Workflow List */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono text-gray-600 uppercase tracking-widest">
              My Workflows
            </span>
            <span className="text-xs font-mono text-gray-700">
              {workflows.length}
            </span>
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <div className="w-8 h-8 rounded-full border-2 border-indigo-400/30 border-t-indigo-400 animate-spin" />
              <p className="text-xs text-gray-600 font-mono">Loading workflows…</p>
            </div>
          ) : workflows.length === 0 ? (
            /* ── Empty State ──────────────────────────────────── */
            <div className="flex flex-col items-center text-center py-10">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mx-auto mb-4 text-indigo-400 text-2xl">
                <i className="fas fa-diagram-project" />
              </div>
              <p className="text-white font-mono font-bold text-lg mb-2">
                No workflows yet
              </p>
              <p className="text-gray-500 text-sm font-mono mb-6 leading-relaxed">
                Create your first workflow to automate multi-agent operations
              </p>
              <button
                onClick={() => setShowCreateForm(true)}
                className="bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-mono text-sm px-4 py-2 rounded-xl flex items-center gap-2 hover:from-indigo-400 hover:to-blue-400 transition-all"
              >
                <i className="fas fa-plus text-xs" />
                Create first workflow
              </button>
            </div>
          ) : (
            /* ── Workflow Cards ───────────────────────────────── */
            <div className="space-y-2">
              {workflows.map((workflow) => {
                const isActive = selectedWorkflowId === workflow.id;
                const stepCount = workflow.steps?.length ?? 0;
                return (
                  <div
                    key={workflow.id}
                    onClick={() => setSelectedWorkflowId(workflow.id)}
                    className={[
                      "bg-black/40 border rounded-2xl p-5 transition-all group cursor-pointer",
                      isActive
                        ? "border-indigo-400/50 bg-indigo-500/5 shadow shadow-indigo-500/15"
                        : "border-white/8 hover:border-indigo-400/30 hover:shadow hover:shadow-indigo-500/10",
                    ].join(" ")}
                  >
                    {/* Card top row */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <h3
                          className={[
                            "font-mono font-bold text-sm truncate transition-colors",
                            isActive
                              ? "text-indigo-300"
                              : "text-white group-hover:text-indigo-300",
                          ].join(" ")}
                        >
                          {workflow.name}
                        </h3>
                        {workflow.description && (
                          <p className="text-xs text-gray-500 font-mono mt-1 line-clamp-2">
                            {workflow.description}
                          </p>
                        )}
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                        <button
                          onClick={(e) => { e.stopPropagation(); runWorkflow(workflow.id); }}
                          style={{ padding:'6px 14px',borderRadius:8,background:'linear-gradient(135deg,#00ff88,#00d8ff)',color:'#04080f',fontFamily:'monospace',fontSize:11,fontWeight:700,cursor:'pointer',border:'none',display:'flex',alignItems:'center',gap:5 }}
                        >
                          <i className="fas fa-play" style={{ fontSize:9 }} />Run
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteWorkflow(workflow.id);
                          }}
                          className="w-6 h-6 flex items-center justify-center rounded-lg text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-all"
                          title="Delete workflow"
                        >
                          <i className="fas fa-trash text-xs" />
                        </button>
                      </div>
                    </div>

                    {/* Card bottom row */}
                    <div className="flex items-center gap-3 mt-3">
                      {/* Step count badge */}
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-mono">
                        <i className="fas fa-layer-group text-[10px]" />
                        {stepCount} {stepCount === 1 ? "step" : "steps"}
                      </span>

                      {/* Status indicator */}
                      <span className="inline-flex items-center gap-1.5 text-xs font-mono text-gray-600">
                        <span
                          className={[
                            "w-1.5 h-1.5 rounded-full",
                            isActive ? "bg-indigo-400 animate-pulse" : "bg-gray-700",
                          ].join(" ")}
                        />
                        {isActive ? (
                          <span className="text-indigo-400">editing</span>
                        ) : (
                          <span>idle</span>
                        )}
                      </span>

                      {/* Date */}
                      <span className="ml-auto text-xs font-mono text-gray-700">
                        {new Date(workflow.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Main Editor Area ──────────────────────────────────────── */}
      <div className="flex-1 flex flex-col bg-black/10 min-w-0">
        {selectedWorkflowId === null ? (
          /* Placeholder when nothing selected */
          <div className="flex-1 flex items-center justify-center p-8">
            <div className="text-center max-w-sm">
              <div className="w-20 h-20 rounded-3xl bg-indigo-500/8 border border-indigo-500/15 flex items-center justify-center mx-auto mb-6">
                <i className="fas fa-diagram-project text-indigo-400/50 text-3xl" />
              </div>
              <p className="text-white font-mono font-bold text-lg mb-2">
                No workflow selected
              </p>
              <p className="text-sm text-gray-600 font-mono leading-relaxed">
                Select a workflow from the sidebar to open the editor, or create a new one to get started.
              </p>
              <button
                onClick={() => setShowCreateForm(true)}
                className="mt-6 bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-mono text-sm px-5 py-2.5 rounded-xl flex items-center gap-2 mx-auto hover:from-indigo-400 hover:to-blue-400 transition-all"
              >
                <i className="fas fa-plus text-xs" />
                New Workflow
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0 p-4">
            {/* Back button */}
            <button
              onClick={() => setSelectedWorkflowId(null)}
              className="text-gray-400 hover:text-white flex items-center gap-2 text-sm font-mono mb-4 w-fit transition-colors group"
            >
              <i className="fas fa-chevron-left text-xs group-hover:-translate-x-0.5 transition-transform" />
              Back to workflows
            </button>

            {/* Editor container */}
            <div className="flex-1 rounded-2xl border border-white/8 overflow-hidden bg-black/20 min-h-0">
              <WorkflowEditor workflowId={selectedWorkflowId} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
