import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import { Code, Bug, Shield, Zap, AlertTriangle, CheckCircle } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";

interface CodeAnalysis {
  id: string;
  code: string;
  language: string;
  vulnerabilities: Array<{
    type: string;
    severity: "low" | "medium" | "high" | "critical";
    description: string;
    line: number;
    suggestion: string;
  }>;
  securityScore: number;
  mitreTags: string[];
  exploitPotential: string;
  recommendations: string[];
  createdAt: string;
}

interface ExploitGeneration {
  id: string;
  targetCode: string;
  exploitType: string;
  payload: string;
  description: string;
  mitreTechnique: string;
  riskLevel: "low" | "medium" | "high";
  preventions: string[];
  createdAt: string;
}

export default function CodingPage() {
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("javascript");
  const [exploitTarget, setExploitTarget] = useState("");
  const [exploitType, setExploitType] = useState("injection");
  const [activeTab, setActiveTab] = useState("analysis");
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Fetch recent code analyses
  const { data: analyses, isLoading: analysesLoading } = useQuery({
    queryKey: ["/api/coding/analyses"],
    enabled: true,
  });

  // Fetch recent exploit generations
  const { data: exploits, isLoading: exploitsLoading } = useQuery({
    queryKey: ["/api/coding/exploits"],
    enabled: true,
  });

  // Code analysis mutation
  const analyzeCodeMutation = useMutation({
    mutationFn: (data: { code: string; language: string }) =>
      apiRequest("/api/coding/analyze", { method: "POST", body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/coding/analyses"] });
      toast({ title: "Code analysis completed", description: "Security vulnerabilities have been identified" });
    },
    onError: (error) => {
      toast({ title: "Analysis failed", description: error.message, variant: "destructive" });
    },
  });

  // Exploit generation mutation
  const generateExploitMutation = useMutation({
    mutationFn: (data: { code: string; exploitType: string; language: string }) =>
      apiRequest("/api/coding/generate-exploit", { method: "POST", body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/coding/exploits"] });
      toast({ title: "Exploit generated", description: "Proof of concept has been created" });
    },
    onError: (error) => {
      toast({ title: "Generation failed", description: error.message, variant: "destructive" });
    },
  });

  const handleAnalyzeCode = () => {
    if (!code.trim()) {
      toast({ title: "No code provided", description: "Please enter code to analyze", variant: "destructive" });
      return;
    }
    analyzeCodeMutation.mutate({ code, language });
  };

  const handleGenerateExploit = () => {
    if (!exploitTarget.trim()) {
      toast({ title: "No target code provided", description: "Please enter target code", variant: "destructive" });
      return;
    }
    generateExploitMutation.mutate({ code: exploitTarget, exploitType, language });
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical": return "bg-red-500";
      case "high": return "bg-red-400";
      case "medium": return "bg-yellow-500";
      case "low": return "bg-green-500";
      default: return "bg-gray-500";
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case "high": return "text-red-500";
      case "medium": return "text-yellow-500";
      case "low": return "text-green-500";
      default: return "text-gray-500";
    }
  };

  return (
    <div className="h-full flex flex-col space-y-6 p-6" data-testid="coding-page">
      <div className="flex items-center space-x-2">
        <Code className="h-6 w-6 text-cyber-blue" />
        <h1 className="text-2xl font-bold text-white">AI Coding Assistant</h1>
        <Badge variant="outline" className="text-cyber-green border-cyber-green">
          Secure Development
        </Badge>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="analysis" data-testid="tab-analysis">
            <Shield className="h-4 w-4 mr-2" />
            Security Analysis
          </TabsTrigger>
          <TabsTrigger value="exploits" data-testid="tab-exploits">
            <Zap className="h-4 w-4 mr-2" />
            Exploit Generation
          </TabsTrigger>
          <TabsTrigger value="history" data-testid="tab-history">
            <Bug className="h-4 w-4 mr-2" />
            Analysis History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="analysis" className="flex-1 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Code Security Analysis</CardTitle>
              <CardDescription>
                AI-powered security analysis to identify vulnerabilities and provide secure coding recommendations
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-white">Programming Language</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full p-2 rounded bg-slate-800 border border-slate-600 text-white"
                  data-testid="select-language"
                >
                  <option value="javascript">JavaScript</option>
                  <option value="python">Python</option>
                  <option value="java">Java</option>
                  <option value="php">PHP</option>
                  <option value="c">C/C++</option>
                  <option value="sql">SQL</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-white">Code to Analyze</label>
                <Textarea
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Paste your code here for security analysis..."
                  className="min-h-[300px] font-mono text-sm bg-slate-900 border-slate-600"
                  data-testid="textarea-code"
                />
              </div>
              <Button
                onClick={handleAnalyzeCode}
                disabled={analyzeCodeMutation.isPending}
                className="w-full bg-cyber-blue hover:bg-cyber-blue/80"
                data-testid="button-analyze"
              >
                {analyzeCodeMutation.isPending ? "Analyzing..." : "Analyze Security"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="exploits" className="flex-1 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Exploit PoC Generation</CardTitle>
              <CardDescription>
                Generate educational proof-of-concept exploits for learning and testing purposes
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  Generated exploits are for educational and authorized testing only. Misuse is prohibited.
                </AlertDescription>
              </Alert>
              <div className="space-y-2">
                <label className="text-sm font-medium text-white">Exploit Type</label>
                <select
                  value={exploitType}
                  onChange={(e) => setExploitType(e.target.value)}
                  className="w-full p-2 rounded bg-slate-800 border border-slate-600 text-white"
                  data-testid="select-exploit-type"
                >
                  <option value="injection">SQL/NoSQL Injection</option>
                  <option value="xss">Cross-Site Scripting (XSS)</option>
                  <option value="csrf">Cross-Site Request Forgery</option>
                  <option value="buffer-overflow">Buffer Overflow</option>
                  <option value="deserialization">Insecure Deserialization</option>
                  <option value="path-traversal">Path Traversal</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-white">Target Code</label>
                <Textarea
                  value={exploitTarget}
                  onChange={(e) => setExploitTarget(e.target.value)}
                  placeholder="Paste vulnerable code to generate exploit PoC..."
                  className="min-h-[200px] font-mono text-sm bg-slate-900 border-slate-600"
                  data-testid="textarea-exploit-target"
                />
              </div>
              <Button
                onClick={handleGenerateExploit}
                disabled={generateExploitMutation.isPending}
                className="w-full bg-cyber-red hover:bg-cyber-red/80"
                data-testid="button-generate-exploit"
              >
                {generateExploitMutation.isPending ? "Generating..." : "Generate Exploit PoC"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Recent Analyses</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[400px]">
                  {analysesLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading analyses...</div>
                  ) : analyses?.length ? (
                    <div className="space-y-4">
                      {analyses.map((analysis: CodeAnalysis) => (
                        <div key={analysis.id} className="border border-slate-600 rounded p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <Badge variant="outline">{analysis.language}</Badge>
                            <span className="text-sm text-slate-400">
                              Score: {analysis.securityScore}/100
                            </span>
                          </div>
                          <div className="text-sm text-slate-300">
                            {analysis.vulnerabilities.length} vulnerabilities found
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {analysis.vulnerabilities.slice(0, 3).map((vuln, index) => (
                              <Badge
                                key={index}
                                className={`text-xs ${getSeverityColor(vuln.severity)}`}
                              >
                                {vuln.type}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No analyses yet</div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recent Exploits</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[400px]">
                  {exploitsLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading exploits...</div>
                  ) : exploits?.length ? (
                    <div className="space-y-4">
                      {exploits.map((exploit: ExploitGeneration) => (
                        <div key={exploit.id} className="border border-slate-600 rounded p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <Badge variant="outline">{exploit.exploitType}</Badge>
                            <span className={`text-sm font-medium ${getRiskColor(exploit.riskLevel)}`}>
                              {exploit.riskLevel.toUpperCase()}
                            </span>
                          </div>
                          <div className="text-sm text-slate-300">{exploit.description}</div>
                          <div className="text-xs text-slate-400">
                            MITRE: {exploit.mitreTechnique}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No exploits generated</div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}