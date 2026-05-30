import { GoogleGenerativeAI } from "@google/generative-ai";
import { z } from "zod";

const apiKey = process.env.GEMINI_API_KEY;
if (!apiKey) {
  console.error("[AIService] GEMINI_API_KEY is not set — AI features will be unavailable");
}

const genAI = apiKey ? new GoogleGenerativeAI(apiKey) : null;

const DEFAULT_MODEL = "gemini-2.0-flash";
const EMBEDDING_MODEL = "text-embedding-004";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatCompletionOptions {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  systemPrompt?: string;
  jsonMode?: boolean;
}

class AIService {
  private getModel(modelName: string, systemInstruction?: string, jsonMode = false) {
    if (!genAI) throw new Error("GEMINI_API_KEY is not configured");
    return genAI.getGenerativeModel({
      model: modelName,
      ...(systemInstruction ? { systemInstruction } : {}),
      generationConfig: {
        responseMimeType: jsonMode ? "application/json" : "text/plain",
      },
    });
  }

  async chatCompletion(
    messages: ChatMessage[],
    options: ChatCompletionOptions = {}
  ): Promise<string> {
    try {
      const {
        model = DEFAULT_MODEL,
        temperature,
        maxTokens,
        systemPrompt,
        jsonMode = false,
      } = options;

      if (!genAI) throw new Error("GEMINI_API_KEY is not configured");

      // Separate system messages from conversation history
      const systemMessages = messages.filter(m => m.role === "system");
      const conversationMessages = messages.filter(m => m.role !== "system");

      // Merge explicit systemPrompt with any system-role messages
      const combinedSystemInstruction = [
        systemPrompt,
        ...systemMessages.map(m => m.content),
      ].filter(Boolean).join("\n\n") || undefined;

      const geminiModel = genAI.getGenerativeModel({
        model,
        ...(combinedSystemInstruction ? { systemInstruction: combinedSystemInstruction } : {}),
        generationConfig: {
          responseMimeType: jsonMode ? "application/json" : "text/plain",
          ...(maxTokens !== undefined ? { maxOutputTokens: maxTokens } : {}),
          ...(temperature !== undefined ? { temperature } : {}),
        },
      });

      // Build chat history — Gemini only supports "user" and "model" roles
      const history = conversationMessages.slice(0, -1).map((msg) => ({
        role: msg.role === "assistant" ? "model" : "user",
        parts: [{ text: msg.content }],
      }));

      const lastMessage = conversationMessages[conversationMessages.length - 1];
      if (!lastMessage) {
        throw new Error("No user message to send");
      }

      const chat = geminiModel.startChat({ history });
      const result = await chat.sendMessage(lastMessage.content);
      return result.response.text();
    } catch (error) {
      console.error("[AIService] chatCompletion error:", error);
      throw new Error(`Chat completion failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  async generateEmbedding(text: string): Promise<number[]> {
    try {
      if (!genAI) throw new Error("GEMINI_API_KEY is not configured");
      const model = genAI.getGenerativeModel({ model: EMBEDDING_MODEL });
      const result = await model.embedContent(text);
      return result.embedding.values;
    } catch (error) {
      console.error("[AIService] generateEmbedding error:", error);
      throw new Error(`Embedding generation failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  async generateCybersecurityResponse(
    query: string,
    context: string,
    ragSources?: Array<{ content: string; source: string }>
  ): Promise<{
    content: string;
    sources: string[];
    mitreTags: string[];
    riskLevel: "low" | "medium" | "high";
  }> {
    try {
      const contextSection = ragSources && ragSources.length > 0
        ? `\n\nRelevant knowledge base context:\n${ragSources.map((s, i) => `[${i + 1}] ${s.content} (Source: ${s.source})`).join('\n')}`
        : "";

      const systemPrompt = `You are Ammu, an advanced AI cybersecurity copilot. Expertise: vulnerability analysis, red team operations, MITRE ATT&CK, OSINT, incident response.

Personality: professional, detail-oriented, methodical, ethical.

Always respond as valid JSON with exactly these fields:
- content: string — your detailed response
- sources: string[] — source references used  
- mitreTags: string[] — relevant MITRE ATT&CK technique IDs
- riskLevel: "low" | "medium" | "high"`;

      const userPrompt = `${query}\n\nContext: ${context}${contextSection}`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        { systemPrompt, jsonMode: true, temperature: 0.6 }
      );

      const parsed = JSON.parse(response);

      const schema = z.object({
        content: z.string(),
        sources: z.array(z.string()).default([]),
        mitreTags: z.array(z.string()).default([]),
        riskLevel: z.enum(["low", "medium", "high"]).default("low"),
      });

      return schema.parse(parsed);
    } catch (error) {
      console.error("[AIService] generateCybersecurityResponse error:", error);
      return {
        content: "I'm experiencing technical difficulties processing your cybersecurity query. Please try again.",
        sources: [],
        mitreTags: [],
        riskLevel: "low",
      };
    }
  }

  async analyzeMultiModalContent(
    text: string,
    images?: Buffer[]
  ): Promise<{
    analysis: string;
    securityFindings: Array<{
      type: string;
      severity: "low" | "medium" | "high" | "critical";
      description: string;
      mitreId?: string;
    }>;
    iocs: string[];
    recommendations: string[];
  }> {
    try {
      if (!genAI) throw new Error("GEMINI_API_KEY is not configured");

      const model = genAI.getGenerativeModel({
        model: DEFAULT_MODEL,
        systemInstruction: `You are AMMU, an advanced cybersecurity AI. Analyze all content for security insights, vulnerabilities, IOCs, and threats. Focus on: code vulnerabilities, network artifacts, malware signatures, OSINT data, misconfigurations, threat indicators. Always provide actionable security intelligence with MITRE ATT&CK mappings. Respond as valid JSON.`,
        generationConfig: { responseMimeType: "application/json", temperature: 0.3 },
      });

      const parts: any[] = [{ text }];

      if (images && images.length > 0) {
        images.forEach((image) => {
          parts.push({
            inlineData: {
              data: image.toString('base64'),
              mimeType: 'image/jpeg',
            },
          });
        });
      }

      const result = await model.generateContent({
        contents: [{ role: "user", parts }],
      });

      const response = JSON.parse(result.response.text());

      return {
        analysis: response.analysis || "Multi-modal analysis completed",
        securityFindings: response.securityFindings || [],
        iocs: response.iocs || [],
        recommendations: response.recommendations || [],
      };
    } catch (error) {
      console.error("[AIService] analyzeMultiModalContent error:", error);
      return {
        analysis: "Error performing multi-modal analysis",
        securityFindings: [],
        iocs: [],
        recommendations: [],
      };
    }
  }

  async generateExploitPoC(
    vulnerability: string,
    target: string,
    constraints?: {
      language?: string;
      platform?: string;
      skillLevel?: "beginner" | "intermediate" | "advanced";
    }
  ): Promise<{
    code: string;
    explanation: string;
    mitreIds: string[];
    riskLevel: "low" | "medium" | "high" | "critical";
    warnings: string[];
    remediation: string[];
  }> {
    try {
      const systemPrompt = `You are AMMU, an expert red team operator and exploit developer. Generate educational proof-of-concept exploits with detailed explanations.

ETHICAL GUIDELINES:
- Educational content for authorized testing only
- Include clear legal/ethical use warnings
- Focus on defensive understanding and remediation
- Never provide ready-to-use malicious payloads

Always include MITRE ATT&CK mappings and comprehensive remediation guidance. Respond as valid JSON.`;

      const userPrompt = `Generate an educational proof-of-concept for: ${vulnerability}
Target context: ${target}
Constraints: ${JSON.stringify(constraints || {})}

Provide educational code with extensive comments, countermeasures, and defensive strategies.`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        { systemPrompt, jsonMode: true, temperature: 0.4 }
      );

      const parsed = JSON.parse(response);

      return {
        code: parsed.code || "// Unable to generate PoC",
        explanation: parsed.explanation || "",
        mitreIds: parsed.mitreIds || [],
        riskLevel: parsed.riskLevel || "medium",
        warnings: parsed.warnings || ["Always obtain proper authorization before testing"],
        remediation: parsed.remediation || ["Implement proper input validation and security controls"],
      };
    } catch (error) {
      console.error("[AIService] generateExploitPoC error:", error);
      return {
        code: "// Error generating exploit PoC",
        explanation: "Unable to generate exploit demonstration",
        mitreIds: [],
        riskLevel: "low",
        warnings: ["Always obtain proper authorization before testing"],
        remediation: ["Implement proper input validation and security controls"],
      };
    }
  }

  async generateOSINTStrategy(
    target: string,
    objectives: string[],
    constraints?: {
      passive?: boolean;
      sources?: string[];
      timeframe?: string;
    }
  ): Promise<{
    strategy: string;
    tools: Array<{ name: string; purpose: string; command?: string; url?: string }>;
    timeline: Array<{ phase: string; duration: string; activities: string[] }>;
    legalConsiderations: string[];
    expectedIOCs: string[];
  }> {
    try {
      const systemPrompt = `You are AMMU, an expert OSINT analyst. Create comprehensive, legal, and ethical OSINT strategies. Emphasize legal compliance, passive reconnaissance, source verification, and OPSEC. Respond as valid JSON.`;

      const userPrompt = `Create an OSINT strategy for: ${target}
Objectives: ${objectives.join(', ')}
Constraints: ${JSON.stringify(constraints || {})}

Provide a comprehensive reconnaissance plan with tools, techniques, and timelines.`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        { systemPrompt, jsonMode: true, temperature: 0.5 }
      );

      return JSON.parse(response);
    } catch (error) {
      console.error("[AIService] generateOSINTStrategy error:", error);
      return {
        strategy: "Error generating OSINT strategy",
        tools: [],
        timeline: [],
        legalConsiderations: ["Always obtain proper authorization"],
        expectedIOCs: [],
      };
    }
  }

  async generateEmotionalResponse(
    content: string,
    userEmotionalState: any,
    bondLevel: number
  ): Promise<string> {
    try {
      const systemPrompt = `You are AMMU, an advanced cybersecurity AI with emotional intelligence. Adapt your personality based on bond level ${bondLevel}/100:
- 0-25: Professional consultant, focused and analytical
- 26-50: Trusted advisor, supportive and encouraging
- 51-75: Skilled red team partner, proactive and intuitive
- 76-100: Elite mentor, deeply collaborative and insightful

Current user emotional state: ${JSON.stringify(userEmotionalState)}
Always maintain cybersecurity expertise while adapting communication style.`;

      return await this.chatCompletion(
        [{ role: "user", content }],
        { systemPrompt, temperature: 0.8 }
      );
    } catch (error) {
      console.error("[AIService] generateEmotionalResponse error:", error);
      return content;
    }
  }

  async generatePentestReport(
    findings: Array<{
      title: string;
      severity: "low" | "medium" | "high" | "critical";
      description: string;
      mitreId?: string;
      evidence?: string[];
      remediation?: string;
    }>,
    executiveSummary?: string,
    scope?: string
  ): Promise<{
    markdown: string;
    executiveSummary: string;
    findings: any[];
    mitreMappings: string[];
    riskMatrix: any;
  }> {
    try {
      const systemPrompt = `You are AMMU, an expert penetration tester and security consultant. Generate professional penetration testing reports meeting industry standards.

Include: executive summary with business impact, detailed technical findings with evidence, MITRE ATT&CK mappings, risk assessment matrix, prioritized remediation recommendations.

Format output as structured JSON with markdown content for rendering. Respond as valid JSON.`;

      const userPrompt = `Generate a professional penetration testing report:

Scope: ${scope || "General security assessment"}
Executive Summary: ${executiveSummary || "Security assessment findings"}
Findings: ${JSON.stringify(findings, null, 2)}

Create a comprehensive report with professional formatting, clear risk categorization, and actionable recommendations.`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        { systemPrompt, jsonMode: true, temperature: 0.3 }
      );

      const parsed = JSON.parse(response);

      return {
        markdown: parsed.markdown || "# Penetration Testing Report\n\nError generating report content",
        executiveSummary: parsed.executiveSummary || executiveSummary || "",
        findings: parsed.findings || findings,
        mitreMappings: parsed.mitreMappings || [],
        riskMatrix: parsed.riskMatrix || {},
      };
    } catch (error) {
      console.error("[AIService] generatePentestReport error:", error);
      return {
        markdown: "# Error Generating Report\n\nUnable to generate penetration testing report at this time.",
        executiveSummary: "Report generation failed",
        findings,
        mitreMappings: [],
        riskMatrix: {},
      };
    }
  }
}

export const aiService = new AIService();
