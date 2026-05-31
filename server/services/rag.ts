/**
 * RAG Service — ChromaDB-free implementation
 *
 * Vector storage: PostgreSQL chunks table (embedding real[] column already exists)
 * Similarity:     Cosine similarity computed in JavaScript (fast for ≤50k chunks)
 * Embeddings:     Ollama nomic-embed-text  OR  Gemini text-embedding-004
 *                 (whichever provider is active in ai.ts)
 *
 * No extra services needed — works out of the box with the existing Neon DB.
 */

import pdf from "pdf-parse";
import { storage } from "../storage";
import { aiService } from "./ai";
import type { InsertDocument, InsertChunk } from "@shared/schema";

export interface RAGQueryResult {
  answer: string;
  sources: Array<{
    content: string;
    source: string;
    relevanceScore: number;
    metadata?: any;
  }>;
  confidence: number;
}

export interface DocumentIngestOptions {
  file: Express.Multer.File;
  userId: string;
  title: string;
  tags?: string[];
}

// ─── Cosine similarity ────────────────────────────────────────────────────────

function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length || a.length === 0) return 0;
  let dot = 0, magA = 0, magB = 0;
  for (let i = 0; i < a.length; i++) {
    dot  += a[i] * b[i];
    magA += a[i] * a[i];
    magB += b[i] * b[i];
  }
  const denom = Math.sqrt(magA) * Math.sqrt(magB);
  return denom === 0 ? 0 : dot / denom;
}

// ─── RAGService ───────────────────────────────────────────────────────────────

class RAGService {
  /** No-op initialisation — always ready (no external service required) */
  async initialize(): Promise<void> {
    const provider = aiService.getActiveProvider();
    console.log(`[RAGService] Ready — embeddings via ${provider}, vector store: PostgreSQL`);
  }

  // ── Document ingestion ──────────────────────────────────────────────────────

  async ingestDocument(options: DocumentIngestOptions): Promise<any> {
    const { file, userId, title, tags = [] } = options;

    // ── 1. Extract text ──────────────────────────────────────────────────────
    let extractedText = "";
    const fileMeta: Record<string, any> = { size: file.size, mimeType: file.mimetype };

    if (file.mimetype === "application/pdf") {
      const pdfData = await pdf(file.buffer);
      extractedText = pdfData.text;
      fileMeta.pages = pdfData.numpages;
    } else if (
      file.mimetype.startsWith("text/") ||
      file.mimetype.includes("markdown") ||
      file.mimetype.includes("json") ||
      file.mimetype.includes("csv")
    ) {
      extractedText = file.buffer.toString("utf-8");
    } else {
      throw new Error(`Unsupported file type: ${file.mimetype}`);
    }

    if (!extractedText.trim()) throw new Error("No readable text found in document");

    // ── 2. Create document record ────────────────────────────────────────────
    const document = await storage.createDocument({
      ownerId: userId,
      title,
      type: this.getDocumentType(file.mimetype),
      content: extractedText,
      tags,
      metadata: fileMeta,
    });

    // ── 3. Chunk + embed ─────────────────────────────────────────────────────
    const textChunks = this.chunkText(extractedText, { chunkSize: 1000, overlap: 200 });

    const results = await Promise.allSettled(
      textChunks.map(async (chunk, index) => {
        let embedding: number[] | undefined;
        try {
          embedding = await aiService.generateEmbedding(chunk.content);
        } catch (embErr) {
          console.warn(`[RAGService] Embedding failed for chunk ${index}:`, embErr);
        }

        return storage.createChunk({
          documentId: document.id,
          content: chunk.content,
          embedding: embedding ?? undefined,
          metadata: { chunkIndex: index, ...chunk.metadata },
        });
      })
    );

    const failed = results.filter(r => r.status === "rejected").length;
    if (failed) console.warn(`[RAGService] ${failed}/${textChunks.length} chunk(s) failed to store`);

    await storage.updateDocument(document.id, { embeddedAt: new Date() });
    console.log(`[RAGService] Ingested "${title}" — ${textChunks.length - failed} chunks with embeddings`);

    return document;
  }

  // ── Semantic query ──────────────────────────────────────────────────────────

  async query(options: {
    query: string;
    topK?: number;
    filters?: Record<string, any>;
  }): Promise<RAGQueryResult> {
    const { query, topK = 5 } = options;

    // Generate query embedding
    let queryEmbedding: number[];
    try {
      queryEmbedding = await aiService.generateEmbedding(query);
    } catch (embErr) {
      // Embedding unavailable — fall back to keyword search then direct AI
      console.warn("[RAGService] Embedding failed, falling back to keyword search:", embErr);
      return this.keywordFallback(query);
    }

    // Fetch all chunks that have stored embeddings
    const allChunks = await storage.getAllChunksWithEmbeddings();

    if (allChunks.length === 0) {
      return this.directAIAnswer(query, "No documents in knowledge base.");
    }

    // Rank by cosine similarity
    const ranked = allChunks
      .map(chunk => ({
        chunk,
        score: cosineSimilarity(queryEmbedding, chunk.embedding as number[]),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);

    // Fetch document titles for source labelling
    const docIds = [...new Set(ranked.map(r => r.chunk.documentId))];
    const docMap: Record<string, string> = {};
    await Promise.all(
      docIds.map(async id => {
        const doc = await storage.getDocument(id);
        if (doc) docMap[id] = doc.title;
      })
    );

    const sources = ranked.map(r => ({
      content: r.chunk.content,
      source: docMap[r.chunk.documentId] || "Unknown",
      relevanceScore: r.score,
      metadata: r.chunk.metadata,
    }));

    // Generate answer using retrieved context
    const contextualAnswer = await aiService.generateCybersecurityResponse(query, `${sources.length} knowledge-base sources retrieved`, sources);

    return {
      answer: contextualAnswer.content,
      sources,
      confidence: this.calcConfidence(sources),
    };
  }

  // ── Document management ─────────────────────────────────────────────────────

  async deleteDocument(documentId: string): Promise<void> {
    await storage.deleteDocumentChunks(documentId);
    await storage.deleteDocument(documentId);
  }

  async searchDocuments(userId: string, query: string): Promise<any[]> {
    const docs = await storage.getUserDocuments(userId);
    const q = query.toLowerCase();
    return docs.filter(d =>
      d.title.toLowerCase().includes(q) ||
      d.content?.toLowerCase().includes(q) ||
      d.tags?.some(t => t.toLowerCase().includes(q))
    );
  }

  // ── Private helpers ─────────────────────────────────────────────────────────

  private async directAIAnswer(query: string, note: string): Promise<RAGQueryResult> {
    const result = await aiService.generateCybersecurityResponse(query, note, []);
    return { answer: result.content, sources: [], confidence: 0.5 };
  }

  private async keywordFallback(query: string): Promise<RAGQueryResult> {
    try {
      const chunks = await storage.searchChunks(query, 5);
      if (chunks.length === 0) return this.directAIAnswer(query, "No matching documents");
      const sources = chunks.map(c => ({ content: c.content, source: "document", relevanceScore: 0.5 }));
      const result = await aiService.generateCybersecurityResponse(query, "Keyword-matched sources", sources);
      return { answer: result.content, sources, confidence: 0.4 };
    } catch {
      return this.directAIAnswer(query, "Knowledge base unavailable");
    }
  }

  private chunkText(text: string, opts: { chunkSize: number; overlap: number }) {
    const { chunkSize, overlap } = opts;
    const result: Array<{ content: string; metadata: any }> = [];
    let start = 0, idx = 0;
    while (start < text.length) {
      const end = Math.min(start + chunkSize, text.length);
      let actual = end;
      if (end < text.length) {
        const chunk = text.slice(start, end);
        const bp = Math.max(chunk.lastIndexOf(". "), chunk.lastIndexOf("\n"));
        if (bp > chunkSize * 0.7) actual = start + bp + 1;
      }
      const content = text.slice(start, actual).trim();
      if (content.length > 0) result.push({ content, metadata: { startOffset: start, endOffset: actual, chunkIndex: idx++ } });
      start = actual - overlap;
    }
    return result;
  }

  private getDocumentType(mime: string): string {
    if (mime === "application/pdf")   return "pdf";
    if (mime.includes("markdown"))    return "markdown";
    if (mime.includes("json"))        return "json";
    if (mime.startsWith("text/"))     return "text";
    return "unknown";
  }

  private calcConfidence(sources: Array<{ relevanceScore: number }>): number {
    if (!sources.length) return 0;
    const avg = sources.reduce((s, r) => s + r.relevanceScore, 0) / sources.length;
    return Math.min(avg * Math.min(sources.length / 3, 1), 1);
  }
}

export const ragService = new RAGService();
ragService.initialize().catch(console.error);
