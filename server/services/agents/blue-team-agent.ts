import { BaseAgent, AgentTask, AgentContext, AgentCapability } from "./base-agent";
import { aiService } from "../ai";

export class BlueTeamAgent extends BaseAgent {
  constructor() {
    super("Blue Team Agent", "Expert in defense, detection, and security monitoring");
    
    this.capabilities = [
      {
        name: "detection_engineering",
        description: "Create detection rules and monitoring strategies",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "siem_rules",
        description: "Generate SIEM rules (Sigma, YARA, Suricata)",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "threat_hunting",
        description: "Develop threat hunting queries and methodologies",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "incident_response",
        description: "Create incident response playbooks and procedures",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "security_monitoring",
        description: "Design security monitoring and alerting strategies",
        riskLevel: "low",
        requiresApproval: false
      },
      {
        name: "mitigation_analysis",
        description: "Analyze and recommend security mitigations",
        riskLevel: "low",
        requiresApproval: false
      }
    ];
  }

  protected getSystemPrompt(): string {
    return `You are the Blue Team Agent, an expert in cybersecurity defense, detection, and monitoring.

Your specialties include:
- Detection engineering and rule creation
- SIEM rule development (Sigma, YARA, Suricata)
- Threat hunting methodologies
- Incident response planning
- Security monitoring and alerting
- Mitigation strategy development
- Security control assessment

You focus on:
- Proactive threat detection
- Automated security monitoring
- Incident response optimization
- Defense strategy improvement
- Security tool integration
- Team training and procedures

You collaborate closely with other agents to provide comprehensive defense strategies.`;
  }

  async executeTask(task: AgentTask, context: AgentContext): Promise<any> {
    const startTime = new Date();
    
    try {
      let result;
      
      switch (task.type) {
        case "detection_engineering":
          result = await this.engineerDetection(task.parameters);
          break;
        case "siem_rules":
          result = await this.generateSIEMRules(task.parameters);
          break;
        case "threat_hunting":
          result = await this.developThreatHunting(task.parameters);
          break;
        case "incident_response":
          result = await this.createIncidentResponse(task.parameters);
          break;
        case "security_monitoring":
          result = await this.designMonitoring(task.parameters);
          break;
        case "mitigation_analysis":
          result = await this.analyzeMitigations(task.parameters);
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

  private async engineerDetection(params: {
    threat: string,
    environment: string,
    technologies: string[]
  }): Promise<any> {
    const { threat, environment, technologies } = params;
    
    const detectionPrompt = `Engineer comprehensive detection strategy:

Threat: ${threat}
Environment: ${environment}
Technologies: ${technologies.join(", ")}

Design detection strategy including:
1. Attack technique analysis
2. Detection data sources
3. Detection logic and rules
4. Alert correlation strategies
5. False positive reduction
6. Detection coverage gaps
7. Monitoring infrastructure requirements
8. Validation and testing procedures

Provide detailed detection engineering framework.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: detectionPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const detection = JSON.parse(response);
    
    return {
      threat,
      environment,
      technologies,
      detectionStrategy: detection,
      dataSources: detection.dataSources || [],
      detectionRules: detection.rules || [],
      correlationRules: detection.correlationRules || [],
      coverageMatrix: this.generateCoverageMatrix(detection),
      testingProcedures: detection.testing || [],
      timestamp: new Date()
    };
  }

  private async generateSIEMRules(params: {
    ruleType: "sigma" | "yara" | "suricata" | "kql" | "splunk",
    threat: string,
    indicators: string[]
  }): Promise<any> {
    const { ruleType, threat, indicators } = params;
    
    const rulePrompt = `Generate ${ruleType.toUpperCase()} detection rule:

Threat: ${threat}
Indicators: ${indicators.join(", ")}

Create comprehensive detection rule including:
1. Rule metadata and description
2. Detection logic and conditions
3. Field mappings and data sources
4. Severity and priority levels
5. False positive considerations
6. Testing and validation steps
7. Tuning recommendations
8. Related rules and correlation

Provide production-ready ${ruleType} rule with documentation.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: rulePrompt }],
      { jsonMode: true, temperature: 0.2 }
    );

    const ruleSet = JSON.parse(response);
    
    return {
      ruleType,
      threat,
      indicators,
      rules: ruleSet.rules || [],
      metadata: ruleSet.metadata || {},
      documentation: ruleSet.documentation || "",
      testCases: ruleSet.testCases || [],
      tuningGuidelines: ruleSet.tuning || [],
      deployment: this.generateDeploymentGuidance(ruleType, ruleSet),
      timestamp: new Date()
    };
  }

  private async developThreatHunting(params: {
    hypothesis: string,
    environment: string,
    dataSources: string[]
  }): Promise<any> {
    const { hypothesis, environment, dataSources } = params;
    
    const huntingPrompt = `Develop threat hunting methodology:

Hypothesis: ${hypothesis}
Environment: ${environment}
Data Sources: ${dataSources.join(", ")}

Create comprehensive hunting approach including:
1. Hypothesis refinement and breakdown
2. Data collection strategies
3. Analysis techniques and queries
4. Baseline establishment methods
5. Anomaly detection approaches
6. Investigation workflows
7. Evidence collection procedures
8. Hunting metrics and success criteria

Provide detailed threat hunting playbook.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: huntingPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const hunting = JSON.parse(response);
    
    return {
      hypothesis,
      environment,
      dataSources,
      huntingMethodology: hunting,
      queries: hunting.queries || [],
      analytics: hunting.analytics || [],
      workflows: hunting.workflows || [],
      metrics: hunting.metrics || {},
      documentation: this.generateHuntingDocumentation(hunting),
      timestamp: new Date()
    };
  }

  private async createIncidentResponse(params: {
    incidentType: string,
    severity: string,
    environment: string
  }): Promise<any> {
    const { incidentType, severity, environment } = params;
    
    const irPrompt = `Create incident response playbook:

Incident Type: ${incidentType}
Severity: ${severity}
Environment: ${environment}

Develop comprehensive playbook including:
1. Incident classification and triage
2. Initial response procedures
3. Investigation steps and evidence collection
4. Containment and mitigation actions
5. Eradication and recovery procedures
6. Communication and escalation paths
7. Legal and compliance considerations
8. Post-incident analysis and lessons learned

Provide detailed incident response framework.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: irPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const playbook = JSON.parse(response);
    
    return {
      incidentType,
      severity,
      environment,
      playbook,
      procedures: playbook.procedures || [],
      escalation: playbook.escalation || {},
      communications: playbook.communications || [],
      timeline: playbook.timeline || {},
      checklists: this.generateIncidentChecklists(playbook),
      timestamp: new Date()
    };
  }

  private async designMonitoring(params: {
    assets: string[],
    threats: string[],
    compliance?: string[]
  }): Promise<any> {
    const { assets, threats, compliance = [] } = params;
    
    const monitoringPrompt = `Design security monitoring strategy:

Assets: ${assets.join(", ")}
Threats: ${threats.join(", ")}
Compliance: ${compliance.join(", ")}

Create comprehensive monitoring design including:
1. Asset inventory and classification
2. Threat model and risk assessment
3. Monitoring architecture and data flows
4. Alert prioritization and thresholds
5. Dashboard and visualization design
6. Automated response capabilities
7. Compliance monitoring requirements
8. Performance and scalability considerations

Provide detailed monitoring framework.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: monitoringPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const monitoring = JSON.parse(response);
    
    return {
      assets,
      threats,
      compliance,
      monitoringStrategy: monitoring,
      architecture: monitoring.architecture || {},
      alerts: monitoring.alerts || [],
      dashboards: monitoring.dashboards || [],
      automation: monitoring.automation || {},
      metrics: this.generateMonitoringMetrics(monitoring),
      timestamp: new Date()
    };
  }

  private async analyzeMitigations(params: {
    vulnerabilities: string[],
    environment: string,
    constraints?: string[]
  }): Promise<any> {
    const { vulnerabilities, environment, constraints = [] } = params;
    
    const mitigationPrompt = `Analyze security mitigations:

Vulnerabilities: ${vulnerabilities.join(", ")}
Environment: ${environment}
Constraints: ${constraints.join(", ")}

Provide comprehensive mitigation analysis including:
1. Vulnerability assessment and prioritization
2. Mitigation strategy options
3. Implementation complexity and cost
4. Effectiveness assessment
5. Risk reduction calculations
6. Compensating controls
7. Monitoring and validation approaches
8. Long-term security roadmap

Develop prioritized mitigation recommendations.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: mitigationPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const mitigations = JSON.parse(response);
    
    return {
      vulnerabilities,
      environment,
      constraints,
      mitigationAnalysis: mitigations,
      recommendations: mitigations.recommendations || [],
      priorities: mitigations.priorities || [],
      roadmap: mitigations.roadmap || {},
      costBenefit: mitigations.costBenefit || {},
      implementation: this.generateImplementationPlan(mitigations),
      timestamp: new Date()
    };
  }

  private generateCoverageMatrix(detection: any): any {
    return {
      techniques: detection.techniques || [],
      coverage: "75%", // Example coverage percentage
      gaps: detection.gaps || [],
      recommendations: detection.recommendations || []
    };
  }

  private generateDeploymentGuidance(ruleType: string, ruleSet: any): any {
    return {
      platform: ruleType,
      deployment: {
        steps: [`Deploy ${ruleType} rules to SIEM platform`, "Configure alert routing", "Set up dashboards"],
        configuration: ruleSet.configuration || {},
        testing: ["Test with known true positives", "Validate false positive rate"],
        monitoring: ["Monitor rule performance", "Track alert volume"]
      }
    };
  }

  private generateHuntingDocumentation(hunting: any): any {
    return {
      overview: hunting.overview || "Threat hunting methodology",
      procedures: hunting.procedures || [],
      tools: hunting.tools || [],
      references: hunting.references || []
    };
  }

  private generateIncidentChecklists(playbook: any): any[] {
    return [
      {
        phase: "Detection",
        checklist: ["Alert triaged", "Incident classified", "Stakeholders notified"]
      },
      {
        phase: "Investigation",
        checklist: ["Evidence collected", "Timeline established", "Scope determined"]
      },
      {
        phase: "Containment",
        checklist: ["Threat contained", "Systems isolated", "Backup verified"]
      },
      {
        phase: "Recovery",
        checklist: ["Systems restored", "Monitoring enhanced", "Lessons documented"]
      }
    ];
  }

  private generateMonitoringMetrics(monitoring: any): any {
    return {
      detection: {
        alertVolume: "Daily alert count",
        falsePositiveRate: "FP percentage",
        meanTimeToDetection: "MTTD in minutes"
      },
      response: {
        meanTimeToResponse: "MTTR in minutes",
        escalationRate: "Escalation percentage",
        resolutionRate: "Resolution percentage"
      }
    };
  }

  private generateImplementationPlan(mitigations: any): any {
    return {
      phases: [
        {
          phase: "Quick Wins",
          duration: "1-2 weeks",
          mitigations: mitigations.quickWins || []
        },
        {
          phase: "Medium Term",
          duration: "1-3 months",
          mitigations: mitigations.mediumTerm || []
        },
        {
          phase: "Long Term",
          duration: "3-12 months",
          mitigations: mitigations.longTerm || []
        }
      ]
    };
  }
}