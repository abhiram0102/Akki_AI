import { BaseAgent, AgentTask, AgentContext, AgentCapability } from "./base-agent";
import { aiService } from "../ai";

export class ReportAgent extends BaseAgent {
  constructor() {
    super("Report Agent", "Expert in security reporting and documentation");
    
    this.capabilities = [
      {
        name: "pentest_report",
        description: "Generate comprehensive penetration testing reports",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "vulnerability_assessment",
        description: "Create detailed vulnerability assessment reports",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "executive_summary",
        description: "Generate executive summaries for security assessments",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "compliance_report",
        description: "Create compliance and audit reports",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "incident_report",
        description: "Generate incident analysis and forensic reports",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "threat_intelligence",
        description: "Create threat intelligence and analysis reports",
        riskLevel: "low",
        requiresApproval: false
      }
    ];
  }

  protected getSystemPrompt(): string {
    return `You are the Report Agent, an expert in cybersecurity reporting and technical documentation.

Your specialties include:
- Penetration testing reports with MITRE ATT&CK mapping
- Vulnerability assessment documentation
- Executive summaries and business impact analysis
- Compliance and audit reporting
- Incident response and forensic reports
- Threat intelligence analysis

You focus on:
- Clear, professional communication
- Technical accuracy and detail
- Business impact articulation
- Actionable recommendations
- Industry standard frameworks
- Compliance requirements
- Executive-level insights

You collaborate with all agents to compile comprehensive security assessments.`;
  }

  async executeTask(task: AgentTask, context: AgentContext): Promise<any> {
    const startTime = new Date();
    
    try {
      let result;
      
      switch (task.type) {
        case "pentest_report":
          result = await this.generatePentestReport(task.parameters);
          break;
        case "vulnerability_assessment":
          result = await this.generateVulnAssessment(task.parameters);
          break;
        case "executive_summary":
          result = await this.generateExecutiveSummary(task.parameters);
          break;
        case "compliance_report":
          result = await this.generateComplianceReport(task.parameters);
          break;
        case "incident_report":
          result = await this.generateIncidentReport(task.parameters);
          break;
        case "threat_intelligence":
          result = await this.generateThreatIntelReport(task.parameters);
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

  private async generatePentestReport(params: {
    findings: any[],
    scope: string,
    methodology: string,
    executiveSummary?: string
  }): Promise<any> {
    const { findings, scope, methodology, executiveSummary } = params;
    
    return await aiService.generatePentestReport(findings, executiveSummary, scope);
  }

  private async generateVulnAssessment(params: {
    vulnerabilities: any[],
    scope: string,
    environment: string
  }): Promise<any> {
    const { vulnerabilities, scope, environment } = params;
    
    const assessmentPrompt = `Generate comprehensive vulnerability assessment report:

Scope: ${scope}
Environment: ${environment}
Vulnerabilities Count: ${vulnerabilities.length}

Create detailed assessment including:
1. Executive Summary
2. Assessment Overview and Methodology
3. Risk Summary and Statistics
4. Detailed Vulnerability Findings
5. Risk Rating and CVSS Scores
6. Remediation Recommendations
7. Prioritization Matrix
8. Compliance Impact Analysis
9. Appendices and Technical Details

Format as professional security assessment report.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: assessmentPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const report = JSON.parse(response);
    
    return {
      type: "vulnerability_assessment",
      scope,
      environment,
      vulnerabilities,
      report,
      statistics: this.generateVulnStatistics(vulnerabilities),
      riskMatrix: this.generateRiskMatrix(vulnerabilities),
      timeline: this.generateRemediationTimeline(vulnerabilities),
      compliance: this.analyzeComplianceImpact(vulnerabilities),
      timestamp: new Date()
    };
  }

  private async generateExecutiveSummary(params: {
    assessmentType: string,
    findings: any[],
    businessContext: string,
    audience: string
  }): Promise<any> {
    const { assessmentType, findings, businessContext, audience } = params;
    
    const summaryPrompt = `Generate executive summary for security assessment:

Assessment Type: ${assessmentType}
Business Context: ${businessContext}
Audience: ${audience}
Findings Count: ${findings.length}

Create executive-level summary including:
1. Assessment Overview and Objectives
2. Key Findings and Risk Summary
3. Business Impact Analysis
4. Strategic Recommendations
5. Resource Requirements
6. Implementation Timeline
7. Risk Mitigation Priorities
8. Return on Investment Analysis

Focus on business impact and strategic decision-making.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: summaryPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const summary = JSON.parse(response);
    
    return {
      assessmentType,
      businessContext,
      audience,
      summary,
      keyMetrics: this.generateExecutiveMetrics(findings),
      recommendations: summary.recommendations || [],
      riskDashboard: this.generateRiskDashboard(findings),
      businessCase: summary.businessCase || {},
      timestamp: new Date()
    };
  }

  private async generateComplianceReport(params: {
    framework: string,
    scope: string,
    findings: any[],
    requirements: string[]
  }): Promise<any> {
    const { framework, scope, findings, requirements } = params;
    
    const compliancePrompt = `Generate compliance assessment report:

Framework: ${framework}
Scope: ${scope}
Requirements: ${requirements.join(", ")}
Findings Count: ${findings.length}

Create comprehensive compliance report including:
1. Compliance Framework Overview
2. Assessment Scope and Methodology
3. Compliance Status Summary
4. Gap Analysis and Findings
5. Risk Assessment and Impact
6. Remediation Roadmap
7. Policy and Procedure Recommendations
8. Continuous Monitoring Strategy

Provide detailed compliance gap analysis and remediation plan.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: compliancePrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const compliance = JSON.parse(response);
    
    return {
      framework,
      scope,
      requirements,
      findings,
      complianceReport: compliance,
      status: this.calculateComplianceStatus(compliance),
      gaps: compliance.gaps || [],
      remediation: compliance.remediation || {},
      roadmap: this.generateComplianceRoadmap(compliance),
      timestamp: new Date()
    };
  }

  private async generateIncidentReport(params: {
    incident: any,
    timeline: any[],
    impact: any,
    response: any
  }): Promise<any> {
    const { incident, timeline, impact, response } = params;
    
    const incidentPrompt = `Generate comprehensive incident analysis report:

Incident: ${JSON.stringify(incident)}
Timeline Events: ${timeline.length}
Impact Assessment: ${JSON.stringify(impact)}
Response Actions: ${JSON.stringify(response)}

Create detailed incident report including:
1. Incident Overview and Classification
2. Timeline of Events
3. Root Cause Analysis
4. Impact Assessment
5. Response Actions and Effectiveness
6. Lessons Learned
7. Preventive Measures
8. Process Improvements
9. Technical Recommendations
10. Post-Incident Monitoring

Provide comprehensive incident analysis and improvement recommendations.`;

    const responseData = await aiService.chatCompletion(
      [{ role: "user", content: incidentPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const report = JSON.parse(responseData);
    
    return {
      incident,
      timeline,
      impact,
      response,
      incidentReport: report,
      rootCause: report.rootCause || {},
      lessonsLearned: report.lessonsLearned || [],
      improvements: report.improvements || [],
      monitoring: this.generatePostIncidentMonitoring(report),
      timestamp: new Date()
    };
  }

  private async generateThreatIntelReport(params: {
    threats: any[],
    period: string,
    sources: string[],
    analysis: any
  }): Promise<any> {
    const { threats, period, sources, analysis } = params;
    
    const threatPrompt = `Generate threat intelligence analysis report:

Analysis Period: ${period}
Threat Count: ${threats.length}
Sources: ${sources.join(", ")}
Analysis Data: ${JSON.stringify(analysis)}

Create comprehensive threat intelligence report including:
1. Executive Summary
2. Threat Landscape Overview
3. Key Threat Actors and Campaigns
4. Attack Trends and Patterns
5. IOC Analysis and Attribution
6. Sector-Specific Threats
7. Emerging Threats and Technologies
8. Defensive Recommendations
9. Strategic Intelligence Insights
10. Tactical Response Guidelines

Provide actionable threat intelligence for security operations.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: threatPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const intel = JSON.parse(response);
    
    return {
      period,
      threats,
      sources,
      analysis,
      threatIntelReport: intel,
      trends: intel.trends || [],
      actors: intel.actors || [],
      recommendations: intel.recommendations || [],
      iocs: this.extractIOCs(intel),
      timestamp: new Date()
    };
  }

  private generateVulnStatistics(vulnerabilities: any[]): any {
    const severityCounts = vulnerabilities.reduce((acc, vuln) => {
      acc[vuln.severity] = (acc[vuln.severity] || 0) + 1;
      return acc;
    }, {});

    return {
      total: vulnerabilities.length,
      severityBreakdown: severityCounts,
      avgCVSS: vulnerabilities.reduce((sum, v) => sum + (v.cvss || 0), 0) / vulnerabilities.length,
      categories: this.categorizeVulnerabilities(vulnerabilities)
    };
  }

  private generateRiskMatrix(vulnerabilities: any[]): any {
    return {
      critical: vulnerabilities.filter(v => v.severity === "critical").length,
      high: vulnerabilities.filter(v => v.severity === "high").length,
      medium: vulnerabilities.filter(v => v.severity === "medium").length,
      low: vulnerabilities.filter(v => v.severity === "low").length,
      riskScore: this.calculateOverallRisk(vulnerabilities)
    };
  }

  private generateRemediationTimeline(vulnerabilities: any[]): any {
    return {
      immediate: vulnerabilities.filter(v => v.severity === "critical"),
      shortTerm: vulnerabilities.filter(v => v.severity === "high"),
      mediumTerm: vulnerabilities.filter(v => v.severity === "medium"),
      longTerm: vulnerabilities.filter(v => v.severity === "low")
    };
  }

  private analyzeComplianceImpact(vulnerabilities: any[]): any {
    return {
      affected: vulnerabilities.filter(v => v.compliance?.length > 0),
      frameworks: ["PCI-DSS", "HIPAA", "SOX", "GDPR"],
      risks: ["Data breach", "Regulatory fines", "Business disruption"]
    };
  }

  private generateExecutiveMetrics(findings: any[]): any {
    return {
      totalFindings: findings.length,
      highRiskFindings: findings.filter(f => f.riskLevel === "high").length,
      businessImpact: "Medium",
      estimatedCost: "$50,000 - $200,000",
      timeToRemediate: "3-6 months"
    };
  }

  private generateRiskDashboard(findings: any[]): any {
    return {
      overallRisk: "Medium",
      trendDirection: "Stable",
      keyRisks: findings.slice(0, 5),
      mitigationProgress: "25%"
    };
  }

  private calculateComplianceStatus(compliance: any): any {
    return {
      overall: "Partially Compliant",
      percentage: 75,
      gaps: compliance.gaps?.length || 0,
      recommendations: compliance.recommendations?.length || 0
    };
  }

  private generateComplianceRoadmap(compliance: any): any {
    return {
      phase1: {
        duration: "1-3 months",
        priority: "High",
        tasks: compliance.quickWins || []
      },
      phase2: {
        duration: "3-6 months",
        priority: "Medium",
        tasks: compliance.mediumTerm || []
      },
      phase3: {
        duration: "6-12 months",
        priority: "Low",
        tasks: compliance.longTerm || []
      }
    };
  }

  private generatePostIncidentMonitoring(report: any): any {
    return {
      indicators: report.indicators || [],
      alertRules: report.alertRules || [],
      dashboards: ["Incident metrics", "Response times", "Prevention effectiveness"],
      reviews: "Monthly incident review meetings"
    };
  }

  private extractIOCs(intel: any): any {
    return {
      domains: intel.domains || [],
      ips: intel.ips || [],
      hashes: intel.hashes || [],
      urls: intel.urls || []
    };
  }

  private categorizeVulnerabilities(vulnerabilities: any[]): any {
    return vulnerabilities.reduce((acc, vuln) => {
      const category = vuln.category || "Other";
      acc[category] = (acc[category] || 0) + 1;
      return acc;
    }, {});
  }

  private calculateOverallRisk(vulnerabilities: any[]): number {
    const weights = { critical: 10, high: 7, medium: 4, low: 1 };
    const totalWeight = vulnerabilities.reduce((sum, v) => 
      sum + (weights[v.severity as keyof typeof weights] || 0), 0);
    return Math.min(10, totalWeight / vulnerabilities.length);
  }
}