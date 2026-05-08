import { BaseAgent, AgentTask, AgentContext, AgentCapability } from "./base-agent";
import { aiService } from "../ai";
import { toolsService } from "../tools";

export class ReconAgent extends BaseAgent {
  constructor() {
    super("Recon Agent", "Advanced OSINT and reconnaissance specialist");
    
    this.capabilities = [
      {
        name: "domain_reconnaissance",
        description: "Comprehensive domain analysis including subdomains, DNS records, and infrastructure mapping",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "subdomain_discovery",
        description: "Advanced subdomain enumeration using multiple techniques",
        riskLevel: "medium",
        requiresApproval: false
      },
      {
        name: "osint_strategy",
        description: "Create comprehensive OSINT investigation strategies",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "social_media_recon",
        description: "Analyze social media presence and digital footprint",
        riskLevel: "medium",
        requiresApproval: true
      },
      {
        name: "infrastructure_mapping",
        description: "Map target infrastructure and technology stack",
        riskLevel: "medium",
        requiresApproval: false
      },
      {
        name: "threat_intelligence",
        description: "Correlate target with known threat intelligence",
        riskLevel: "low",
        requiresApproval: false
      }
    ];
  }

  protected getSystemPrompt(): string {
    return `You are the Recon Agent, an expert in Open Source Intelligence (OSINT) and reconnaissance.

Your specialties include:
- Domain and subdomain enumeration
- Infrastructure mapping and fingerprinting
- Social media and digital footprint analysis
- Threat intelligence correlation
- Attack surface discovery
- Passive reconnaissance techniques

You work ethically and legally, focusing on:
- Publicly available information only
- Passive reconnaissance methods
- Proper authorization verification
- Educational and defensive purposes
- Collaboration with other security agents

Always provide detailed, actionable intelligence with proper source attribution and risk assessments.`;
  }

  async executeTask(task: AgentTask, context: AgentContext): Promise<any> {
    const startTime = new Date();
    
    try {
      let result;
      
      switch (task.type) {
        case "domain_reconnaissance":
          result = await this.performDomainRecon(task.parameters);
          break;
        case "subdomain_discovery":
          result = await this.discoverSubdomains(task.parameters);
          break;
        case "osint_strategy":
          result = await this.createOSINTStrategy(task.parameters);
          break;
        case "social_media_recon":
          result = await this.analyzeSocialMedia(task.parameters);
          break;
        case "infrastructure_mapping":
          result = await this.mapInfrastructure(task.parameters);
          break;
        case "threat_intelligence":
          result = await this.correlateThreatIntel(task.parameters);
          break;
        default:
          throw new Error(`Unknown task type: ${task.type}`);
      }

      return {
        success: true,
        result,
        executionTime: Date.now() - startTime.getTime(),
        agent: this.name
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
        executionTime: Date.now() - startTime.getTime(),
        agent: this.name
      };
    }
  }

  private async performDomainRecon(params: { domain: string }): Promise<any> {
    const { domain } = params;
    
    const reconPrompt = `Perform comprehensive domain reconnaissance for: ${domain}

Analyze and provide:
1. Domain registration details (WHOIS data patterns)
2. DNS record analysis (A, AAAA, MX, TXT, NS records)
3. Technology stack identification
4. Certificate transparency log analysis
5. Historical data and changes
6. Associated infrastructure
7. Security posture assessment

Provide results in structured JSON format with actionable intelligence and risk indicators.

IMPORTANT: Only analyze publicly available information. This is for authorized security assessment.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: reconPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const analysis = JSON.parse(response);
    
    return {
      domain,
      analysis,
      sources: ["DNS", "WHOIS", "Certificate Transparency", "Public Records"],
      riskLevel: this.assessDomainRisk(analysis),
      recommendations: this.generateReconRecommendations(analysis),
      nextSteps: ["subdomain_discovery", "infrastructure_mapping"],
      timestamp: new Date()
    };
  }

  private async discoverSubdomains(params: { domain: string, techniques?: string[] }): Promise<any> {
    const { domain, techniques = ["dns", "certificate", "search_engines"] } = params;
    
    const subdomainPrompt = `Generate a comprehensive subdomain discovery strategy for: ${domain}

Techniques to simulate:
${techniques.map(t => `- ${t}`).join('\n')}

Provide realistic subdomain enumeration results including:
1. Common subdomains (www, mail, ftp, admin, api, dev, test, staging)
2. Service-specific subdomains (jenkins, gitlab, jira, confluence)
3. Geographic subdomains (us, eu, asia)
4. Department subdomains (hr, finance, support)
5. Infrastructure subdomains (vpn, remote, portal)

Format as JSON with subdomain details, services, and security implications.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: subdomainPrompt }],
      { jsonMode: true, temperature: 0.4 }
    );

    const results = JSON.parse(response);
    
    return {
      domain,
      subdomains: results.subdomains || [],
      techniques: techniques,
      discoveryStats: {
        total: results.subdomains?.length || 0,
        highValue: results.subdomains?.filter((s: any) => s.riskLevel === "high").length || 0,
        services: results.services || []
      },
      attackSurface: this.assessAttackSurface(results),
      timestamp: new Date()
    };
  }

  private async createOSINTStrategy(params: { target: string, objectives: string[] }): Promise<any> {
    const { target, objectives } = params;
    
    return await aiService.generateOSINTStrategy(target, objectives, {
      passive: true,
      sources: ["search_engines", "social_media", "public_records", "certificate_transparency"],
      timeframe: "2-4 weeks"
    });
  }

  private async analyzeSocialMedia(params: { target: string, platforms?: string[] }): Promise<any> {
    const { target, platforms = ["linkedin", "twitter", "github", "facebook"] } = params;
    
    const socialPrompt = `Analyze social media presence and digital footprint for: ${target}

Platforms to analyze: ${platforms.join(", ")}

Provide comprehensive analysis including:
1. Employee identification and roles
2. Technology mentions and preferences
3. Company events and announcements
4. Security awareness indicators
5. Potential social engineering vectors
6. Information leakage assessment

IMPORTANT: Only analyze publicly available information. This is for defensive security awareness.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: socialPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const analysis = JSON.parse(response);
    
    return {
      target,
      platforms,
      analysis,
      socialEngVectors: analysis.vectors || [],
      informationLeakage: analysis.leakage || [],
      securityAwareness: analysis.awareness || "unknown",
      recommendations: [
        "Implement social media security policies",
        "Conduct security awareness training",
        "Monitor digital footprint regularly",
        "Review information sharing practices"
      ],
      timestamp: new Date()
    };
  }

  private async mapInfrastructure(params: { target: string }): Promise<any> {
    const { target } = params;
    
    const infraPrompt = `Map infrastructure and technology stack for: ${target}

Analyze and identify:
1. Web technologies and frameworks
2. Server infrastructure and hosting
3. Content delivery networks (CDN)
4. Security technologies (WAF, DDoS protection)
5. Third-party integrations
6. Cloud services and providers
7. Network architecture patterns

Provide detailed infrastructure map with security implications.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: infraPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const infrastructure = JSON.parse(response);
    
    return {
      target,
      infrastructure,
      technologies: infrastructure.technologies || [],
      cloudServices: infrastructure.cloudServices || [],
      securityControls: infrastructure.securityControls || [],
      vulnerabilities: infrastructure.potentialVulns || [],
      attackVectors: this.identifyAttackVectors(infrastructure),
      timestamp: new Date()
    };
  }

  private async correlateThreatIntel(params: { target: string, indicators?: string[] }): Promise<any> {
    const { target, indicators = [] } = params;
    
    const threatPrompt = `Correlate threat intelligence for: ${target}

Indicators to analyze: ${indicators.join(", ")}

Provide threat intelligence correlation including:
1. Historical incidents and breaches
2. Known threat actor activity
3. Industry-specific threats
4. Vulnerability trends
5. Attack pattern analysis
6. Risk assessment based on threat landscape

Format as comprehensive threat intelligence report.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: threatPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const threatIntel = JSON.parse(response);
    
    return {
      target,
      threatIntelligence: threatIntel,
      riskScore: this.calculateThreatRisk(threatIntel),
      recommendations: this.generateThreatMitigations(threatIntel),
      monitoringRules: this.generateMonitoringRules(threatIntel),
      timestamp: new Date()
    };
  }

  private assessDomainRisk(analysis: any): "low" | "medium" | "high" | "critical" {
    // Simple risk assessment logic
    let riskFactors = 0;
    
    if (analysis.outdatedTech) riskFactors++;
    if (analysis.exposedServices) riskFactors++;
    if (analysis.weakSecurity) riskFactors++;
    if (analysis.historicalIssues) riskFactors++;
    
    if (riskFactors >= 3) return "high";
    if (riskFactors >= 2) return "medium";
    return "low";
  }

  private generateReconRecommendations(analysis: any): string[] {
    return [
      "Continue with subdomain enumeration",
      "Analyze identified services for vulnerabilities",
      "Review security headers and configurations",
      "Monitor for changes in infrastructure"
    ];
  }

  private assessAttackSurface(results: any): any {
    return {
      totalEndpoints: results.subdomains?.length || 0,
      exposedServices: results.services?.length || 0,
      riskLevel: "medium",
      priorityTargets: results.subdomains?.filter((s: any) => s.riskLevel === "high") || []
    };
  }

  private identifyAttackVectors(infrastructure: any): string[] {
    return [
      "Web application vulnerabilities",
      "Misconfigured services",
      "Outdated software components",
      "Weak authentication mechanisms",
      "Information disclosure"
    ];
  }

  private calculateThreatRisk(threatIntel: any): number {
    // Risk score from 1-10
    return Math.min(10, Math.max(1, (threatIntel.severityScore || 5)));
  }

  private generateThreatMitigations(threatIntel: any): string[] {
    return [
      "Implement threat monitoring and detection",
      "Update security controls based on threat landscape",
      "Conduct targeted security assessments",
      "Enhance incident response capabilities"
    ];
  }

  private generateMonitoringRules(threatIntel: any): any[] {
    return [
      {
        type: "sigma",
        rule: "Monitor for suspicious domain resolutions",
        indicators: threatIntel.iocs || []
      },
      {
        type: "yara",
        rule: "Detect known threat actor tools",
        patterns: threatIntel.patterns || []
      }
    ];
  }
}