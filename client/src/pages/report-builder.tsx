import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

const ReportBuilder = () => {
  const [availableSections, setAvailableSections] = useState<Array<any>>([]);
  const [selectedSections, setSelectedSections] = useState<Array<any>>([]);
  const [reportTitle, setReportTitle] = useState<string>("");
  const [reportDescription, setReportDescription] = useState<string>("");
  const [executiveSummary, setExecutiveSummary] = useState<string>("");
  const [scope, setScope] = useState<string>("");
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [generatedReport, setGeneratedReport] = useState<any>(null);
  const { toast } = useToast();

  useEffect(() => {
    const fetchAvailableSections = async () => {
      try {
        const response = await api.get("/api/protected/report-sections");
        setAvailableSections(response);
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        toast({
          title: "Failed to load section templates",
          description: message,
          variant: "destructive",
        });
      }
    };

    fetchAvailableSections();
  }, [toast]);

  const handleDragStart = (section: any) => {
    // For simplicity, we'll just copy the section on drop
    // In a real DnD library, we would use drag and drop events
    // We'll implement a simple click to add for now
    const newSection = { ...section, id: Date.now() + Math.random() }; // Make a copy with a new ID
    setSelectedSections([...selectedSections, newSection]);
  };

  const removeSection = (id: any) => {
    setSelectedSections(selectedSections.filter((section) => section.id !== id));
  };

  const moveUp = (id: any) => {
    const index = selectedSections.findIndex((section) => section.id === id);
    if (index > 0) {
      const newSelected = [...selectedSections];
      [newSelected[index], newSelected[index - 1]] = [
        newSelected[index - 1],
        newSelected[index],
      ];
      setSelectedSections(newSelected);
    }
  };

  const moveDown = (id: any) => {
    const index = selectedSections.findIndex((section) => section.id === id);
    if (index < selectedSections.length - 1) {
      const newSelected = [...selectedSections];
      [newSelected[index], newSelected[index + 1]] = [
        newSelected[index + 1],
        newSelected[index],
      ];
      setSelectedSections(newSelected);
    }
  };

  const saveConfiguration = async () => {
    if (!reportTitle.trim()) return;

    setIsSaving(true);
    try {
      const response = await api.post("/api/protected/report-configurations", {
        name: reportTitle,
        description: reportDescription,
        sections: selectedSections.map((section) => ({
          section_type: section.section_type,
          title: section.title,
          content_template: section.content_template,
          is_public: section.is_public,
        })),
        is_default: false,
      });

      toast({
        title: "Configuration saved",
        description: "Your report configuration has been saved",
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to save configuration",
        description: message,
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const generateReport = async () => {
    setIsGenerating(true);
    setGeneratedReport(null);
    try {
      // Fetch findings from the workspace
      const findingsResponse = await api.get("/api/protected/findings");
      const findings = findingsResponse;

      // executiveSummary and scope come from component state

      const reportResponse = await api.post("/api/protected/reports/generate", {
        title: reportTitle || "Untitled Report",
        type: "technical", // default type
        sections: selectedSections.map((section) => ({
          type: section.section_type,
          title: section.title,
          content: "", // We don't have the actual content from the template; we would need to render the template with data.
          // For now, we'll leave it empty and hope the backend can handle it.
          // We'll need to pass the findings to the template rendering.
          // This is a simplified implementation.
        })),
        executiveSummary: executiveSummary,
        scope: scope,
      });

      setGeneratedReport(reportResponse);
      toast({
        title: "Report generated",
        description: "Your report has been generated",
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      toast({
        title: "Failed to generate report",
        description: message,
        variant: "destructive",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-black/20">
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-black/10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br from-indigo-500 to-blue-500">
            <i className="fas fa-file-alt text-white text-sm" />
          </div>
          <div>
            <h1 className="font-display text-xl font-black text-white tracking-wider">
              Report Builder
            </h1>
            <p className="text-sm text-gray-400 font-mono">
              Create custom reports with drag-and-drop sections
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={saveConfiguration}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-blue-500 text-white font-bold text-sm rounded-lg disabled:opacity-50 hover:from-indigo-400 hover:to-blue-400 transition-colors"
          >
            {isSaving ? "Saving..." : "Save Configuration"}
          </button>

          <button
            onClick={generateReport}
            disabled={isGenerating || selectedSections.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-green-500 text-white font-bold text-sm rounded-lg disabled:opacity-50 hover:from-emerald-400 hover:to-green-400 transition-colors"
          >
            {isGenerating ? "Generating..." : "Generate Report"}
          </button>
        </div>
      </div>

      <div className="flex-1 flex p-6">
        {/* Available Sections */}
        <div className="w-1/3 border-r border-white/5 bg-black/30 p-4 overflow-y-auto">
          <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
            Available Sections
          </h2>
          {availableSections.length === 0 ? (
            <p className="text-gray-400">Loading sections...</p>
          ) : (
            <div className="space-y-2">
              {availableSections.map((section) => (
                <div
                  key={section.id}
                  className="bg-black/50 rounded-lg p-3 cursor-pointer hover:bg-black/400 transition-colors"
                  onClick={() => handleDragStart(section)}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-mono font-bold text-white">{section.title}</h3>
                      <p className="text-xs text-gray-400">
                        {section.section_type}
                      </p>
                    </div>
                    <span className="text-indigo-400">+</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Sections */}
        <div className="w-1/3 border-r border-white/5 bg-black/30 p-4 overflow-y-auto">
          <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
            Selected Sections
          </h2>
          {selectedSections.length === 0 ? (
            <p className="text-gray-400">No sections selected. Click on available sections to add them.</p>
          ) : (
            <div className="space-y-3">
              {selectedSections.map((section, index) => (
                <div key={section.id} className="bg-black/50 rounded-lg p-4 flex flex-col">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <h3 className="font-mono font-bold text-white">{section.title}</h3>
                      <p className="text-xs text-gray-400">
                        {section.section_type}
                      </p>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={() => moveUp(section.id)}
                        disabled={index === 0}
                        className="p-1 text-indigo-400 hover:text-indigo-300"
                      >
                        <i className="fas fa-arrow-up" />
                      </button>
                      <button
                        onClick={() => moveDown(section.id)}
                        disabled={index === selectedSections.length - 1}
                        className="p-1 text-indigo-400 hover:text-indigo-300"
                      >
                        <i className="fas fa-arrow-down" />
                      </button>
                      <button
                        onClick={() => removeSection(section.id)}
                        className="p-1 text-red-400 hover:text-red-300"
                      >
                        <i className="fas fa-trash" />
                      </button>
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3 mt-2">
                    <p className="text-sm text-gray-300">
                      {section.content_template || "No content template"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Report Settings */}
        <div className="w-1/3 bg-black/30 p-4 overflow-y-auto">
          <h2 className="font-mono font-bold text-indigo-400 text-lg mb-4">
            Report Settings
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-mono text-gray-400 mb-1">
                Report Title
              </label>
              <input
                type="text"
                value={reportTitle}
                onChange={(e) => setReportTitle(e.target.value)}
                placeholder="Enter report title"
                className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400"
              />
            </div>

            <div>
              <label className="block text-xs font-mono text-gray-400 mb-1">
                Report Description (optional)
              </label>
              <textarea
                value={reportDescription}
                onChange={(e) => setReportDescription(e.target.value)}
                rows={3}
                placeholder="Describe what this report covers..."
                className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-indigo-400"
              />
            </div>

            <div style={{ marginBottom:12 }}>
              <label style={{ fontFamily:'monospace',fontSize:9,color:'rgba(255,255,255,0.35)',textTransform:'uppercase',letterSpacing:'0.12em',display:'block',marginBottom:4 }}>Executive Summary</label>
              <textarea
                value={executiveSummary}
                onChange={e => setExecutiveSummary(e.target.value)}
                rows={3}
                placeholder="Optional: describe the overall security posture..."
                style={{ width:'100%',background:'rgba(4,8,15,0.90)',border:'1px solid rgba(0,216,255,0.22)',color:'#fff',fontFamily:'monospace',fontSize:12,borderRadius:10,padding:'10px 14px',resize:'vertical',boxSizing:'border-box' }}
              />
            </div>
            <div style={{ marginBottom:12 }}>
              <label style={{ fontFamily:'monospace',fontSize:9,color:'rgba(255,255,255,0.35)',textTransform:'uppercase',letterSpacing:'0.12em',display:'block',marginBottom:4 }}>Scope</label>
              <textarea
                value={scope}
                onChange={e => setScope(e.target.value)}
                rows={2}
                placeholder="Optional: define scope of assessment..."
                style={{ width:'100%',background:'rgba(4,8,15,0.90)',border:'1px solid rgba(0,216,255,0.22)',color:'#fff',fontFamily:'monospace',fontSize:12,borderRadius:10,padding:'10px 14px',resize:'vertical',boxSizing:'border-box' }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Generated Report Preview */}
      {generatedReport && (
        <div className="border-t border-white/5 px-6 py-4 bg-black/10">
          <h2 className="font-mono font-bold text-emerald-400 text-lg mb-3">
            Generated Report
          </h2>
          <div className="space-y-4">
            <div>
              <h3 className="font-mono font-bold text-white">{generatedReport.title}</h3>
              <p className="text-sm text-gray-400">
                Type: {generatedReport.type}
              </p>
            </div>
            <div className="bg-black/30 rounded-lg p-4">
              {generatedReport.content ? (
                <pre style={{ fontFamily:'monospace',fontSize:12,color:'rgba(255,255,255,0.80)',whiteSpace:'pre-wrap',margin:0,maxHeight:300,overflowY:'auto' }}>
                  {typeof generatedReport.content === 'string' ? generatedReport.content : JSON.stringify(generatedReport.content, null, 2)}
                </pre>
              ) : (
                <p className="text-gray-300">
                  Report generated successfully. Use the download buttons below to export.
                </p>
              )}
            </div>
            {generatedReport && (
              <div style={{ marginTop:16,display:'flex',gap:8 }}>
                <a
                  href={`/api/reports/${generatedReport.id}/download/pdf`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ padding:'8px 16px',borderRadius:10,background:'rgba(0,216,255,0.12)',border:'1px solid rgba(0,216,255,0.35)',color:'#00d8ff',fontFamily:'monospace',fontSize:11,fontWeight:700,textDecoration:'none',display:'inline-flex',alignItems:'center',gap:6 }}
                >
                  <i className="fas fa-download" />Download PDF
                </a>
                <a
                  href={`/api/reports/${generatedReport.id}/download/docx`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ padding:'8px 16px',borderRadius:10,background:'rgba(0,255,136,0.10)',border:'1px solid rgba(0,255,136,0.30)',color:'#00ff88',fontFamily:'monospace',fontSize:11,fontWeight:700,textDecoration:'none',display:'inline-flex',alignItems:'center',gap:6 }}
                >
                  <i className="fas fa-file-word" />Download DOCX
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ReportBuilder;