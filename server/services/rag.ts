import { ChromaClient, type EmbeddingFunction as IEmbeddingFunction } from "chromadb";
import pdf from "pdf-parse";
import { storage } from "../storage";
import { aiService } from "./ai";
import type { InsertDocument, InsertChunk } from "@shared/schema";

// Custom embedding function wrapping Gemini embeddings for ChromaDB v3 compatibility
const geminiEmbeddingFunction: IEmbeddingFunction = {
  generate: async (texts: string[]): Promise<number[][]> => {
    return Promise.all(texts.map((text) => aiService.generateEmbedding(text)));
  },
};

const chromaClient = new ChromaClient({
  path: process.env.CHROMA_URL || "http://localhost:8000",
});

// Flag to track if ChromaDB is available
let chromaAvailable = false;

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

class RAGService {
  private collectionName = "cybersecurity_docs";
  private collection: any;

  async initialize() {
    try {
      this.collection = await chromaClient.getOrCreateCollection({
        name: this.collectionName,
        metadata: { "hnsw:space": "cosine" },
        embeddingFunction: geminiEmbeddingFunction,
      });
      console.log("[RAGService] Initialized successfully");
      chromaAvailable = true;
    } catch (error) {
      console.error("[RAGService] Initialization error:", error);
      console.log("[RAGService] ChromaDB not available — RAG features disabled");
      chromaAvailable = false;
    }
  }

  async ingestDocument(options: DocumentIngestOptions): Promise<any> {
    if (!chromaAvailable) {
      throw new Error("Vector database not available. Document ingestion is disabled.");
    }

    const { file, userId, title, tags = [] } = options;

    let extractedText = "";
    const metadata: Record<string, any> = {
      size: file.size,
      mimeType: file.mimetype,
    };

    if (file.mimetype === "application/pdf") {
      const pdfData = await pdf(file.buffer);
      extractedText = pdfData.text;
      metadata.pages = pdfData.numpages;
    } else if (file.mimetype.startsWith("text/") || file.mimetype.includes("markdown")) {
      extractedText = file.buffer.toString("utf-8");
    } else {
      throw new Error(`Unsupported file type: ${file.mimetype}`);
    }

    const document = await storage.createDocument({
      ownerId: userId,
      title,
      type: this.getDocumentType(file.mimetype),
      content: extractedText,
      tags,
      metadata,
    });

    const chunks = this.chunkText(extractedText, { chunkSize: 1000, overlap: 200 });

    const chunkResults = await Promise.allSettled(
      chunks.map(async (chunk, index) => {
        const embedding = await aiService.generateEmbedding(chunk.content);

        await this.collection.add({
          ids: [`${document.id}_chunk_${index}`],
          embeddings: [embedding],
          documents: [chunk.content],
          metadatas: [{
            documentId: document.id,
            chunkIndex: index,
            title,
            tags: tags.join(","),
            ...chunk.metadata,
          }],
        });

        return storage.createChunk({
          documentId: document.id,
          content: chunk.content,
          embedding,
          metadata: { chunkIndex: index, ...chunk.metadata },
        });
      })
    );

    const failed = chunkResults.filter(r => r.status === "rejected");
    if (failed.length > 0) {
      console.error(`[RAGService] ${failed.length} chunk(s) failed to ingest`);
    }

    await storage.updateDocument(document.id, { embeddedAt: new Date() });

    return document;
  }

  async query(options: {
    query: string;
    topK?: number;
    filters?: Record<string, any>;
  }): Promise<RAGQueryResult> {
    if (!chromaAvailable) {
      const directAnswer = await aiService.generateCybersecurityResponse(
        options.query,
        "No knowledge base available — providing direct AI response",
        []
      );
      return { answer: directAnswer.content, sources: [], confidence: 0.5 };
    }

    const { query, topK = 5, filters = {} } = options;
    const queryEmbedding = await aiService.generateEmbedding(query);

    const searchResults = await this.collection.query({
      queryEmbeddings: [queryEmbedding],
      nResults: topK,
      ...(Object.keys(filters).length > 0 ? { where: filters } : {}),
    });

    const sources = (searchResults.documents[0] as string[]).map((doc, index) => ({
      content: doc,
      source: searchResults.metadatas[0][index]?.title || "Unknown",
      relevanceScore: 1 - (searchResults.distances[0][index] || 0),
      metadata: searchResults.metadatas[0][index],
    }));

    const contextualAnswer = await aiService.generateCybersecurityResponse(
      query,
      `${sources.length} relevant knowledge base sources found`,
      sources
    );

    return {
      answer: contextualAnswer.content,
      sources,
      confidence: this.calculateConfidence(sources),
    };
  }

  async deleteDocument(documentId: string): Promise<void> {
    if (chromaAvailable) {
      const chunks = await storage.getDocumentChunks(documentId);
      const chunkIds = chunks.map((_, index) => `${documentId}_chunk_${index}`);
      if (chunkIds.length > 0) {
        await this.collection.delete({ ids: chunkIds });
      }
    }
    await storage.deleteDocumentChunks(documentId);
    await storage.deleteDocument(documentId);
  }

  async searchDocuments(userId: string, query: string): Promise<any[]> {
    const userDocuments = await storage.getUserDocuments(userId);
    const q = query.toLowerCase();
    return userDocuments.filter(
      (doc) =>
        doc.title.toLowerCase().includes(q) ||
        doc.content?.toLowerCase().includes(q) ||
        doc.tags?.some((tag) => tag.toLowerCase().includes(q))
    );
  }

  private chunkText(
    text: string,
    options: { chunkSize: number; overlap: number }
  ): Array<{ content: string; metadata: any }> {
    const { chunkSize, overlap } = options;
    const chunks: Array<{ content: string; metadata: any }> = [];
    let startIndex = 0;
    let chunkIndex = 0;

    while (startIndex < text.length) {
      const endIndex = Math.min(startIndex + chunkSize, text.length);
      const chunkContent = text.slice(startIndex, endIndex);

      let actualEndIndex = endIndex;
      if (endIndex < text.length) {
        const lastPeriod = chunkContent.lastIndexOf(". ");
        const lastNewline = chunkContent.lastIndexOf("\n");
        const breakPoint = Math.max(lastPeriod, lastNewline);
        if (breakPoint > chunkSize * 0.7) {
          actualEndIndex = startIndex + breakPoint + 1;
        }
      }

      const finalContent = text.slice(startIndex, actualEndIndex).trim();
      if (finalContent.length > 0) {
        chunks.push({
          content: finalContent,
          metadata: { startOffset: startIndex, endOffset: actualEndIndex, chunkIndex },
        });
      }

      startIndex = actualEndIndex - overlap;
      chunkIndex++;
    }

    return chunks;
  }

  private getDocumentType(mimeType: string): string {
    if (mimeType === "application/pdf") return "pdf";
    if (mimeType.includes("markdown")) return "markdown";
    if (mimeType.startsWith("text/")) return "text";
    if (mimeType.includes("json")) return "json";
    return "unknown";
  }

  private calculateConfidence(sources: any[]): number {
    if (sources.length === 0) return 0;
    const avgRelevance =
      sources.reduce((sum, s) => sum + s.relevanceScore, 0) / sources.length;
    const sourceQuality = Math.min(sources.length / 3, 1);
    return Math.min(avgRelevance * sourceQuality, 1);
  }
}

export const ragService = new RAGService();
ragService.initialize().catch(console.error);
