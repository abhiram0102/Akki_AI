import { aiService } from "../ai";
import { storage } from "../../storage";

export interface AgentCapability {
  name: string;
  description: string;
  riskLevel: "low" | "medium" | "high" | "critical";
  requiresApproval: boolean;
}

export interface AgentTask {
  id: string;
  type: string;
  parameters: any;
  status: "pending" | "running" | "completed" | "failed";
  result?: any;
  error?: string;
  startTime?: Date;
  endTime?: Date;
}

export interface AgentContext {
  userId: string;
  sessionId: string;
  workspace: string;
  previousTasks: AgentTask[];
  collaboratingAgents: string[];
}

export abstract class BaseAgent {
  protected name: string;
  protected description: string;
  protected capabilities: AgentCapability[];

  constructor(name: string, description: string) {
    this.name = name;
    this.description = description;
    this.capabilities = [];
  }

  abstract executeTask(task: AgentTask, context: AgentContext): Promise<any>;

  protected abstract getSystemPrompt(): string;

  async planTasks(objective: string, context: AgentContext): Promise<AgentTask[]> {
    const planningPrompt = `${this.getSystemPrompt()}

You are planning tasks for: ${objective}

Available capabilities:
${this.capabilities.map(cap => `- ${cap.name}: ${cap.description} (Risk: ${cap.riskLevel})`).join("\n")}

Return a JSON object with a "tasks" array where each task has: id, type, parameters, estimatedDuration, riskLevel.`;

    try {
      const response = await aiService.chatCompletion(
        [{ role: "user", content: planningPrompt }],
        { jsonMode: true, temperature: 0.3 }
      );
      const plan = JSON.parse(response);
      return (plan.tasks || []).map((task: any) => ({ ...task, status: "pending" as const }));
    } catch (error) {
      console.error(`Task planning error for ${this.name}:`, error);
      return [];
    }
  }

  async collaborateWithAgent(
    targetAgent: string,
    taskType: string,
    data: any,
    context: AgentContext
  ): Promise<any> {
    const collaborationRequest = {
      fromAgent: this.name,
      toAgent: targetAgent,
      taskType,
      data,
      context,
      timestamp: new Date(),
    };

    try {
      await (storage as any).createCollaborationLog?.({
        sessionId: context.sessionId,
        fromAgent: this.name,
        toAgent: targetAgent,
        taskType,
        data: JSON.stringify(data),
        status: "pending",
      });
    } catch {
      // Log collaboration attempt even if storage method not available
    }

    return collaborationRequest;
  }

  getCapabilities(): AgentCapability[] {
    return this.capabilities;
  }

  getName(): string {
    return this.name;
  }

  getDescription(): string {
    return this.description;
  }
}
