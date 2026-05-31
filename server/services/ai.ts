/**
 * Multi-provider AI service
 *
 * Provider priority (controlled by AI_PROVIDER env var):
 *   "auto"   (default) — Ollama if reachable, otherwise Gemini
 *   "ollama"            — Ollama only (throws if unavailable)
 *   "gemini"            — Gemini only (original behaviour)
 *
 * Agent-role model routing (Ollama):
 *   options.agentRole = "chat" | "code" | "redteam" | "embed"
 *   Maps to OLLAMA_MODELS.* from ollama.ts
 */

import { GoogleGenerativeAI } from "@google/generative-ai";
import { z } from "zod";
import {
  checkOllamaAvailability,
  isOllamaAvailable,
  ollamaChat,
  ollamaEmbed,
  OLLAMA_MODELS,
  type OllamaMessage,
  type OllamaAgentRole,
} from "./ollama";

// ─── Config ───────────────────────────────────────────────────────────────────

const AI_PROVIDER = (process.env.AI_PROVIDER || "auto").toLowerCase() as
  | "auto" | "ollama" | "gemini";

const geminiKey = process.env.GEMINI_API_KEY;
const genAI = geminiKey ? new GoogleGenerativeAI(geminiKey) : null;

if (!geminiKey && AI_PROVIDER !== "ollama") {
  console.warn("[AIService] GEMINI_API_KEY not set — Gemini unavailable");
}

const GEMINI_MODEL   = "gemini-2.0-flash";
const GEMINI_EMBED   = "text-embedding-004";

// ─── Initialise Ollama at startup ─────────────────────────────────────────────

if (AI_PROVIDER !== "gemini") {
  checkOllamaAvailability().catch(() => {});
}

// ─── Retry helper (Gemini rate-limits only) ───────────────────────────────────

async function withRetry<T>(fn: () => Promise<T>, maxAttempts = 2): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try { return await fn(); } catch (err: any) {
      lastError = err;
      const status = err?.status ?? err?.statusCode;
      if (status === 429) {
        const isDailyLimit = err?.errorDetails?.some((d: any) =>
          d?.violations?.some((v: any) => v?.quotaId?.includes("PerDay"))
        );
        if (isDailyLimit) throw new Error(
          "RATE_LIMIT_DAILY: Gemini daily quota exhausted. Set AI_PROVIDER=ollama to bypass."
        );
        let waitMs = 3000;
        try {
          const ri = err?.errorDetails?.find((d: any) => d["@type"]?.endsWith("RetryInfo"));
          if (ri?.retryDelay) waitMs = Math.min(Math.ceil(parseFloat(ri.retryDelay) * 1000) + 200, 8000);
        } catch {}
        console.warn(`[AIService] Gemini 429 — waiting ${waitMs}ms (attempt ${attempt + 1})`);
        await new Promise(r => setTimeout(r, waitMs));
        continue;
      }
      throw err;
    }
  }
  throw lastError;
}

// ─── Exported types ───────────────────────────────────────────────────────────

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
  /** Ollama agent role — routes to the right model automatically */
  agentRole?: OllamaAgentRole;
}

// ─── AIService ────────────────────────────────────────────────────────────────

class AIService {
  /** Which provider is actually serving requests right now */
  getActiveProvider(): "ollama" | "gemini" | "none" {
    if (AI_PROVIDER === "gemini")  return genAI ? "gemini" : "none";
    if (AI_PROVIDER === "ollama")  return isOllamaAvailable() ? "ollama" : "none";
    // auto
    if (isOllamaAvailable())       return "ollama";
    if (genAI)                     return "gemini";
    return "none";
  }

  // ── Chat completion ─────────────────────────────────────────────────────────

  async chatCompletion(
    messages: ChatMessage[],
    options: ChatCompletionOptions = {}
  ): Promise<string> {
    const provider = this.getActiveProvider();

    if (provider === "ollama") {
      return this._ollamaChat(messages, options);
    }
    if (provider === "gemini") {
      return this._geminiChat(messages, options);
    }
    throw new Error(
      "No AI provider available. Start Ollama or set GEMINI_API_KEY."
    );
  }

  // ── Embeddings ──────────────────────────────────────────────────────────────

  async generateEmbedding(text: string): Promise<number[]> {
    const provider = this.getActiveProvider();

    if (provider === "ollama") {
      try {
        return await ollamaEmbed(text);
      } catch (err) {
        console.error("[AIService] Ollama embedding failed:", err);
        throw err;
      }
    }
    if (provider === "gemini") {
      return this._geminiEmbed(text);
    }
    throw new Error("No AI provider available for embeddings.");
  }

  // ── Ollama implementation ───────────────────────────────────────────────────

  private async _ollamaChat(
    messages: ChatMessage[],
    options: ChatCompletionOptions
  ): Promise<string> {
    const { systemPrompt, agentRole = "chat", temperature } = options;

    const ollamaMessages: OllamaMessage[] = [];
    if (systemPrompt) ollamaMessages.push({ role: "system", content: systemPrompt });
    for (const m of messages) {
      if (m.role !== "system") ollamaMessages.push({ role: m.role, content: m.content });
      else ollamaMessages.push({ role: "system", content: m.content });
    }

    try {
      const model = OLLAMA_MODELS[agentRole] ?? OLLAMA_MODELS.chat;
      return await ollamaChat(ollamaMessages, model, { temperature });
    } catch (err) {
      console.error("[AIService] Ollama chat error:", err);
      throw new Error(`Ollama chat failed: ${err instanceof Error ? err.message : err}`);
    }
  }

  // ── Gemini implementation ───────────────────────────────────────────────────

  private async _geminiChat(
    messages: ChatMessage[],
    options: ChatCompletionOptions
  ): Promise<string> {
    if (!genAI) throw new Error("GEMINI_API_KEY is not configured");
    const { model = GEMINI_MODEL, temperature, maxTokens, systemPrompt, jsonMode = false } = options;

    const sysMessages = messages.filter(m => m.role === "system");
    const convMessages = messages.filter(m => m.role !== "system");
    const combined = [systemPrompt, ...sysMessages.map(m => m.content)].filter(Boolean).join("\n\n") || undefined;
    const last = convMessages[convMessages.length - 1];
    if (!last) throw new Error("No user message to send");

    const history = convMessages.slice(0, -1).map(m => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.content }],
    }));

    const geminiModel = genAI.getGenerativeModel({
      model,
      ...(combined ? { systemInstruction: combined } : {}),
      generationConfig: {
        responseMimeType: jsonMode ? "application/json" : "text/plain",
        ...(maxTokens ? { maxOutputTokens: maxTokens } : {}),
        ...(temperature !== undefined ? { temperature } : {}),
      },
    });

    try {
      return await withRetry(async () => {
        const chat = geminiModel.startChat({ history });
        const result = await chat.sendMessage(last.content);
        return result.response.text();
      });
    } catch (err) {
      console.error("[AIService] Gemini chat error:", err);
      throw new Error(`Chat completion failed: ${err instanceof Error ? err.message : err}`);
    }
  }

  private async _geminiEmbed(text: string): Promise<number[]> {
    if (!genAI) throw new Error("GEMINI_API_KEY is not configured");
    try {
      const model = genAI.getGenerativeModel({ model: GEMINI_EMBED });
      const result = await model.embedContent(text);
      return result.embedding.values;
    } catch (err) {
      console.error("[AIService] Gemini embedding error:", err);
      throw new Error(`Embedding failed: ${err instanceof Error ? err.message : err}`);
    }
  }

  // ── High-level helpers (unchanged behaviour, now multi-provider) ─────────────

  async generateCybersecurityResponse(
    query: string,
    context: string,
    ragSources?: Array<{ content: string; source: string }>
  ): Promise<{ content: string; sources: string[]; mitreTags: string[]; riskLevel: "low" | "medium" | "high" }> {
    try {
      const contextSection = ragSources?.length
        ? `\n\nKnowledge base context:\n${ragSources.map((s, i) => `[${i + 1}] ${s.content} (Source: ${s.source})`).join("\n")}`
        : "";

      const systemPrompt = `You are AKKI, an advanced cybersecurity AI. Expertise: vulnerability analysis, red team, MITRE ATT\&CK, OSINT, incident response.
Respond as valid JSON with fields: content (string), sources (string[]), mitreTags (string[]), riskLevel ("low"|"medium"|"high").`;

      const response = await this.chatCompletion(
        [{ role: "user", content: `${query}\n\nContext: ${context}${contextSection}` }],
        { systemPrompt, jsonMode: true, temperature: 0.6, agentRole: "chat" }
      );

      const parsed = JSON.parse(response);
      return z.object({
        content: z.string(),
        sources: z.array(z.string()).default([]),
        mitreTags: z.array(z.string()).default([]),
        riskLevel: z.enum(["low", "medium", "high"]).default("low"),
      }).parse(parsed);
    } catch {
      return { content: "I'm experiencing technical difficulties. Please try again.", sources: [], mitreTags: [], riskLevel: "low" };
    }
  }

  async generateExploitPoC(
    vulnerability: string, target: string,
    constraints?: { language?: string; platform?: string; skillLevel?: string }
  ): Promise<{ code: string; explanation: string; mitreIds: string[]; riskLevel: string; warnings: string[]; remediation: string[] }> {
    try {
      const systemPrompt = `You are AKKI, an expert red team operator. Generate educational proof-of-concept exploits.
GUIDELINES: educational/authorized testing only, include legal warnings, never ready-to-use malicious payloads.
Respond as valid JSON with fields: code, explanation, mitreIds, riskLevel, warnings, remediation.`;

      const response = await this.chatCompletion(
        [{ role: "user", content: `Vulnerability: ${vulnerability}\nTarget: ${target}\nConstraints: ${JSON.stringify(constraints || {})}` }],
        { systemPrompt, jsonMode: true, temperature: 0.4, agentRole: "code" }
      );
      const p = JSON.parse(response);
      return {
        code: p.code || "// PoC unavailable",
        explanation: p.explanation || "",
        mitreIds: p.mitreIds || [],
        riskLevel: p.riskLevel || "medium",
        warnings: p.warnings || ["Always obtain proper authorization before testing"],
        remediation: p.remediation || ["Implement proper input validation"],
      };
    } catch {
      return { code: "// Error", explanation: "PoC generation failed", mitreIds: [], riskLevel: "low", warnings: [], remediation: [] };
    }
  }

  async generateOSINTStrategy(
    target: string, objectives: string[], constraints?: any
  ): Promise<{ strategy: string; tools: any[]; timeline: any[]; legalConsiderations: string[]; expectedIOCs: string[] }> {
    try {
      const systemPrompt = `You are AKKI, an expert OSINT analyst. Create legal, ethical OSINT strategies. Respond as valid JSON.`;
      const response = await this.chatCompletion(
        [{ role: "user", content: `Target: ${target}\nObjectives: ${objectives.join(", ")}\nConstraints: ${JSON.stringify(constraints || {})}` }],
        { systemPrompt, jsonMode: true, temperature: 0.5, agentRole: "chat" }
      );
      return JSON.parse(response);
    } catch {
      return { strategy: "Error", tools: [], timeline: [], legalConsiderations: ["Always obtain proper authorization"], expectedIOCs: [] };
    }
  }

  async generatePentestReport(
    findings: any[], executiveSummary?: string, scope?: string
  ): Promise<{ markdown: string; executiveSummary: string; findings: any[]; mitreMappings: string[]; riskMatrix: any }> {
    try {
      const systemPrompt = `You are AKKI, an expert penetration tester. Generate professional pentest reports meeting industry standards. Respond as valid JSON with fields: markdown, executiveSummary, findings, mitreMappings, riskMatrix.`;
      const response = await this.chatCompletion(
        [{ role: "user", content: `Scope: ${scope || "General"}\nSummary: ${executiveSummary || ""}\nFindings: ${JSON.stringify(findings, null, 2)}` }],
        { systemPrompt, jsonMode: true, temperature: 0.3, agentRole: "chat" }
      );
      const p = JSON.parse(response);
      return { markdown: p.markdown || "# Report\n\nError", executiveSummary: p.executiveSummary || "", findings: p.findings || findings, mitreMappings: p.mitreMappings || [], riskMatrix: p.riskMatrix || {} };
    } catch {
      return { markdown: "# Error\n\nReport generation failed", executiveSummary: "", findings, mitreMappings: [], riskMatrix: {} };
    }
  }

  async generateEmotionalResponse(content: string, userEmotionalState: any, bondLevel: number): Promise<string> {
    try {
      const systemPrompt = `You are AKKI, a cybersecurity AI with emotional intelligence. Bond level ${bondLevel}/100 shapes your tone:\n0-25: professional, 26-50: trusted advisor, 51-75: red team partner, 76-100: elite mentor.\nUser state: ${JSON.stringify(userEmotionalState)}`;
      return await this.chatCompletion([{ role: "user", content }], { systemPrompt, temperature: 0.8 });
    } catch { return content; }
  }

  async analyzeMultiModalContent(text: string, images?: Buffer[]) {
    try {
      if (isOllamaAvailable()) {
        const response = await ollamaChat(
          [{ role: "user", content: `Analyze the following for security insights, vulnerabilities, IOCs and threats:\n\n${text}` }],
          OLLAMA_MODELS.chat
        );
        return { analysis: response, securityFindings: [], iocs: [], recommendations: [] };
      }
      if (!genAI) throw new Error("No provider");
      const model = genAI.getGenerativeModel({ model: GEMINI_MODEL, generationConfig: { responseMimeType: "application/json" } });
      const parts: any[] = [{ text }];
      images?.forEach(img => parts.push({ inlineData: { data: img.toString("base64"), mimeType: "image/jpeg" } }));
      const result = await model.generateContent({ contents: [{ role: "user", parts }] });
      const r = JSON.parse(result.response.text());
      return { analysis: r.analysis || "Done", securityFindings: r.securityFindings || [], iocs: r.iocs || [], recommendations: r.recommendations || [] };
    } catch {
      return { analysis: "Analysis unavailable", securityFindings: [], iocs: [], recommendations: [] };
    }
  }
}

export const aiService = new AIService();
