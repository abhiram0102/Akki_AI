import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { FileText, Download, BarChart3, Target, Shield, Calendar } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";

interface SecurityReport {
  id: string;
  title: string;
  type: "executive" | "technical" | "compliance" | "penetration";
  status: "generating" | "completed" | "failed";
  progress: number;
  findings: Array<{
    id: string;
    title: string;
    severity: "critical" | "high" | "medium" | "low";
    category: string;
    description: string;
    recommendation: string;
    mitreTechnique?: string;
    cvss?: number;
  }>;
  summary: {
    totalFindings: number;
    criticalCount: number;
    highCount: number;
    mediumCount: number;
    lowCount: number;
    overallRisk: "critical" | "high" | "medium" | "low";
  };
  mitreMapping: Array<{
    tactic: string;
    techniques: string[];
  }>;
  recommendations: string[];
  executiveSummary: string;
  technicalDetails: string;
  createdAt: string;
  updatedAt: string;
}

interface ReportTemplate {
  id: string;
  name: string;
  type: string;
  description: string;
  sections: string[];
  customizable: boolean;
}

export default function ReportsPage() {
  const [reportTitle, setReportTitle] = useState("");
  const [reportType, setReportType] = useState("technical");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [customSections, setCustomSections] = useState("");
  const [activeTab, setActiveTab] = useState("generate");
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Fetch reports
  const { data: reports, isLoading: reportsLoading } = useQuery({
    queryKey: ["/api/reports"],
    enabled: true,
  });

  // Fetch report templates
  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ["/api/reports/templates"],
    enabled: true,
  });

  // Fetch findings for report generation
  const { data: availableFindings, isLoading: findingsLoading } = useQuery({
    queryKey: ["/api/findings"],
    enabled: true,
  });

  // Generate report mutation
  const generateReportMutation = useMutation({
    mutationFn: (data: { title: string; type: string; template?: string; sections?: string[] }) =>
      apiRequest("/api/reports/generate", { method: "POST", body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/reports"] });
      toast({ title: "Report generation started", description: "Your report is being generated" });
      setReportTitle("");
    },
    onError: (error) => {
      toast({ title: "Generation failed", description: error.message, variant: "destructive" });
    },
  });

  // Download report mutation
  const downloadReportMutation = useMutation({
    mutationFn: (reportId: string) =>
      apiRequest(`/api/reports/${reportId}/download`, { method: "GET" }),
    onSuccess: (blob, reportId) => {
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `security-report-${reportId}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      toast({ title: "Download started", description: "Report is being downloaded" });
    },
    onError: (error) => {
      toast({ title: "Download failed", description: error.message, variant: "destructive" });
    },
  });

  const handleGenerateReport = () => {
    if (!reportTitle.trim()) {
      toast({ title: "No title provided", description: "Please enter a report title", variant: "destructive" });
      return;
    }
    
    const sections = customSections.trim() 
      ? customSections.split('\n').map(s => s.trim()).filter(s => s)
      : undefined;
      
    generateReportMutation.mutate({
      title: reportTitle,
      type: reportType,
      template: selectedTemplate || undefined,
      sections,
    });
  };

  const handleDownloadReport = (reportId: string) => {
    downloadReportMutation.mutate(reportId);
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical": return "bg-red-600 text-white";
      case "high": return "bg-red-500 text-white";
      case "medium": return "bg-yellow-500 text-black";
      case "low": return "bg-green-500 text-white";
      default: return "bg-gray-500 text-white";
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case "critical": return "text-red-600";
      case "high": return "text-red-500";
      case "medium": return "text-yellow-500";
      case "low": return "text-green-500";
      default: return "text-gray-500";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed": return "text-green-500";
      case "generating": return "text-yellow-500 animate-pulse";
      case "failed": return "text-red-500";
      default: return "text-gray-500";
    }
  };

  return (
    <div className="h-full flex flex-col space-y-6 p-6" data-testid="reports-page">
      <div className="flex items-center space-x-2">
        <FileText className="h-6 w-6 text-cyber-amber" />
        <h1 className="text-2xl font-bold text-white">Security Reports</h1>
        <Badge variant="outline" className="text-cyber-amber border-cyber-amber">
          AI Generated
        </Badge>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="generate" data-testid="tab-generate">
            <FileText className="h-4 w-4 mr-2" />
            Generate
          </TabsTrigger>
          <TabsTrigger value="reports" data-testid="tab-reports">
            <BarChart3 className="h-4 w-4 mr-2" />
            Reports
          </TabsTrigger>
          <TabsTrigger value="analytics" data-testid="tab-analytics">
            <Target className="h-4 w-4 mr-2" />
            Analytics
          </TabsTrigger>
        </TabsList>

        <TabsContent value="generate" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Generate Security Report</CardTitle>
                <CardDescription>
                  Create professional cybersecurity reports with AI-powered analysis and recommendations
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Report Title</label>
                  <Input
                    value={reportTitle}
                    onChange={(e) => setReportTitle(e.target.value)}
                    placeholder="Q1 2024 Security Assessment Report"
                    className="bg-slate-800 border-slate-600"
                    data-testid="input-report-title"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Report Type</label>
                  <select
                    value={reportType}
                    onChange={(e) => setReportType(e.target.value)}
                    className="w-full p-2 rounded bg-slate-800 border border-slate-600 text-white"
                    data-testid="select-report-type"
                  >
                    <option value="executive">Executive Summary</option>
                    <option value="technical">Technical Report</option>
                    <option value="compliance">Compliance Report</option>
                    <option value="penetration">Penetration Test Report</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Template (Optional)</label>
                  <select
                    value={selectedTemplate}
                    onChange={(e) => setSelectedTemplate(e.target.value)}
                    className="w-full p-2 rounded bg-slate-800 border border-slate-600 text-white"
                    data-testid="select-template"
                  >
                    <option value="">Select a template...</option>
                    {templates?.map((template: ReportTemplate) => (
                      <option key={template.id} value={template.id}>
                        {template.name} - {template.description}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Custom Sections (Optional)</label>
                  <Textarea
                    value={customSections}
                    onChange={(e) => setCustomSections(e.target.value)}
                    placeholder="Executive Summary&#10;Risk Assessment&#10;Findings&#10;Recommendations&#10;..."
                    className="min-h-[100px] bg-slate-800 border-slate-600"
                    data-testid="textarea-custom-sections"
                  />
                </div>
                <Button
                  onClick={handleGenerateReport}
                  disabled={generateReportMutation.isPending}
                  className="w-full bg-cyber-amber text-black hover:bg-cyber-amber/80"
                  data-testid="button-generate-report"
                >
                  {generateReportMutation.isPending ? "Generating..." : "Generate Report"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Available Findings</CardTitle>
                <CardDescription>
                  Current findings that will be included in the report
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[400px]">
                  {findingsLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading findings...</div>
                  ) : availableFindings?.length ? (
                    <div className="space-y-3">
                      {availableFindings.map((finding: any, index: number) => (
                        <div key={index} className="border border-slate-600 rounded p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white text-sm">{finding.title}</span>
                            <Badge className={getSeverityColor(finding.severity)}>
                              {finding.severity}
                            </Badge>
                          </div>
                          <div className="text-xs text-slate-400">{finding.category}</div>
                          <div className="text-sm text-slate-300 line-clamp-2">
                            {finding.description}
                          </div>
                          {finding.mitreTechnique && (
                            <Badge variant="outline" className="text-xs">
                              {finding.mitreTechnique}
                            </Badge>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No findings available</div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="reports" className="flex-1 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Generated Reports</CardTitle>
              <CardDescription>
                Browse and download your generated security reports
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[600px]">
                {reportsLoading ? (
                  <div className="text-center py-4 text-slate-400">Loading reports...</div>
                ) : reports?.length ? (
                  <div className="space-y-4">
                    {reports.map((report: SecurityReport) => (
                      <div key={report.id} className="border border-slate-600 rounded p-4 space-y-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <h3 className="font-medium text-white">{report.title}</h3>
                            <div className="flex items-center space-x-2 mt-1">
                              <Badge variant="outline">{report.type}</Badge>
                              <span className={`text-sm ${getStatusColor(report.status)}`}>
                                {report.status}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            {report.status === "generating" && (
                              <div className="flex items-center space-x-2">
                                <Progress value={report.progress} className="w-20 h-2" />
                                <span className="text-xs text-slate-400">{report.progress}%</span>
                              </div>
                            )}
                            {report.status === "completed" && (
                              <Button
                                size="sm"
                                onClick={() => handleDownloadReport(report.id)}
                                disabled={downloadReportMutation.isPending}
                                className="bg-cyber-blue hover:bg-cyber-blue/80"
                                data-testid={`button-download-${report.id}`}
                              >
                                <Download className="h-4 w-4 mr-1" />
                                Download
                              </Button>
                            )}
                          </div>
                        </div>

                        {report.summary && (
                          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                            <div className="text-center">
                              <div className="text-slate-400">Total</div>
                              <div className="text-white font-bold">{report.summary.totalFindings}</div>
                            </div>
                            <div className="text-center">
                              <div className="text-slate-400">Critical</div>
                              <div className="text-red-500 font-bold">{report.summary.criticalCount}</div>
                            </div>
                            <div className="text-center">
                              <div className="text-slate-400">High</div>
                              <div className="text-red-400 font-bold">{report.summary.highCount}</div>
                            </div>
                            <div className="text-center">
                              <div className="text-slate-400">Medium</div>
                              <div className="text-yellow-500 font-bold">{report.summary.mediumCount}</div>
                            </div>
                            <div className="text-center">
                              <div className="text-slate-400">Low</div>
                              <div className="text-green-500 font-bold">{report.summary.lowCount}</div>
                            </div>
                          </div>
                        )}

                        {report.executiveSummary && (
                          <div className="text-sm">
                            <div className="text-slate-400 mb-1">Executive Summary</div>
                            <div className="text-slate-300 line-clamp-3">{report.executiveSummary}</div>
                          </div>
                        )}

                        {report.mitreMapping && report.mitreMapping.length > 0 && (
                          <div>
                            <div className="text-sm text-slate-400 mb-2">MITRE ATT&CK Coverage</div>
                            <div className="flex flex-wrap gap-1">
                              {report.mitreMapping.slice(0, 5).map((mapping, index) => (
                                <Badge key={index} variant="outline" className="text-xs">
                                  {mapping.tactic} ({mapping.techniques.length})
                                </Badge>
                              ))}
                              {report.mitreMapping.length > 5 && (
                                <Badge variant="outline" className="text-xs">
                                  +{report.mitreMapping.length - 5} more
                                </Badge>
                              )}
                            </div>
                          </div>
                        )}

                        <div className="flex items-center justify-between text-xs text-slate-400">
                          <span>Created: {new Date(report.createdAt).toLocaleDateString()}</span>
                          <span className={getRiskColor(report.summary?.overallRisk || "low")}>
                            Overall Risk: {report.summary?.overallRisk?.toUpperCase() || "N/A"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <FileText className="h-12 w-12 text-slate-600 mx-auto mb-4" />
                    <p className="text-slate-400 mb-4">No reports generated yet</p>
                    <Button
                      onClick={() => setActiveTab("generate")}
                      className="bg-cyber-amber text-black hover:bg-cyber-amber/80"
                    >
                      Generate Your First Report
                    </Button>
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analytics" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Report Statistics</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Total Reports</span>
                    <span className="text-white font-bold">{reports?.length || 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Completed</span>
                    <span className="text-green-500 font-bold">
                      {reports?.filter(r => r.status === 'completed').length || 0}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">In Progress</span>
                    <span className="text-yellow-500 font-bold">
                      {reports?.filter(r => r.status === 'generating').length || 0}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Failed</span>
                    <span className="text-red-500 font-bold">
                      {reports?.filter(r => r.status === 'failed').length || 0}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Finding Trends</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="text-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-300">Critical Findings</span>
                      <span className="text-red-500">
                        {reports?.reduce((acc, r) => acc + (r.summary?.criticalCount || 0), 0) || 0}
                      </span>
                    </div>
                    <Progress 
                      value={reports?.length ? (reports.reduce((acc, r) => acc + (r.summary?.criticalCount || 0), 0) / reports.reduce((acc, r) => acc + (r.summary?.totalFindings || 0), 0)) * 100 : 0} 
                      className="h-2" 
                    />
                  </div>
                  <div className="text-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-300">High Findings</span>
                      <span className="text-red-400">
                        {reports?.reduce((acc, r) => acc + (r.summary?.highCount || 0), 0) || 0}
                      </span>
                    </div>
                    <Progress 
                      value={reports?.length ? (reports.reduce((acc, r) => acc + (r.summary?.highCount || 0), 0) / reports.reduce((acc, r) => acc + (r.summary?.totalFindings || 0), 0)) * 100 : 0} 
                      className="h-2" 
                    />
                  </div>
                  <div className="text-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-300">Medium Findings</span>
                      <span className="text-yellow-500">
                        {reports?.reduce((acc, r) => acc + (r.summary?.mediumCount || 0), 0) || 0}
                      </span>
                    </div>
                    <Progress 
                      value={reports?.length ? (reports.reduce((acc, r) => acc + (r.summary?.mediumCount || 0), 0) / reports.reduce((acc, r) => acc + (r.summary?.totalFindings || 0), 0)) * 100 : 0} 
                      className="h-2" 
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>MITRE Coverage</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="text-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-300">Tactics Covered</span>
                      <span className="text-cyber-blue">
                        {reports?.reduce((acc, r) => {
                          const tactics = new Set(r.mitreMapping?.map(m => m.tactic) || []);
                          return acc + tactics.size;
                        }, 0) || 0}
                      </span>
                    </div>
                  </div>
                  <div className="text-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-300">Techniques Mapped</span>
                      <span className="text-cyber-green">
                        {reports?.reduce((acc, r) => {
                          return acc + (r.mitreMapping?.reduce((tAcc, m) => tAcc + m.techniques.length, 0) || 0);
                        }, 0) || 0}
                      </span>
                    </div>
                  </div>
                  <div className="text-xs text-slate-400">
                    Coverage improves with each assessment
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}