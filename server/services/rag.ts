import { ChromaClient } from "chromadb";
import pdf from "pdf-parse";
import { storage } from "../storage";
import { aiService } from "./ai";
import type { InsertDocument, InsertChunk } from "@shared/schema";
const chromaClient = new ChromaClient({
  path: process.env.CHROMA_URL || "http://localhost:8000"
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
      // Create or get collection
      this.collection = await chromaClient.getOrCreateCollection({
        name: this.collectionName,
        metadata: { "hnsw:space": "cosine" },
        embeddingFunction: null // ✅ Tell Chroma we’re handling embeddings ourselves
      });
      console.log("RAG service initialized successfully");
      chromaAvailable = true;
    } catch (error) {
      console.error("RAG service initialization error:", error);
      console.log("⚠️ ChromaDB not available - RAG features will be disabled");
      chromaAvailable = false;
      // Don't throw - allow app to continue without vector storage
    }
  }

  async ingestDocument(options: DocumentIngestOptions): Promise<any> {
    if (!chromaAvailable) {
      console.log("⚠️ ChromaDB not available - document ingestion disabled");
      throw new Error("Vector database not available. Please try again later.");
    }
    
    try {
      const { file, userId, title, tags = [] } = options;
      
      // Extract text based on file type
      let extractedText = "";
      let metadata: any = {
        size: file.size,
        mimeType: file.mimetype
      };

      if (file.mimetype === "application/pdf") {
        const pdfData = await pdf(file.buffer);
        extractedText = pdfData.text;
        metadata.pages = pdfData.numpages;
      } else if (file.mimetype.startsWith("text/")) {
        extractedText = file.buffer.toString("utf-8");
      } else if (file.mimetype.includes("markdown")) {
        extractedText = file.buffer.toString("utf-8");
      } else {
        throw new Error("Unsupported file type");
      }

      // Create document record
      const document = await storage.createDocument({
        ownerId: userId,
        title,
        type: this.getDocumentType(file.mimetype),
        content: extractedText,
        tags,
        metadata
      });

      // Chunk the document
      const chunks = this.chunkText(extractedText, {
        chunkSize: 1000,
        overlap: 200
      });

      // Generate embeddings and store chunks
      const chunkPromises = chunks.map(async (chunk, index) => {
        const embedding = await aiService.generateEmbedding(chunk.content);
        
        // Store in vector database
        await this.collection.add({
          ids: [`${document.id}_chunk_${index}`],
          embeddings: [embedding],
          documents: [chunk.content],
          metadatas: [{
            documentId: document.id,
            chunkIndex: index,
            title,
            tags: tags.join(","),
            ...chunk.metadata
          }]
        });

        // Store in PostgreSQL
        return storage.createChunk({
          documentId: document.id,
          content: chunk.content,
          embedding,
          metadata: {
            chunkIndex: index,
            ...chunk.metadata
          }
        });
      });

      await Promise.all(chunkPromises);

      // Update document with embedding timestamp
      await storage.updateDocument(document.id, {
        embeddedAt: new Date()
      });

      return document;
    } catch (error) {
      console.error("Document ingestion error:", error);
      throw error;
    }
  }

  async query(options: {
    query: string;
    topK?: number;
    filters?: Record<string, any>;
  }): Promise<RAGQueryResult> {
    if (!chromaAvailable) {
      // Fallback to direct AI response without RAG
      const directAnswer = await aiService.generateCybersecurityResponse(
        options.query,
        "ChromaDB not available - providing direct AI response",
        []
      );
      
      return {
        answer: directAnswer.content,
        sources: [],
        confidence: 0.5 // Lower confidence without RAG context
      };
    }
    
    try {
      const { query, topK = 5, filters = {} } = options;

      // Generate query embedding
      const queryEmbedding = await aiService.generateEmbedding(query);

      // Search vector database
      const searchResults = await this.collection.query({
        queryEmbeddings: [queryEmbedding],
        nResults: topK,
        where: filters
      });

      // Format search results
      const sources = searchResults.documents[0].map((doc: string, index: number) => ({
        content: doc,
        source: searchResults.metadatas[0][index]?.title || "Unknown",
        relevanceScore: 1 - (searchResults.distances[0][index] || 0),
        metadata: searchResults.metadatas[0][index]
      }));

      // Generate contextual answer using RAG
      const contextualAnswer = await aiService.generateCybersecurityResponse(
        query,
        `RAG Query Context: ${sources.length} relevant sources found`,
        sources
      );

      return {
        answer: contextualAnswer.content,
        sources,
        confidence: this.calculateConfidence(sources)
      };
    } catch (error) {
      console.error("RAG query error:", error);
      throw error;
    }
  }

  private chunkText(
    text: string,
    options: { chunkSize: number; overlap: number }
  ): Array<{ content: string; metadata: any }> {
    const { chunkSize, overlap } = options;
    const chunks: Array<{ content: string; metadata: any }> = [];
    
    // Simple chunking strategy - can be improved with sentence boundary detection
    let startIndex = 0;
    let chunkIndex = 0;
    
    while (startIndex < text.length) {
      const endIndex = Math.min(startIndex + chunkSize, text.length);
      const chunkContent = text.slice(startIndex, endIndex);
      
      // Try to break at sentence boundaries
      let actualEndIndex = endIndex;
      if (endIndex < text.length) {
        const lastPeriod = chunkContent.lastIndexOf('. ');
        const lastNewline = chunkContent.lastIndexOf('\n');
        const breakPoint = Math.max(lastPeriod, lastNewline);
        
        if (breakPoint > chunkSize * 0.7) { // Don't make chunks too small
          actualEndIndex = startIndex + breakPoint + 1;
        }
      }
      
      const finalContent = text.slice(startIndex, actualEndIndex);
      
      chunks.push({
        content: finalContent.trim(),
        metadata: {
          startOffset: startIndex,
          endOffset: actualEndIndex,
          chunkIndex
        }
      });
      
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
    
    const avgRelevance = sources.reduce((sum, source) => sum + source.relevanceScore, 0) / sources.length;
    const sourceQuality = sources.length >= 3 ? 1 : sources.length / 3;
    
    return Math.min(avgRelevance * sourceQuality, 1);
  }

  async deleteDocument(documentId: string): Promise<void> {
    try {
      // Delete from vector database
      const chunks = await storage.getDocumentChunks(documentId);
      const chunkIds = chunks.map((_, index) => `${documentId}_chunk_${index}`);
      
      if (chunkIds.length > 0) {
        await this.collection.delete({
          ids: chunkIds
        });
      }

      // Delete from PostgreSQL
      await storage.deleteDocumentChunks(documentId);
      await storage.deleteDocument(documentId);
    } catch (error) {
      console.error("Document deletion error:", error);
      throw error;
    }
  }

  async searchDocuments(userId: string, query: string): Promise<any[]> {
    try {
      const userDocuments = await storage.getUserDocuments(userId);
      return userDocuments.filter(doc => 
        doc.title.toLowerCase().includes(query.toLowerCase()) ||
        doc.content?.toLowerCase().includes(query.toLowerCase()) ||
        (doc.tags && doc.tags.some(tag => tag.toLowerCase().includes(query.toLowerCase())))
      );
    } catch (error) {
      console.error("Document search error:", error);
      throw error;
    }
  }
}

export const ragService = new RAGService();

// Initialize the service
ragService.initialize().catch(console.error);
