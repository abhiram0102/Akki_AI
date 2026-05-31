/**
 * Ollama local-model client
 *
 * Connects to an Ollama server running at OLLAMA_URL.
 * That server can be:
 *   - On your own machine → expose with `ollama serve` + ngrok / port-forward
 *   - On any LAN/VPS that runs Ollama
 *
 * Quick-start (your local machine):
 *   1.  curl -fsSL https://ollama.ai/install.sh | sh
 *   2.  ollama pull llama3.2          # general chat
 *   3.  ollama pull codellama         # code / exploit analysis
 *   4.  ollama pull mistral           # red-team reasoning
 *   5.  ollama pull nomic-embed-text  # RAG embeddings (no GPU needed, tiny model)
 *   6.  Set OLLAMA_URL=http://<your-ip-or-ngrok>:11434  in .env
 *   7.  Set AI_PROVIDER=ollama  (or "auto" to keep Gemini as fallback)
 *
 * Model env-var overrides:
 *   OLLAMA_CHAT_MODEL      default: llama3.2
 *   OLLAMA_CODE_MODEL      default: codellama
 *   OLLAMA_REDTEAM_MODEL   default: mistral
 *   OLLAMA_EMBED_MODEL     default: nomic-embed-text
 *   OLLAMA_TIMEOUT_MS      default: 120000
 */

const BASE_URL = (process.env.OLLAMA_URL || "http://localhost:11434").replace(/\/$/, "");
const TIMEOUT_MS = parseInt(process.env.OLLAMA_TIMEOUT_MS || "120000", 10);

export const OLLAMA_MODELS = {
  chat:    process.env.OLLAMA_CHAT_MODEL    || "llama3.2",
  code:    process.env.OLLAMA_CODE_MODEL    || "codellama",
  redteam: process.env.OLLAMA_REDTEAM_MODEL || "mistral",
  embed:   process.env.OLLAMA_EMBED_MODEL   || "nomic-embed-text",
} as const;

export type OllamaAgentRole = keyof typeof OLLAMA_MODELS;

let _available: boolean | null = null;
let _models: string[] = [];

/** Called once at startup — sets the availability flag */
export async function checkOllamaAvailability(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/api/tags`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) { _available = false; return false; }
    const data: any = await res.json();
    _models = (data.models || []).map((m: any) => String(m.name));
    console.log(`[Ollama] Connected ✓  models: ${_models.slice(0, 8).join(", ") || "(none pulled yet)"}`);
    _available = true;
    return true;
  } catch {
    console.log(`[Ollama] Not reachable at ${BASE_URL} — will use Gemini`);
    _available = false;
    return false;
  }
}

export const isOllamaAvailable   = () => _available === true;
export const getOllamaModels     = () => _models;
export const getOllamaBaseUrl    = () => BASE_URL;

// ─── Internal fetch helper ────────────────────────────────────────────────────

async function ollamaPost(endpoint: string, body: object): Promise<any> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(`Ollama ${endpoint} → ${res.status}: ${msg}`);
  }
  return res.json();
}

// ─── Public API ───────────────────────────────────────────────────────────────

export interface OllamaMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

/**
 * Chat completion via Ollama.
 * Pass `role` to auto-select the right model for the task.
 */
export async function ollamaChat(
  messages: OllamaMessage[],
  modelOrRole: string = OLLAMA_MODELS.chat,
  options: { temperature?: number } = {}
): Promise<string> {
  // Allow callers to pass a role name ("code", "redteam", etc.) instead of a full model name
  const model = (OLLAMA_MODELS as any)[modelOrRole] ?? modelOrRole;

  const data = await ollamaPost("/api/chat", {
    model,
    messages,
    stream: false,
    options: { temperature: options.temperature ?? 0.7 },
  });
  return (data.message?.content ?? "").trim();
}

/**
 * Generate a vector embedding via Ollama.
 * Uses nomic-embed-text by default (fast, CPU-friendly, 768-dim).
 */
export async function ollamaEmbed(
  text: string,
  model: string = OLLAMA_MODELS.embed
): Promise<number[]> {
  const data = await ollamaPost("/api/embeddings", { model, prompt: text });
  if (!Array.isArray(data.embedding) || data.embedding.length === 0) {
    throw new Error(`Ollama embedding returned empty vector (model: ${model})`);
  }
  return data.embedding as number[];
}

/** List models that are actually pulled on the Ollama server */
export async function listOllamaModels(): Promise<string[]> {
  try {
    const res = await fetch(`${BASE_URL}/api/tags`, { signal: AbortSignal.timeout(5000) });
    const data: any = await res.json();
    return (data.models || []).map((m: any) => String(m.name));
  } catch {
    return [];
  }
}
