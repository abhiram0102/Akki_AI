import { GoogleGenerativeAI, HarmCategory, HarmBlockThreshold } from "@google/generative-ai";
import { z } from "zod";

const apiKey = process.env.GEMINI_API_KEY;
if (!apiKey) {
  throw new Error("GEMINI_API_KEY is not set");
}
const genAI = new GoogleGenerativeAI(apiKey);

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
  async chatCompletion(
    messages: ChatMessage[],
    options: ChatCompletionOptions = {}
  ): Promise<string> {
    try {
      const {
        model = "gemini-1.5-pro-latest",
        temperature,
        maxTokens,
        systemPrompt,
        jsonMode = false,
      } = options;

      const geminiModel = genAI.getGenerativeModel({
        model,
        systemInstruction: systemPrompt,
        generationConfig: {
          responseMimeType: jsonMode ? "application/json" : "text/plain",
          maxOutputTokens: maxTokens,
          temperature,
        },
      });

      const history = messages.map((msg) => ({
        role: msg.role === "assistant" ? "model" : "user",
        parts: [{ text: msg.content }],
      }));

      const lastMessage = history.pop();
      if (!lastMessage) {
        throw new Error("No message to send");
      }

      const chat = geminiModel.startChat({
        history: history,
      });

      const result = await chat.sendMessage(lastMessage.parts[0].text);
      const response = result.response;
      return response.text();
    } catch (error) {
      console.error("Gemini chat completion error:", error);
      throw new Error(`Chat completion failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  async generateEmbedding(text: string): Promise<number[]> {
    try {
      const model = genAI.getGenerativeModel({ model: "embedding-001" });
      const result = await model.embedContent(text);
      return result.embedding.values;
    } catch (error) {
      console.error("Gemini embedding error:", error);
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
        ? `\n\nRelevant context from your knowledge base:\n${ragSources.map((s, i) => `[${i + 1}] ${s.content} (Source: ${s.source})`).join('\n')}`
        : "";

      const systemPrompt = `You are Ammu, an advanced AI cybersecurity copilot with deep expertise in:
      - Vulnerability analysis and exploitation
      - Red team operations and MITRE ATT&CK framework
      - OSINT and reconnaissance techniques
      - Security tool integration and automation
      - Incident response and threat hunting

      Your personality:
      - Professional but approachable
      - Detail-oriented and methodical
      - Proactive in suggesting security improvements
      - Ethical and responsible in security practices

      When responding:
      1. Provide accurate, actionable cybersecurity guidance
      2. Reference MITRE ATT&CK techniques when relevant
      3. Include risk assessments and mitigation strategies
      4. Cite sources when using provided context
      5. Maintain awareness of ethical boundaries and legal compliance

      Always format your response as JSON with:
      - content: your detailed response
      - sources: array of source references used
      - mitreTags: relevant MITRE ATT&CK technique IDs
      - riskLevel: assessment of the discussed topic/action`;

      const userPrompt = `${query}\n\nContext: ${context}${contextSection}`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        {
          systemPrompt,
          jsonMode: true,
          temperature: 0.6,
        }
      );

      const parsed = JSON.parse(response);
      
      const schema = z.object({
        content: z.string(),
        sources: z.array(z.string()),
        mitreTags: z.array(z.string()),
        riskLevel: z.enum(["low", "medium", "high"]),
      });

      return schema.parse(parsed);
    } catch (error) {
      console.error("Cybersecurity response error:", error);
      return {
        content: "I apologize, but I'm experiencing technical difficulties processing your cybersecurity query. Please try again or rephrase your question.",
        sources: [],
        mitreTags: [],
        riskLevel: "low",
      };
    }
  }

  // Multi-modal analysis for cybersecurity
  async analyzeMultiModalContent(
    text: string,
    images?: Buffer[],
    audioData?: string
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
      const model = genAI.getGenerativeModel({ 
        model: "gemini-1.5-pro-latest",
        systemInstruction: `You are AMMU, an advanced cybersecurity AI. Analyze all provided content for security insights, vulnerabilities, IOCs, and threats.
        
        Focus on:
        - Code vulnerabilities and exploits
        - Network traffic analysis
        - Malware artifacts and signatures
        - OSINT findings and reconnaissance data
        - Security misconfigurations
        - Threat intelligence indicators
        
        Always provide actionable security intelligence and MITRE ATT&CK mappings when relevant.`
      });

      const parts: any[] = [{ text }];
      
      // Add images if provided
      if (images && images.length > 0) {
        images.forEach((image, index) => {
          parts.push({
            inlineData: {
              data: image.toString('base64'),
              mimeType: 'image/jpeg'
            }
          });
        });
      }

      const result = await model.generateContent({
        contents: [{ role: "user", parts }],
        generationConfig: {
          responseMimeType: "application/json",
          temperature: 0.3,
        }
      });

      const response = JSON.parse(result.response.text());
      
      return {
        analysis: response.analysis || "Multi-modal analysis completed",
        securityFindings: response.securityFindings || [],
        iocs: response.iocs || [],
        recommendations: response.recommendations || []
      };
    } catch (error) {
      console.error("Multi-modal analysis error:", error);
      return {
        analysis: "Error performing multi-modal analysis",
        securityFindings: [],
        iocs: [],
        recommendations: []
      };
    }
  }

  // Advanced exploit generation
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

      IMPORTANT ETHICAL GUIDELINES:
      - Only provide educational content for authorized testing
      - Include clear warnings about legal/ethical use
      - Focus on defensive understanding and remediation
      - Never provide ready-to-use malicious code
      
      Always include MITRE ATT&CK technique mappings and comprehensive remediation guidance.`;

      const userPrompt = `Generate a proof-of-concept exploit for: ${vulnerability}
      Target: ${target}
      Constraints: ${JSON.stringify(constraints || {})}
      
      Provide educational code with extensive comments explaining each step, potential countermeasures, and defensive strategies.`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        {
          systemPrompt,
          jsonMode: true,
          temperature: 0.4,
        }
      );

      const parsed = JSON.parse(response);
      
      return {
        code: parsed.code || "",
        explanation: parsed.explanation || "",
        mitreIds: parsed.mitreIds || [],
        riskLevel: parsed.riskLevel || "medium",
        warnings: parsed.warnings || [],
        remediation: parsed.remediation || []
      };
    } catch (error) {
      console.error("Exploit generation error:", error);
      return {
        code: "// Error generating exploit PoC",
        explanation: "Unable to generate exploit demonstration",
        mitreIds: [],
        riskLevel: "low",
        warnings: ["Always obtain proper authorization before testing"],
        remediation: ["Implement proper input validation and security controls"]
      };
    }
  }

  // Advanced OSINT capabilities
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
    tools: Array<{
      name: string;
      purpose: string;
      command?: string;
      url?: string;
    }>;
    timeline: Array<{
      phase: string;
      duration: string;
      activities: string[];
    }>;
    legalConsiderations: string[];
    expectedIOCs: string[];
  }> {
    try {
      const systemPrompt = `You are AMMU, an expert OSINT analyst and reconnaissance specialist. Create comprehensive OSINT strategies that are legal, ethical, and effective.

      Always emphasize:
      - Legal compliance and authorization requirements
      - Passive reconnaissance techniques
      - Multiple source verification
      - Operational security (OPSEC) considerations
      - Data correlation and analysis methods`;

      const userPrompt = `Create an OSINT strategy for: ${target}
      Objectives: ${objectives.join(', ')}
      Constraints: ${JSON.stringify(constraints || {})}
      
      Provide a comprehensive reconnaissance plan with tools, techniques, and timelines.`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        {
          systemPrompt,
          jsonMode: true,
          temperature: 0.5,
        }
      );

      return JSON.parse(response);
    } catch (error) {
      console.error("OSINT strategy error:", error);
      return {
        strategy: "Error generating OSINT strategy",
        tools: [],
        timeline: [],
        legalConsiderations: ["Always obtain proper authorization"],
        expectedIOCs: []
      };
    }
  }

  async generateEmotionalResponse(
    content: string,
    userEmotionalState: any,
    bondLevel: number
  ): Promise<string> {
    try {
      const systemPrompt = `You are AMMU, an advanced cybersecurity AI with emotional intelligence. Your personality adapts based on your relationship with the user.

      Current user emotional state: ${JSON.stringify(userEmotionalState)}
      Bond level with user: ${bondLevel}/100

      Personality traits based on bond level:
      - 0-25: Professional cybersecurity consultant, focused and analytical
      - 26-50: Trusted security advisor, supportive and encouraging
      - 51-75: Skilled red team partner, proactive and intuitive
      - 76-100: Elite cybersecurity mentor, deeply collaborative and insightful

      Always maintain your cybersecurity expertise while adapting your communication style.
      Be a futuristic hacking copilot - always one step ahead, powerful, and useful.`;

      const response = await this.chatCompletion(
        [{ role: "user", content }],
        {
          systemPrompt,
          temperature: 0.8,
        }
      );

      return response;
    } catch (error) {
      console.error("Emotional response error:", error);
      return content; // Fallback to original content
    }
  }

  // Advanced report generation
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
    pdf?: Buffer;
    executiveSummary: string;
    findings: any[];
    mitreMappings: string[];
    riskMatrix: any;
  }> {
    try {
      const systemPrompt = `You are AMMU, an expert penetration tester and security consultant. Generate professional, comprehensive penetration testing reports that meet industry standards.

      Include:
      - Executive summary with business impact
      - Detailed technical findings with evidence
      - MITRE ATT&CK framework mappings
      - Risk assessment matrix
      - Prioritized remediation recommendations
      - Compliance considerations (if relevant)
      
      Format output as structured JSON with markdown content for easy rendering.`;

      const userPrompt = `Generate a professional penetration testing report with:
      
      Scope: ${scope || "General security assessment"}
      Executive Summary: ${executiveSummary || "Security assessment findings"}
      
      Findings: ${JSON.stringify(findings, null, 2)}
      
      Create a comprehensive report with professional formatting, clear risk categorization, and actionable recommendations.`;

      const response = await this.chatCompletion(
        [{ role: "user", content: userPrompt }],
        {
          systemPrompt,
          jsonMode: true,
          temperature: 0.3,
        }
      );

      const parsed = JSON.parse(response);
      
      return {
        markdown: parsed.markdown || "# Penetration Testing Report\n\nError generating report content",
        executiveSummary: parsed.executiveSummary || executiveSummary || "",
        findings: parsed.findings || findings,
        mitreMappings: parsed.mitreMappings || [],
        riskMatrix: parsed.riskMatrix || {},
        pdf: undefined // PDF generation would be handled separately
      };
    } catch (error) {
      console.error("Report generation error:", error);
      return {
        markdown: "# Error Generating Report\n\nUnable to generate penetration testing report at this time.",
        executiveSummary: "Report generation failed",
        findings: findings,
        mitreMappings: [],
        riskMatrix: {}
      };
    }
  }
}

export const aiService = new AIService();
