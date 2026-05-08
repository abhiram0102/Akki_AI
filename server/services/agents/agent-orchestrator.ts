import { BaseAgent, AgentTask, AgentContext } from "./base-agent";
import { ReconAgent } from "./recon-agent";
import { ExploitationAgent } from "./exploitation-agent";
import { BlueTeamAgent } from "./blue-team-agent";
import { ReportAgent } from "./report-agent";
import { aiService } from "../ai";
import { storage } from "../../storage";

export interface WorkflowDefinition {
  id: string;
  name: string;
  description: string;
  agents: string[];
  phases: WorkflowPhase[];
  approvalRequired: boolean;
}

export interface WorkflowPhase {
  id: string;
  name: string;
  agent: string;
  tasks: string[];
  dependencies: string[];
  parallelizable: boolean;
}

export interface WorkflowExecution {
  id: string;
  workflowId: string;
  userId: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  currentPhase: string;
  results: Map<string, any>;
  startTime: Date;
  endTime?: Date;
}

export class AgentOrchestrator {
  private agents: Map<string, BaseAgent>;
  private workflows: Map<string, WorkflowDefinition>;
  private activeExecutions: Map<string, WorkflowExecution>;

  constructor() {
    this.agents = new Map();
    this.workflows = new Map();
    this.activeExecutions = new Map();
    
    this.initializeAgents();
    this.initializeWorkflows();
  }

  private initializeAgents(): void {
    this.agents.set("recon", new ReconAgent());
    this.agents.set("exploitation", new ExploitationAgent());
    this.agents.set("blue-team", new BlueTeamAgent());
    this.agents.set("report", new ReportAgent());
  }

  private initializeWorkflows(): void {
    // Full Penetration Test Workflow
    this.workflows.set("full-pentest", {
      id: "full-pentest",
      name: "Complete Penetration Test",
      description: "End-to-end penetration testing from reconnaissance to reporting",
      agents: ["recon", "exploitation", "blue-team", "report"],
      approvalRequired: true,
      phases: [
        {
          id: "reconnaissance",
          name: "Reconnaissance & OSINT",
          agent: "recon",
          tasks: ["domain_reconnaissance", "subdomain_discovery", "infrastructure_mapping"],
          dependencies: [],
          parallelizable: true
        },
        {
          id: "vulnerability-analysis",
          name: "Vulnerability Analysis",
          agent: "exploitation",
          tasks: ["vulnerability_analysis", "exploit_generation"],
          dependencies: ["reconnaissance"],
          parallelizable: false
        },
        {
          id: "defense-analysis",
          name: "Defense Assessment",
          agent: "blue-team",
          tasks: ["detection_engineering", "mitigation_analysis"],
          dependencies: ["vulnerability-analysis"],
          parallelizable: true
        },
        {
          id: "reporting",
          name: "Report Generation",
          agent: "report",
          tasks: ["pentest_report", "executive_summary"],
          dependencies: ["defense-analysis"],
          parallelizable: false
        }
      ]
    });

    // Threat Intelligence Workflow
    this.workflows.set("threat-intel", {
      id: "threat-intel",
      name: "Threat Intelligence Analysis",
      description: "Comprehensive threat intelligence gathering and analysis",
      agents: ["recon", "blue-team", "report"],
      approvalRequired: false,
      phases: [
        {
          id: "osint-gathering",
          name: "OSINT Collection",
          agent: "recon",
          tasks: ["osint_strategy", "threat_intelligence"],
          dependencies: [],
          parallelizable: true
        },
        {
          id: "threat-hunting",
          name: "Threat Hunting",
          agent: "blue-team",
          tasks: ["threat_hunting", "siem_rules"],
          dependencies: ["osint-gathering"],
          parallelizable: true
        },
        {
          id: "intel-reporting",
          name: "Intelligence Reporting",
          agent: "report",
          tasks: ["threat_intelligence"],
          dependencies: ["threat-hunting"],
          parallelizable: false
        }
      ]
    });

    // Incident Response Workflow
    this.workflows.set("incident-response", {
      id: "incident-response",
      name: "Incident Response Analysis",
      description: "Comprehensive incident analysis and response planning",
      agents: ["exploitation", "blue-team", "report"],
      approvalRequired: false,
      phases: [
        {
          id: "malware-analysis",
          name: "Malware Analysis",
          agent: "exploitation",
          tasks: ["malware_analysis", "vulnerability_analysis"],
          dependencies: [],
          parallelizable: true
        },
        {
          id: "response-planning",
          name: "Response Planning",
          agent: "blue-team",
          tasks: ["incident_response", "detection_engineering"],
          dependencies: ["malware-analysis"],
          parallelizable: true
        },
        {
          id: "incident-reporting",
          name: "Incident Reporting",
          agent: "report",
          tasks: ["incident_report"],
          dependencies: ["response-planning"],
          parallelizable: false
        }
      ]
    });
  }

  async executeWorkflow(
    workflowId: string,
    parameters: any,
    context: AgentContext
  ): Promise<string> {
    const workflow = this.workflows.get(workflowId);
    if (!workflow) {
      throw new Error(`Workflow not found: ${workflowId}`);
    }

    const executionId = `exec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    const execution: WorkflowExecution = {
      id: executionId,
      workflowId,
      userId: context.userId,
      status: "pending",
      currentPhase: workflow.phases[0].id,
      results: new Map(),
      startTime: new Date()
    };

    this.activeExecutions.set(executionId, execution);

    // Check if workflow requires approval
    if (workflow.approvalRequired) {
      await this.requestWorkflowApproval(execution, workflow, parameters);
      return executionId;
    }

    // Start execution
    this.startWorkflowExecution(execution, workflow, parameters, context);
    return executionId;
  }

  private async requestWorkflowApproval(
    execution: WorkflowExecution,
    workflow: WorkflowDefinition,
    parameters: any
  ): Promise<void> {
    // Create approval request (stored in-memory for now)
    console.log(`[AgentOrchestrator] Approval required for workflow: ${workflow.name} (execution: ${execution.id})`);
    execution.status = "paused";
  }

  private async startWorkflowExecution(
    execution: WorkflowExecution,
    workflow: WorkflowDefinition,
    parameters: any,
    context: AgentContext
  ): Promise<void> {
    execution.status = "running";
    
    try {
      for (const phase of workflow.phases) {
        await this.executePhase(execution, phase, parameters, context);
        execution.currentPhase = phase.id;
      }
      
      execution.status = "completed";
      execution.endTime = new Date();
      
    } catch (error) {
      execution.status = "failed";
      execution.endTime = new Date();
      console.error(`Workflow execution failed:`, error);
    }
  }

  private async executePhase(
    execution: WorkflowExecution,
    phase: WorkflowPhase,
    parameters: any,
    context: AgentContext
  ): Promise<void> {
    const agent = this.agents.get(phase.agent);
    if (!agent) {
      throw new Error(`Agent not found: ${phase.agent}`);
    }

    const phaseResults = [];

    if (phase.parallelizable) {
      // Execute tasks in parallel
      const taskPromises = phase.tasks.map(async (taskType) => {
        const task: AgentTask = {
          id: `${phase.id}_${taskType}_${Date.now()}`,
          type: taskType,
          parameters: this.prepareTaskParameters(taskType, parameters, execution.results),
          status: "pending"
        };

        return await agent.executeTask(task, context);
      });

      const results = await Promise.all(taskPromises);
      phaseResults.push(...results);
    } else {
      // Execute tasks sequentially
      for (const taskType of phase.tasks) {
        const task: AgentTask = {
          id: `${phase.id}_${taskType}_${Date.now()}`,
          type: taskType,
          parameters: this.prepareTaskParameters(taskType, parameters, execution.results),
          status: "pending"
        };

        const result = await agent.executeTask(task, context);
        phaseResults.push(result);
      }
    }

    execution.results.set(phase.id, phaseResults);
  }

  private prepareTaskParameters(
    taskType: string,
    originalParameters: any,
    previousResults: Map<string, any>
  ): any {
    // Combine original parameters with results from previous phases
    const taskParameters = { ...originalParameters };

    // Add context from previous phases
    for (const [phaseId, results] of previousResults.entries()) {
      taskParameters[`${phaseId}_results`] = results;
    }

    return taskParameters;
  }

  async getWorkflowStatus(executionId: string): Promise<WorkflowExecution | null> {
    return this.activeExecutions.get(executionId) || null;
  }

  async pauseWorkflow(executionId: string): Promise<boolean> {
    const execution = this.activeExecutions.get(executionId);
    if (execution && execution.status === "running") {
      execution.status = "paused";
      return true;
    }
    return false;
  }

  async resumeWorkflow(executionId: string): Promise<boolean> {
    const execution = this.activeExecutions.get(executionId);
    if (execution && execution.status === "paused") {
      execution.status = "running";
      // Resume execution logic would go here
      return true;
    }
    return false;
  }

  async stopWorkflow(executionId: string): Promise<boolean> {
    const execution = this.activeExecutions.get(executionId);
    if (execution) {
      execution.status = "failed";
      execution.endTime = new Date();
      return true;
    }
    return false;
  }

  getAvailableWorkflows(): WorkflowDefinition[] {
    return Array.from(this.workflows.values());
  }

  getAgentCapabilities(agentName: string): any {
    const agent = this.agents.get(agentName);
    return agent ? {
      name: agent.getName(),
      description: agent.getDescription(),
      capabilities: agent.getCapabilities()
    } : null;
  }

  async planCustomWorkflow(
    objective: string,
    constraints: string[],
    context: AgentContext
  ): Promise<WorkflowDefinition> {
    const planningPrompt = `Create a custom cybersecurity workflow for the following objective:

Objective: ${objective}
Constraints: ${constraints.join(", ")}
Available Agents: Recon Agent, Exploitation Agent, Blue Team Agent, Report Agent

Design a workflow with:
1. Workflow name and description
2. Required agents and their roles
3. Sequential phases with dependencies
4. Task assignments per phase
5. Risk assessment and approval requirements
6. Expected deliverables

Available Agent Capabilities:
- Recon Agent: OSINT, domain reconnaissance, subdomain discovery, infrastructure mapping
- Exploitation Agent: Vulnerability analysis, exploit generation, payload crafting, attack simulation
- Blue Team Agent: Detection engineering, SIEM rules, threat hunting, incident response
- Report Agent: Pentest reports, vulnerability assessments, executive summaries, compliance reports

Format as workflow definition JSON.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: planningPrompt }],
      { jsonMode: true, temperature: 0.4 }
    );

    const workflowDef = JSON.parse(response);
    
    // Generate unique ID for custom workflow
    const customId = `custom_${Date.now()}`;
    workflowDef.id = customId;
    
    // Store custom workflow
    this.workflows.set(customId, workflowDef);
    
    return workflowDef;
  }

  async generateAgentCollaboration(
    primaryAgent: string,
    secondaryAgents: string[],
    task: string,
    context: AgentContext
  ): Promise<any> {
    const primary = this.agents.get(primaryAgent);
    if (!primary) {
      throw new Error(`Primary agent not found: ${primaryAgent}`);
    }

    const collaborators = secondaryAgents
      .map(name => this.agents.get(name))
      .filter(agent => agent !== undefined);

    const collaborationPrompt = `Plan agent collaboration for task: ${task}

Primary Agent: ${primary.getName()} - ${primary.getDescription()}
Secondary Agents: ${collaborators.map(a => `${a!.getName()} - ${a!.getDescription()}`).join(", ")}

Design collaboration strategy including:
1. Primary agent responsibilities
2. Secondary agent contributions
3. Information sharing protocols
4. Coordination checkpoints
5. Deliverable consolidation
6. Quality assurance steps

Provide detailed collaboration plan.`;

    const response = await aiService.chatCompletion(
      [{ role: "user", content: collaborationPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    return JSON.parse(response);
  }
}

export const agentOrchestrator = new AgentOrchestrator();