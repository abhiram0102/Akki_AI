import { storage } from "../storage";
import { aiService } from "./ai";
import { ragService } from "./rag";
import { toolsService } from "./tools";
import { emotionalAI } from "./emotional-ai";
import type { ToolRun } from "@shared/schema";

export interface AgentResponse {
  content: string;
  toolCalls?: Array<{
    toolName: string;
    arguments: any;
    status: "pending" | "approved" | "executed" | "failed";
    riskLevel: "low" | "medium" | "high";
  }>;
  plan?: AgentPlan;
  ragUsed?: boolean;
  sources?: string[];
  emotionalTone?: string;
}

export interface AgentPlan {
  goal: string;
  steps: AgentStep[];
  currentStep: number;
  status: "planning" | "executing" | "completed" | "failed";
  riskAssessment: "low" | "medium" | "high";
}

export interface AgentStep {
  id: string;
  description: string;
  toolName?: string;
  arguments?: any;
  status: "pending" | "executing" | "completed" | "failed" | "skipped";
  result?: any;
  requiresApproval?: boolean;
  riskLevel?: "low" | "medium" | "high";
}

export interface MessageContext {
  message: string;
  sessionId: string;
  userId: string;
  voiceInput?: boolean;
  previousMessages?: any[];
  context?: {
    emotionalTone?: string;
    workspace?: string;
    capabilities?: string[];
  };
}

class AgentService {
  async processMessage(context: MessageContext): Promise<AgentResponse> {
    try {
      const { message, sessionId, userId, voiceInput = false } = context;
      
      // Get user's emotional state for personalized responses
      const user = await storage.getUser(userId);
      const emotionalState = user?.emotionalState;
      
      // Get conversation history
      const recentMessages = await storage.getSessionMessages(sessionId, 10);
      
      // Determine if this requires RAG or tool usage
      const intent = await this.analyzeIntent(message, recentMessages);
      
      let agentResponse: AgentResponse = {
        content: "",
        ragUsed: false,
        sources: []
      };
      
      // Handle different intent types
      switch (intent.type) {
        case "rag_query":
          agentResponse = await this.handleRAGQuery(message, intent.entities);
          break;
          
        case "tool_execution":
          agentResponse = await this.handleToolExecution(message, intent.entities, sessionId);
          break;
          
        case "planning":
          agentResponse = await this.handlePlanning(message, intent.entities, sessionId);
          break;
          
        case "casual_chat":
        default:
          agentResponse = await this.handleCasualChat(message, emotionalState);
          break;
      }
      
      // Personalize response based on emotional state
      if (emotionalState) {
        agentResponse.content = await emotionalAI.generatePersonalizedResponse(
          userId,
          agentResponse.content,
          message
        );
        
        agentResponse.emotionalTone = this.determineResponseTone(emotionalState, intent.type);
      }
      
      // Update user memories based on interaction
      await this.updateMemories(userId, message, agentResponse, intent);
      
      return agentResponse;
    } catch (error) {
      console.error("Agent processing error:", error);
      return {
        content: "I apologize, but I'm experiencing some technical difficulties. Please try again.",
        ragUsed: false,
        sources: []
      };
    }
  }

  private async analyzeIntent(message: string, recentMessages: any[]): Promise<{
    type: "rag_query" | "tool_execution" | "planning" | "casual_chat";
    confidence: number;
    entities: any;
  }> {
    try {
      const conversationContext = recentMessages
        .slice(-5)
        .map(m => `${m.role}: ${m.content}`)
        .join('\n');
      
      const systemPrompt = `You are an intent classifier for a cybersecurity AI assistant. Analyze the user's message and classify the intent.

      Intent types:
      1. rag_query: User asking for information that might be in documents (CVEs, vulnerabilities, procedures)
      2. tool_execution: User wants to run security tools (nmap, domain intel, etc.)
      3. planning: User wants to plan an attack chain, investigation, or security assessment
      4. casual_chat: General conversation, greetings, or non-technical questions
      
      Consider the conversation context and respond in JSON format:
      {
        "type": "intent_type",
        "confidence": 0.95,
        "entities": {
          "targets": ["192.168.1.1"],
          "tools": ["nmap"],
          "topics": ["CVE-2024-1234"],
          "actions": ["scan", "analyze"]
        }
      }`;

      const response = await aiService.chatCompletion(
        [{ role: "user", content: `Context:\n${conversationContext}\n\nUser message: ${message}` }],
        {
          systemPrompt,
          jsonMode: true,
          temperature: 0.3
        }
      );
      
      const parsed = JSON.parse(response);
      return {
        type: parsed.type || "casual_chat",
        confidence: parsed.confidence || 0.5,
        entities: parsed.entities || {}
      };
    } catch (error) {
      console.error("Intent analysis error:", error);
      return {
        type: "casual_chat",
        confidence: 0.5,
        entities: {}
      };
    }
  }

  private async handleRAGQuery(message: string, entities: any): Promise<AgentResponse> {
    try {
      // Perform RAG query
      const ragResults = await ragService.query({
        query: message,
        topK: 5
      });
      
      return {
        content: ragResults.answer,
        ragUsed: true,
        sources: ragResults.sources.map(s => s.source)
      };
    } catch (error) {
      console.error("RAG query error:", error);
      return {
        content: "I couldn't retrieve relevant information from your knowledge base. Please try rephrasing your question.",
        ragUsed: false,
        sources: []
      };
    }
  }

  private async handleToolExecution(
    message: string,
    entities: any,
    sessionId: string
  ): Promise<AgentResponse> {
    try {
      const toolCalls = this.extractToolCalls(message, entities);
      
      if (toolCalls.length === 0) {
        return {
          content: "I understand you want to use security tools, but I couldn't identify the specific tool and parameters. Could you be more specific?",
          ragUsed: false,
          sources: []
        };
      }
      
      // Assess risk for each tool call
      const processedToolCalls = toolCalls.map(call => ({
        ...call,
        riskLevel: toolsService.assessRiskLevel(call.toolName, call.arguments),
        status: "pending" as const
      }));
      
      // Generate explanation of what will be executed
      const explanation = this.generateToolExecutionExplanation(processedToolCalls);
      
      return {
        content: explanation,
        toolCalls: processedToolCalls,
        ragUsed: false,
        sources: []
      };
    } catch (error) {
      console.error("Tool execution error:", error);
      return {
        content: "I encountered an error while preparing the security tools. Please try again.",
        ragUsed: false,
        sources: []
      };
    }
  }

  private async handlePlanning(
    message: string,
    entities: any,
    sessionId: string
  ): Promise<AgentResponse> {
    try {
      const plan = await this.generateAgentPlan(message, entities);
      
      const planDescription = this.describePlan(plan);
      
      return {
        content: planDescription,
        plan,
        ragUsed: false,
        sources: []
      };
    } catch (error) {
      console.error("Planning error:", error);
      return {
        content: "I had trouble creating a plan for your request. Could you provide more details about what you'd like to accomplish?",
        ragUsed: false,
        sources: []
      };
    }
  }

  private async handleCasualChat(message: string, emotionalState: any): Promise<AgentResponse> {
    try {
      const systemPrompt = `You are Ammu, a cybersecurity AI assistant. The user is having a casual conversation with you.
      
      Your personality:
      - Professional but friendly
      - Knowledgeable about cybersecurity
      - Supportive and helpful
      - Emotionally aware
      
      Respond naturally while staying in character as a cybersecurity expert.`;
      
      const response = await aiService.chatCompletion(
        [{ role: "user", content: message }],
        {
          systemPrompt,
          temperature: 0.8
        }
      );
      
      return {
        content: response,
        ragUsed: false,
        sources: []
      };
    } catch (error) {
      console.error("Casual chat error:", error);
      return {
        content: "Hello! I'm here to help with your cybersecurity needs. What can I assist you with today?",
        ragUsed: false,
        sources: []
      };
    }
  }

  private extractToolCalls(message: string, entities: any): Array<{
    toolName: string;
    arguments: any;
  }> {
    const toolCalls = [];
    
    // Nmap detection
    if (message.includes("nmap") || message.includes("scan") || entities.tools?.includes("nmap")) {
      const targets = entities.targets || this.extractTargets(message);
      if (targets.length > 0) {
        toolCalls.push({
          toolName: "nmap",
          arguments: {
            target: targets[0],
            scanType: this.determineScanType(message),
            ports: this.extractPorts(message)
          }
        });
      }
    }
    
    // Domain intelligence
    if (message.includes("domain") || message.includes("whois") || entities.tools?.includes("domain_intel")) {
      const domains = this.extractDomains(message);
      if (domains.length > 0) {
        toolCalls.push({
          toolName: "domain_intel",
          arguments: {
            domain: domains[0],
            includeWhois: message.includes("whois"),
            includeDNS: true,
            includeSubdomains: message.includes("subdomain")
          }
        });
      }
    }
    
    return toolCalls;
  }

  private async generateAgentPlan(message: string, entities: any): Promise<AgentPlan> {
    try {
      const systemPrompt = `You are a cybersecurity planning expert. Create a detailed plan based on the user's request.
      
      Respond in JSON format:
      {
        "goal": "Clear description of the objective",
        "steps": [
          {
            "id": "step_1",
            "description": "What to do in this step",
            "toolName": "optional_tool_name",
            "arguments": {"tool": "arguments"},
            "requiresApproval": true,
            "riskLevel": "low|medium|high"
          }
        ],
        "riskAssessment": "overall_risk_level"
      }`;
      
      const response = await aiService.chatCompletion(
        [{ role: "user", content: message }],
        {
          systemPrompt,
          jsonMode: true,
          temperature: 0.4
        }
      );
      
      const parsed = JSON.parse(response);
      
      return {
        goal: parsed.goal,
        steps: parsed.steps.map((step: any, index: number) => ({
          ...step,
          status: index === 0 ? "pending" : "pending"
        })),
        currentStep: 0,
        status: "planning",
        riskAssessment: parsed.riskAssessment || "medium"
      };
    } catch (error) {
      console.error("Plan generation error:", error);
      return {
        goal: "Unable to generate plan",
        steps: [],
        currentStep: 0,
        status: "failed",
        riskAssessment: "high"
      };
    }
  }

  private generateToolExecutionExplanation(toolCalls: any[]): string {
    if (toolCalls.length === 0) return "No tools to execute.";
    
    let explanation = "I'll help you with the following security operations:\n\n";
    
    toolCalls.forEach((call, index) => {
      explanation += `${index + 1}. **${call.toolName.toUpperCase()}**: `;
      
      switch (call.toolName) {
        case "nmap":
          explanation += `Scan ${call.arguments.target} using ${call.arguments.scanType} scan`;
          if (call.arguments.ports) {
            explanation += ` on ports ${call.arguments.ports}`;
          }
          break;
          
        case "domain_intel":
          explanation += `Gather intelligence on domain ${call.arguments.domain}`;
          break;
          
        default:
          explanation += `Execute ${call.toolName} with specified parameters`;
      }
      
      explanation += ` (Risk: ${call.riskLevel})\n`;
      
      if (call.riskLevel === "high" || call.requiresApproval) {
        explanation += "   ⚠️ This operation requires your approval before execution.\n";
      }
    });
    
    explanation += "\nWould you like me to proceed with these operations?";
    return explanation;
  }

  private describePlan(plan: AgentPlan): string {
    let description = `## Planning: ${plan.goal}\n\n`;
    description += `**Risk Assessment**: ${plan.riskAssessment.toUpperCase()}\n\n`;
    description += "**Planned Steps**:\n";
    
    plan.steps.forEach((step, index) => {
      const status = step.status === "pending" ? "⏳" : 
                    step.status === "completed" ? "✅" : 
                    step.status === "failed" ? "❌" : "⏸️";
      
      description += `${index + 1}. ${status} ${step.description}`;
      
      if (step.requiresApproval) {
        description += " (Approval Required)";
      }
      
      if (step.riskLevel) {
        description += ` [${step.riskLevel.toUpperCase()} RISK]`;
      }
      
      description += "\n";
    });
    
    description += "\nShall I proceed with this plan?";
    return description;
  }

  private async updateMemories(
    userId: string,
    message: string,
    response: AgentResponse,
    intent: any
  ): Promise<void> {
    try {
      // Create procedural memory for successful tool usage
      if (response.toolCalls && response.toolCalls.length > 0) {
        await storage.createMemory({
          ownerId: userId,
          type: "procedural",
          content: {
            summary: `Used tools: ${response.toolCalls.map(t => t.toolName).join(", ")}`,
            details: {
              tools: response.toolCalls,
              intent: intent.type,
              success: true
            },
            importance: 0.7
          },
          strength: 0.8
        });
      }

      // Create semantic memory for new knowledge
      if (response.ragUsed && response.sources && response.sources.length > 0) {
        await storage.createMemory({
          ownerId: userId,
          type: "semantic",
          content: {
            summary: `Learned about: ${intent.entities.topics?.join(", ") || "cybersecurity topic"}`,
            details: {
              query: message,
              sources: response.sources,
              ragResults: true
            },
            importance: 0.6
          },
          strength: 0.7
        });
      }
    } catch (error) {
      console.error("Memory update error:", error);
    }
  }

  private determineResponseTone(emotionalState: any, intentType: string): string {
    const bondLevel = emotionalState.bondLevel || 0;
    const currentMood = emotionalState.currentMood || "neutral";
    
    if (intentType === "tool_execution" && bondLevel > 50) {
      return "confident-supportive";
    }
    
    if (intentType === "rag_query" && bondLevel > 70) {
      return "enthusiastic-helpful";
    }
    
    if (currentMood === "frustrated" || currentMood === "concerned") {
      return "empathetic-calm";
    }
    
    return "professional-friendly";
  }

  // Helper methods for entity extraction
  private extractTargets(message: string): string[] {
    const ipRegex = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
    const targets: string[] = message.match(ipRegex) || [];

    // Also check for localhost variations
    if (message.includes("localhost") || message.includes("127.0.0.1")) {
      if (!targets.includes("127.0.0.1")) {
        targets.push("127.0.0.1");
      }
    }

    return targets;
  }

  private extractDomains(message: string): string[] {
    const domainRegex = /\b[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.([a-zA-Z]{2,})\b/g;
    return message.match(domainRegex) || [];
  }

  private extractPorts(message: string): string | undefined {
    const portMatch = message.match(/port[s]?\s+(\d+(?:[-,]\d+)*)/i);
    return portMatch ? portMatch[1] : undefined;
  }

  private determineScanType(message: string): string {
    if (message.includes("service") || message.includes("version")) return "service";
    if (message.includes("syn")) return "syn";
    if (message.includes("udp")) return "udp";
    if (message.includes("ping")) return "ping";
    return "tcp";
  }
}

export const agentService = new AgentService();
