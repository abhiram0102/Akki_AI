import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useToast } from "@/hooks/use-toast";
import { Search, Globe, Database, GitBranch, AlertTriangle, ExternalLink } from "lucide-react";
import { apiRequest } from "@/lib/queryClient";

interface DomainIntelligence {
  domain: string;
  subdomains: string[];
  ipAddresses: string[];
  technologies: Array<{
    name: string;
    version?: string;
    category: string;
  }>;
  certificates: Array<{
    issuer: string;
    subject: string;
    validFrom: string;
    validTo: string;
  }>;
  dnsRecords: Record<string, string[]>;
  socialMedia: Array<{
    platform: string;
    url: string;
    verified: boolean;
  }>;
  breaches: Array<{
    name: string;
    date: string;
    description: string;
  }>;
  riskScore: number;
  lastUpdated: string;
}

interface GitHubIntelligence {
  organization: string;
  repositories: Array<{
    name: string;
    description: string;
    language: string;
    stars: number;
    forks: number;
    isPrivate: boolean;
    hasSecrets: boolean;
    vulnerabilities: Array<{
      type: string;
      severity: string;
      description: string;
    }>;
  }>;
  users: Array<{
    username: string;
    email?: string;
    name?: string;
    location?: string;
    company?: string;
  }>;
  sensitiveFiles: Array<{
    repository: string;
    filename: string;
    type: "config" | "credential" | "key" | "other";
    content: string;
  }>;
  totalRepos: number;
  riskLevel: "low" | "medium" | "high";
}

interface ShodanIntelligence {
  query: string;
  results: Array<{
    ip: string;
    port: number;
    protocol: string;
    service: string;
    banner: string;
    location: {
      country: string;
      city: string;
      latitude: number;
      longitude: number;
    };
    vulns: string[];
    lastSeen: string;
  }>;
  totalResults: number;
  countriesFound: string[];
  topServices: Array<{
    name: string;
    count: number;
  }>;
  vulnerabilities: Array<{
    cve: string;
    count: number;
    severity: string;
  }>;
}

export default function OSINTPage() {
  const [domainTarget, setDomainTarget] = useState("");
  const [githubTarget, setGithubTarget] = useState("");
  const [shodanQuery, setShodanQuery] = useState("");
  const [activeTab, setActiveTab] = useState("domain");
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Domain intelligence mutation
  const domainIntelMutation = useMutation({
    mutationFn: (domain: string) =>
      apiRequest("/api/osint/domain", { method: "POST", body: { domain } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/osint/domain"] });
      toast({ title: "Domain scan completed", description: "Intelligence gathered successfully" });
    },
    onError: (error) => {
      toast({ title: "Domain scan failed", description: error.message, variant: "destructive" });
    },
  });

  // GitHub intelligence mutation
  const githubIntelMutation = useMutation({
    mutationFn: (target: string) =>
      apiRequest("/api/osint/github", { method: "POST", body: { target } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/osint/github"] });
      toast({ title: "GitHub scan completed", description: "Code intelligence gathered" });
    },
    onError: (error) => {
      toast({ title: "GitHub scan failed", description: error.message, variant: "destructive" });
    },
  });

  // Shodan intelligence mutation
  const shodanIntelMutation = useMutation({
    mutationFn: (query: string) =>
      apiRequest("/api/osint/shodan", { method: "POST", body: { query } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/osint/shodan"] });
      toast({ title: "Shodan search completed", description: "Internet-wide scan results ready" });
    },
    onError: (error) => {
      toast({ title: "Shodan search failed", description: error.message, variant: "destructive" });
    },
  });

  // Fetch recent domain intelligence
  const { data: domainIntel, isLoading: domainLoading } = useQuery({
    queryKey: ["/api/osint/domain/recent"],
    enabled: true,
  });

  // Fetch recent GitHub intelligence
  const { data: githubIntel, isLoading: githubLoading } = useQuery({
    queryKey: ["/api/osint/github/recent"],
    enabled: true,
  });

  // Fetch recent Shodan results
  const { data: shodanIntel, isLoading: shodanLoading } = useQuery({
    queryKey: ["/api/osint/shodan/recent"],
    enabled: true,
  });

  const handleDomainScan = () => {
    if (!domainTarget.trim()) {
      toast({ title: "No domain specified", description: "Please enter a domain to scan", variant: "destructive" });
      return;
    }
    domainIntelMutation.mutate(domainTarget);
  };

  const handleGitHubScan = () => {
    if (!githubTarget.trim()) {
      toast({ title: "No target specified", description: "Please enter GitHub org/user", variant: "destructive" });
      return;
    }
    githubIntelMutation.mutate(githubTarget);
  };

  const handleShodanSearch = () => {
    if (!shodanQuery.trim()) {
      toast({ title: "No query specified", description: "Please enter Shodan query", variant: "destructive" });
      return;
    }
    shodanIntelMutation.mutate(shodanQuery);
  };

  const getRiskColor = (risk: string | number) => {
    if (typeof risk === 'number') {
      if (risk >= 70) return "text-red-500";
      if (risk >= 40) return "text-yellow-500";
      return "text-green-500";
    }
    switch (risk) {
      case "high": return "text-red-500";
      case "medium": return "text-yellow-500";
      case "low": return "text-green-500";
      default: return "text-slate-400";
    }
  };

  return (
    <div className="h-full flex flex-col space-y-6 p-6" data-testid="osint-page">
      <div className="flex items-center space-x-2">
        <Search className="h-6 w-6 text-cyber-green" />
        <h1 className="text-2xl font-bold text-white">OSINT Intelligence</h1>
        <Badge variant="outline" className="text-cyber-green border-cyber-green">
          Open Source Intelligence
        </Badge>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          Ensure you have proper authorization before conducting reconnaissance on target organizations.
        </AlertDescription>
      </Alert>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="domain" data-testid="tab-domain">
            <Globe className="h-4 w-4 mr-2" />
            Domain Intel
          </TabsTrigger>
          <TabsTrigger value="github" data-testid="tab-github">
            <GitBranch className="h-4 w-4 mr-2" />
            GitHub Intel
          </TabsTrigger>
          <TabsTrigger value="shodan" data-testid="tab-shodan">
            <Database className="h-4 w-4 mr-2" />
            Shodan Search
          </TabsTrigger>
        </TabsList>

        <TabsContent value="domain" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Domain Intelligence Gathering</CardTitle>
                <CardDescription>
                  Comprehensive domain reconnaissance and infrastructure mapping
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Target Domain</label>
                  <Input
                    value={domainTarget}
                    onChange={(e) => setDomainTarget(e.target.value)}
                    placeholder="example.com"
                    className="bg-slate-800 border-slate-600"
                    data-testid="input-domain"
                  />
                </div>
                <Button
                  onClick={handleDomainScan}
                  disabled={domainIntelMutation.isPending}
                  className="w-full bg-cyber-green hover:bg-cyber-green/80"
                  data-testid="button-scan-domain"
                >
                  {domainIntelMutation.isPending ? "Scanning..." : "Start Domain Reconnaissance"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recent Domain Intelligence</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[300px]">
                  {domainLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading intelligence...</div>
                  ) : domainIntel?.length ? (
                    <div className="space-y-4">
                      {domainIntel.map((intel: DomainIntelligence, index: number) => (
                        <div key={index} className="border border-slate-600 rounded p-4 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white">{intel.domain}</span>
                            <span className={`text-sm font-medium ${getRiskColor(intel.riskScore)}`}>
                              Risk: {intel.riskScore}/100
                            </span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <span className="text-slate-400">Subdomains:</span>
                              <span className="ml-2 text-cyber-blue">{intel.subdomains?.length || 0}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">IPs:</span>
                              <span className="ml-2 text-cyber-green">{intel.ipAddresses?.length || 0}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Technologies:</span>
                              <span className="ml-2 text-cyber-amber">{intel.technologies?.length || 0}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Breaches:</span>
                              <span className="ml-2 text-cyber-red">{intel.breaches?.length || 0}</span>
                            </div>
                          </div>
                          {intel.technologies?.slice(0, 3).map((tech, techIndex) => (
                            <Badge key={techIndex} variant="outline" className="mr-1">
                              {tech.name} {tech.version && `v${tech.version}`}
                            </Badge>
                          ))}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No domain intelligence yet</div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="github" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>GitHub Intelligence</CardTitle>
                <CardDescription>
                  Scan GitHub organizations and repositories for exposed secrets and vulnerabilities
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">GitHub Organization/User</label>
                  <Input
                    value={githubTarget}
                    onChange={(e) => setGithubTarget(e.target.value)}
                    placeholder="organization-name or username"
                    className="bg-slate-800 border-slate-600"
                    data-testid="input-github"
                  />
                </div>
                <Button
                  onClick={handleGitHubScan}
                  disabled={githubIntelMutation.isPending}
                  className="w-full bg-cyber-blue hover:bg-cyber-blue/80"
                  data-testid="button-scan-github"
                >
                  {githubIntelMutation.isPending ? "Scanning..." : "Scan GitHub"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>GitHub Findings</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[300px]">
                  {githubLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading GitHub data...</div>
                  ) : githubIntel?.length ? (
                    <div className="space-y-4">
                      {githubIntel.map((intel: GitHubIntelligence, index: number) => (
                        <div key={index} className="border border-slate-600 rounded p-4 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white">{intel.organization}</span>
                            <span className={`text-sm font-medium ${getRiskColor(intel.riskLevel)}`}>
                              {intel.riskLevel.toUpperCase()}
                            </span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <span className="text-slate-400">Repositories:</span>
                              <span className="ml-2 text-cyber-blue">{intel.totalRepos}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Users Found:</span>
                              <span className="ml-2 text-cyber-green">{intel.users?.length || 0}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Sensitive Files:</span>
                              <span className="ml-2 text-cyber-red">{intel.sensitiveFiles?.length || 0}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Repositories with Secrets:</span>
                              <span className="ml-2 text-cyber-amber">
                                {intel.repositories?.filter(r => r.hasSecrets).length || 0}
                              </span>
                            </div>
                          </div>
                          {intel.sensitiveFiles?.slice(0, 2).map((file, fileIndex) => (
                            <div key={fileIndex} className="text-xs">
                              <Badge variant="outline" className="mr-2">{file.type}</Badge>
                              <span className="text-slate-300">{file.repository}/{file.filename}</span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No GitHub intelligence yet</div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="shodan" className="flex-1 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Shodan Internet Search</CardTitle>
                <CardDescription>
                  Search for internet-connected devices and services using Shodan
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Search Query</label>
                  <Input
                    value={shodanQuery}
                    onChange={(e) => setShodanQuery(e.target.value)}
                    placeholder="apache city:&quot;New York&quot; country:US"
                    className="bg-slate-800 border-slate-600"
                    data-testid="input-shodan"
                  />
                </div>
                <div className="text-xs text-slate-400 space-y-1">
                  <p>Example queries:</p>
                  <p>• apache city:"New York" - Apache servers in NYC</p>
                  <p>• product:MySQL - MySQL databases</p>
                  <p>• port:22 country:US - SSH services in US</p>
                </div>
                <Button
                  onClick={handleShodanSearch}
                  disabled={shodanIntelMutation.isPending}
                  className="w-full bg-cyber-amber text-black hover:bg-cyber-amber/80"
                  data-testid="button-shodan-search"
                >
                  {shodanIntelMutation.isPending ? "Searching..." : "Search Shodan"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Shodan Results</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[300px]">
                  {shodanLoading ? (
                    <div className="text-center py-4 text-slate-400">Loading Shodan data...</div>
                  ) : shodanIntel?.length ? (
                    <div className="space-y-4">
                      {shodanIntel.map((result: ShodanIntelligence, index: number) => (
                        <div key={index} className="border border-slate-600 rounded p-4 space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white">{result.query}</span>
                            <span className="text-sm text-slate-400">{result.totalResults} results</span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <span className="text-slate-400">Countries:</span>
                              <span className="ml-2 text-cyber-blue">{result.countriesFound?.length || 0}</span>
                            </div>
                            <div>
                              <span className="text-slate-400">Vulnerabilities:</span>
                              <span className="ml-2 text-cyber-red">{result.vulnerabilities?.length || 0}</span>
                            </div>
                          </div>
                          <div className="space-y-2">
                            {result.topServices?.slice(0, 3).map((service, serviceIndex) => (
                              <div key={serviceIndex} className="flex items-center justify-between text-xs">
                                <Badge variant="outline">{service.name}</Badge>
                                <span className="text-slate-400">{service.count}</span>
                              </div>
                            ))}
                          </div>
                          {result.results?.slice(0, 2).map((item, itemIndex) => (
                            <div key={itemIndex} className="text-xs border-t border-slate-700 pt-2">
                              <div className="flex items-center justify-between">
                                <span className="text-cyber-green">{item.ip}:{item.port}</span>
                                <span className="text-slate-400">{item.location?.country}</span>
                              </div>
                              <div className="text-slate-300 mt-1">
                                {item.service} • {item.protocol}
                              </div>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-slate-400">No Shodan results yet</div>
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