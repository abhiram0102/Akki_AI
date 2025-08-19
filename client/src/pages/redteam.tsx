import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import { Target, Swords, Mail, Users, AlertTriangle, Activity } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";

interface AttackSimulation {
  id: string;
  name: string;
  target: string;
  attackType: string;
  phase: "reconnaissance" | "weaponization" | "delivery" | "exploitation" | "installation" | "command" | "actions";
  progress: number;
  findings: Array<{
    type: string;
    severity: "low" | "medium" | "high" | "critical";
    description: string;
    mitreTechnique: string;
  }>;
  status: "planning" | "active" | "completed" | "failed";
  createdAt: string;
}

interface PhishingCampaign {
  id: string;
  name: string;
  template: string;
  targetList: string[];
  sendsCompleted: number;
  opensTracked: number;
  clicksTracked: number;
  credentialsHarvested: number;
  status: "draft" | "active" | "completed";
  createdAt: string;
}

interface AttackChain {
  id: string;
  name: string;
  steps: Array<{
    technique: string;
    mitreTactic: string;
    description: string;
    automated: boolean;
    status: "pending" | "executing" | "completed" | "failed";
  }>;
  currentStep: number;
  overallProgress: number;
  riskLevel: "low" | "medium" | "high";
  createdAt: string;
}

export default function RedTeamPage() {
  const [selectedTarget, setSelectedTarget] = useState("");
  const [attackType, setAttackType] = useState("phishing");
  const [campaignName, setCampaignName] = useState("");
  const [emailTemplate, setEmailTemplate] = useState("");
  const [targetEmails, setTargetEmails] = useState("");
  const [activeTab, setActiveTab] = useState("simulations");
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Fetch active simulations
  const { data: simulations, isLoading: simulationsLoading } = useQuery({
    queryKey: ["/api/redteam/simulations"],
    enabled: true,
  });

  // Fetch phishing campaigns
  const { data: campaigns, isLoading: campaignsLoading } = useQuery({
    queryKey: ["/api/redteam/campaigns"],
    enabled: true,
  });

  // Fetch attack chains
  const { data: attackChains, isLoading: chainsLoading } = useQuery({
    queryKey: ["/api/redteam/chains"],
    enabled: true,
  });

  // Create attack simulation
  const createSimulationMutation = useMutation({
    mutationFn: (data: { target: string; attackType: string; name: string }) =>
      apiRequest("/api/redteam/simulations", { method: "POST", body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/redteam/simulations"] });
      toast({ title: "Simulation created", description: "Attack simulation has been initiated" });
      setSelectedTarget("");
    },
    onError: (error) => {
      toast({ title: "Creation failed", description: error.message, variant: "destructive" });
    },
  });

  // Create phishing campaign
  const createCampaignMutation = useMutation({
    mutationFn: (data: { name: string; template: string; targets: string[] }) =>
      apiRequest("/api/redteam/campaigns", { method: "POST", body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/redteam/campaigns"] });
      toast({ title: "Campaign created", description: "Phishing campaign is ready to launch" });
      setCampaignName("");
      setEmailTemplate("");
      setTargetEmails("");
    },
    onError: (error) => {
      toast({ title: "Creation failed", description: error.message, variant: "destructive" });
    },
  });

  // Generate attack chain
  const generateChainMutation = useMutation({
    mutationFn: (data: { target: string; objective: string }) =>
      apiRequest("/api/redteam/chains/generate", { method: "POST", body: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/redteam/chains"] });
      toast({ title: "Attack chain generated", description: "Multi-step attack plan created" });
    },
    onError: (error) => {
      toast({ title: "Generation failed", description: error.message, variant: "destructive" });
    },
  });

  const handleCreateSimulation = () => {
    if (!selectedTarget.trim()) {
      toast({ title: "No target specified", description: "Please enter a target", variant: "destructive" });
      return;
    }
    createSimulationMutation.mutate({
      target: selectedTarget,
      attackType,
      name: `${attackType} simulation on ${selectedTarget}`,
    });
  };

  const handleCreateCampaign = () => {
    if (!campaignName.trim() || !emailTemplate.trim() || !targetEmails.trim()) {
      toast({ title: "Missing information", description: "Please fill all required fields", variant: "destructive" });
      return;
    }
    const targets = targetEmails.split('\n').filter(email => email.trim());
    createCampaignMutation.mutate({
      name: campaignName,
      template: emailTemplate,
      targets,
    });
  };

  const getPhaseColor = (phase: string) => {
    const phases = {
      reconnaissance: "bg-blue-500",
      weaponization: "bg-purple-500",
      delivery: "bg-yellow-500",
      exploitation: "bg-orange-500",
      installation: "bg-red-500",
      command: "bg-red-600",
      actions: "bg-red-700",
    };
    return phases[phase] || "bg-gray-500";
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "active": return "text-green-500";
      case "completed": return "text-blue-500";
      case "failed": return "text-red-500";
      default: return "text-yellow-500";
    }
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

  return (
    <div className="h-full flex flex-col space-y-6 p-6" data-testid="redteam-page">
      <div className="flex items-center space-x-2">
        <Swords className="h-6 w-6 text-cyber-red" />
        <h1 className="text-2xl font-bold text-white">Red Team Operations</h1>
        <Badge variant="outline" className="text-cyber-red border-cyber-red">
          Authorized Testing Only
        </Badge>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          All red team activities must be authorized and conducted within approved scope. Unauthorized attacks are illegal.
        </AlertDescription>
      </Alert>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="simulations" data-testid="tab-simulations">
            <Target className="h-4 w-4 mr-2" />
            Simulations
          </TabsTrigger>
          <TabsTrigger value="phishing" data-testid="tab-phishing">
            <Mail className="h-4 w-4 mr-2" />
            Phishing
          </TabsTrigger>
          <TabsTrigger value="chains" data-testid="tab-chains">
            <Activity className="h-4 w-4 mr-2" />
            Attack Chains
          </TabsTrigger>
          <TabsTrigger value="operations" data-testid="tab-operations">
            <Users className="h-4 w-4 mr-2" />
            Operations
          </TabsTrigger>
        </TabsList>

        <TabsContent value="simulations" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Create Attack Simulation</CardTitle>
                <CardDescription>
                  Launch AI-driven attack simulations to test defensive capabilities
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Target</label>
                  <Input
                    value={selectedTarget}
                    onChange={(e) => setSelectedTarget(e.target.value)}
                    placeholder="Target domain or IP (e.g., testlab.local)"
                    className="bg-slate-800 border-slate-600"
                    data-testid="input-target"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Attack Type</label>
                  <select
                    value={attackType}
                    onChange={(e) => setAttackType(e.target.value)}
                    className="w-full p-2 rounded bg-slate-800 border border-slate-600 text-white"
                    data-testid="select-attack-type"
                  >
                    <option value="phishing">Phishing Campaign</option>
                    <option value="network-scan">Network Reconnaissance</option>
                    <option value="web-app">Web Application Testing</option>
                    <option value="social-engineering">Social Engineering</option>
                    <option value="credential-stuffing">Credential Stuffing</option>
                    <option value="lateral-movement">Lateral Movement</option>
                  </select>
                </div>
                <Button
                  onClick={handleCreateSimulation}
                  disabled={createSimulationMutation.isPending}
                  className="w-full bg-cyber-red hover:bg-cyber-red/80"
                  data-testid="button-create-simulation"
                >
                  {createSimulationMutation.isPending ? "Creating..." : "Launch Simulation"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Active Simulations</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[300px]">
                  {simulationsLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading simulations...</div>
                  ) : simulations?.length ? (
                    <div className="space-y-4">
                      {simulations.map((sim: AttackSimulation) => (
                        <div key={sim.id} className="border border-slate-600 rounded p-4 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white">{sim.name}</span>
                            <Badge className={getStatusColor(sim.status)}>{sim.status}</Badge>
                          </div>
                          <div className="text-sm text-slate-400">Target: {sim.target}</div>
                          <div className="space-y-2">
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-slate-300">Phase: {sim.phase}</span>
                              <span className="text-slate-400">{sim.progress}%</span>
                            </div>
                            <Progress value={sim.progress} className="h-2" />
                          </div>
                          {sim.findings.length > 0 && (
                            <div className="text-sm text-slate-300">
                              {sim.findings.length} findings discovered
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No active simulations</div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="phishing" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Create Phishing Campaign</CardTitle>
                <CardDescription>
                  Design and deploy AI-generated phishing campaigns for security awareness training
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Campaign Name</label>
                  <Input
                    value={campaignName}
                    onChange={(e) => setCampaignName(e.target.value)}
                    placeholder="Q1 2024 Security Awareness Test"
                    className="bg-slate-800 border-slate-600"
                    data-testid="input-campaign-name"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Email Template</label>
                  <Textarea
                    value={emailTemplate}
                    onChange={(e) => setEmailTemplate(e.target.value)}
                    placeholder="AI will generate realistic phishing email content..."
                    className="min-h-[150px] bg-slate-800 border-slate-600"
                    data-testid="textarea-email-template"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Target Email List</label>
                  <Textarea
                    value={targetEmails}
                    onChange={(e) => setTargetEmails(e.target.value)}
                    placeholder="user1@company.com&#10;user2@company.com&#10;..."
                    className="min-h-[100px] bg-slate-800 border-slate-600"
                    data-testid="textarea-target-emails"
                  />
                </div>
                <Button
                  onClick={handleCreateCampaign}
                  disabled={createCampaignMutation.isPending}
                  className="w-full bg-cyber-amber text-black hover:bg-cyber-amber/80"
                  data-testid="button-create-campaign"
                >
                  {createCampaignMutation.isPending ? "Creating..." : "Create Campaign"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Campaign Results</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[400px]">
                  {campaignsLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading campaigns...</div>
                  ) : campaigns?.length ? (
                    <div className="space-y-4">
                      {campaigns.map((campaign: PhishingCampaign) => (
                        <div key={campaign.id} className="border border-slate-600 rounded p-4 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white">{campaign.name}</span>
                            <Badge variant="outline">{campaign.status}</Badge>
                          </div>
                          <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                              <span className="text-slate-400">Sent:</span>
                              <span className="ml-2 text-white">{campaign.sendsCompleted}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Opened:</span>
                              <span className="ml-2 text-cyber-amber">{campaign.opensTracked}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Clicked:</span>
                              <span className="ml-2 text-cyber-red">{campaign.clicksTracked}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Compromised:</span>
                              <span className="ml-2 text-red-500">{campaign.credentialsHarvested}</span>
                            </div>
                          </div>
                          {campaign.sendsCompleted > 0 && (
                            <div className="text-xs text-slate-400">
                              Success Rate: {Math.round((campaign.clicksTracked / campaign.sendsCompleted) * 100)}%
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No campaigns created</div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="chains" className="flex-1 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Attack Chain Planning</CardTitle>
              <CardDescription>
                AI-generated multi-step attack chains mapped to MITRE ATT&CK framework
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[500px]">
                {chainsLoading ? (
                  <div className="text-center py-4 text-slate-400">Loading attack chains...</div>
                ) : attackChains?.length ? (
                  <div className="space-y-6">
                    {attackChains.map((chain: AttackChain) => (
                      <div key={chain.id} className="border border-slate-600 rounded p-4 space-y-4">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-white">{chain.name}</span>
                          <div className="flex items-center space-x-2">
                            <Badge variant="outline" className={`${chain.riskLevel === 'high' ? 'text-red-500 border-red-500' : chain.riskLevel === 'medium' ? 'text-yellow-500 border-yellow-500' : 'text-green-500 border-green-500'}`}>
                              {chain.riskLevel.toUpperCase()}
                            </Badge>
                            <span className="text-sm text-slate-400">{chain.overallProgress}%</span>
                          </div>
                        </div>
                        <Progress value={chain.overallProgress} className="h-2" />
                        <div className="space-y-2">
                          {chain.steps.map((step, index) => (
                            <div key={index} className="flex items-center space-x-3 text-sm">
                              <div className={`w-3 h-3 rounded-full ${
                                step.status === 'completed' ? 'bg-green-500' :
                                step.status === 'executing' ? 'bg-yellow-500 animate-pulse' :
                                step.status === 'failed' ? 'bg-red-500' : 'bg-slate-600'
                              }`} />
                              <span className="flex-1 text-slate-300">{step.technique}</span>
                              <Badge variant="outline" className="text-xs">{step.mitreTactic}</Badge>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <p className="text-slate-400 mb-4">No attack chains planned</p>
                    <Button
                      onClick={() => generateChainMutation.mutate({ target: "testlab.local", objective: "Domain Admin" })}
                      disabled={generateChainMutation.isPending}
                      className="bg-cyber-blue hover:bg-cyber-blue/80"
                    >
                      {generateChainMutation.isPending ? "Generating..." : "Generate Sample Chain"}
                    </Button>
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="operations" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Operation Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Active Simulations</span>
                    <span className="text-cyber-blue font-bold">{simulations?.filter(s => s.status === 'active')?.length || 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Running Campaigns</span>
                    <span className="text-cyber-amber font-bold">{campaigns?.filter(c => c.status === 'active')?.length || 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Planned Chains</span>
                    <span className="text-cyber-red font-bold">{attackChains?.length || 0}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Success Metrics</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Avg. Click Rate</span>
                    <span className="text-white font-bold">
                      {campaigns?.length 
                        ? Math.round(campaigns.reduce((acc, c) => acc + (c.clicksTracked / Math.max(c.sendsCompleted, 1)) * 100, 0) / campaigns.length)
                        : 0}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Compromise Rate</span>
                    <span className="text-white font-bold">
                      {campaigns?.length 
                        ? Math.round(campaigns.reduce((acc, c) => acc + (c.credentialsHarvested / Math.max(c.sendsCompleted, 1)) * 100, 0) / campaigns.length)
                        : 0}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-300">Objectives Met</span>
                    <span className="text-white font-bold">
                      {attackChains?.filter(c => c.overallProgress === 100)?.length || 0}/{attackChains?.length || 0}
                    </span>
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
                      <span className="text-slate-300">Initial Access</span>
                      <span className="text-cyber-blue">85%</span>
                    </div>
                    <Progress value={85} className="h-2" />
                  </div>
                  <div className="text-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-300">Persistence</span>
                      <span className="text-cyber-amber">60%</span>
                    </div>
                    <Progress value={60} className="h-2" />
                  </div>
                  <div className="text-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-300">Lateral Movement</span>
                      <span className="text-cyber-red">40%</span>
                    </div>
                    <Progress value={40} className="h-2" />
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