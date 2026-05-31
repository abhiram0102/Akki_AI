import { eq, desc, and, like, sql, gte, lte, isNotNull, getTableColumns } from "drizzle-orm";
import { db } from "./db";
import {
  users, documents, chunks, sessions, messages, memories, toolRuns, findings, voiceInteractions,
  type User, type InsertUser, type Document, type InsertDocument, type Chunk, type InsertChunk,
  type Session, type InsertSession, type Message, type InsertMessage, type Memory, type InsertMemory,
  type ToolRun, type InsertToolRun, type Finding, type InsertFinding,
  type VoiceInteraction, type InsertVoiceInteraction
} from "@shared/schema";

export interface IStorage {
  // User operations
  getUser(id: string): Promise<User | undefined>;
  getUserByEmail(email: string): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  updateUser(id: string, updates: Partial<User>): Promise<User>;
  updateUserEmotionalState(id: string, emotionalState: User['emotionalState']): Promise<void>;

  // Document operations
  createDocument(document: InsertDocument): Promise<Document>;
  getDocument(id: string): Promise<Document | undefined>;
  getUserDocuments(userId: string): Promise<Document[]>;
  updateDocument(id: string, updates: Partial<Document>): Promise<Document>;
  deleteDocument(id: string): Promise<void>;

  // Chunk operations (for RAG)
  createChunk(chunk: InsertChunk): Promise<Chunk>;
  getDocumentChunks(documentId: string): Promise<Chunk[]>;
  searchChunks(query: string, limit?: number): Promise<Chunk[]>;
  getAllChunksWithEmbeddings(): Promise<Chunk[]>;
  deleteDocumentChunks(documentId: string): Promise<void>;

  // Session operations
  createSession(session: InsertSession): Promise<Session>;
  getSession(id: string): Promise<Session | undefined>;
  getUserSessions(userId: string, limit?: number): Promise<Session[]>;
  updateSession(id: string, updates: Partial<Session>): Promise<Session>;
  endSession(id: string): Promise<void>;

  // Message operations
  createMessage(message: InsertMessage): Promise<Message>;
  getSessionMessages(sessionId: string, limit?: number): Promise<Message[]>;
  updateMessage(id: string, updates: Partial<Message>): Promise<Message>;

  // Memory operations
  createMemory(memory: InsertMemory): Promise<Memory>;
  getUserMemories(userId: string, type?: string): Promise<Memory[]>;
  getRecentMemories(userId: string, limit?: number): Promise<Memory[]>;
  updateMemoryStrength(id: string, strength: number): Promise<void>;
  updateMemoryAccess(id: string): Promise<void>;
  deleteExpiredMemories(): Promise<void>;

  // Tool run operations
  createToolRun(toolRun: InsertToolRun): Promise<ToolRun>;
  getToolRun(id: string): Promise<ToolRun | undefined>;
  getSessionToolRuns(sessionId: string): Promise<ToolRun[]>;
  updateToolRun(id: string, updates: Partial<ToolRun>): Promise<ToolRun>;
  getPendingToolRuns(userId: string): Promise<ToolRun[]>;

  // Finding operations
  createFinding(finding: InsertFinding): Promise<Finding>;
  getSessionFindings(sessionId: string): Promise<Finding[]>;
  getUserFindings(userId: string, severity?: string): Promise<Finding[]>;
  updateFinding(id: string, updates: Partial<Finding>): Promise<Finding>;

  // Voice interaction operations
  createVoiceInteraction(interaction: InsertVoiceInteraction): Promise<VoiceInteraction>;
  getUserVoiceInteractions(userId: string, limit?: number): Promise<VoiceInteraction[]>;
  getSessionVoiceInteractions(sessionId: string): Promise<VoiceInteraction[]>;
}

export class DatabaseStorage implements IStorage {
  // User operations
  async getUser(id: string): Promise<User | undefined> {
    const [user] = await db.select().from(users).where(eq(users.id, id));
    return user || undefined;
  }

  async getUserByEmail(email: string): Promise<User | undefined> {
    const [user] = await db.select().from(users).where(eq(users.email, email));
    return user || undefined;
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    const [user] = await db.select().from(users).where(eq(users.username, username));
    return user || undefined;
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const [user] = await db.insert(users).values(insertUser).returning();
    return user;
  }

  async updateUser(id: string, updates: Partial<User>): Promise<User> {
    const [user] = await db
      .update(users)
      .set({ ...updates, lastActiveAt: new Date() })
      .where(eq(users.id, id))
      .returning();
    return user;
  }

  async updateUserEmotionalState(id: string, emotionalState: User['emotionalState']): Promise<void> {
    await db
      .update(users)
      .set({ emotionalState, lastActiveAt: new Date() })
      .where(eq(users.id, id));
  }

  // Document operations
  async createDocument(document: InsertDocument): Promise<Document> {
    const [doc] = await db.insert(documents).values(document).returning();
    return doc;
  }

  async getDocument(id: string): Promise<Document | undefined> {
    const [doc] = await db.select().from(documents).where(eq(documents.id, id));
    return doc || undefined;
  }

  async getUserDocuments(userId: string): Promise<Document[]> {
    return await db
      .select()
      .from(documents)
      .where(eq(documents.ownerId, userId))
      .orderBy(desc(documents.createdAt));
  }

  async updateDocument(id: string, updates: Partial<Document>): Promise<Document> {
    const [doc] = await db
      .update(documents)
      .set(updates)
      .where(eq(documents.id, id))
      .returning();
    return doc;
  }

  async deleteDocument(id: string): Promise<void> {
    await db.delete(documents).where(eq(documents.id, id));
  }

  // Chunk operations
  async createChunk(chunk: InsertChunk): Promise<Chunk> {
    const [newChunk] = await db.insert(chunks).values(chunk).returning();
    return newChunk;
  }

  async getDocumentChunks(documentId: string): Promise<Chunk[]> {
    return await db
      .select()
      .from(chunks)
      .where(eq(chunks.documentId, documentId));
  }

  async searchChunks(query: string, limit: number = 10): Promise<Chunk[]> {
    return await db
      .select()
      .from(chunks)
      .where(like(chunks.content, `%${query}%`))
      .limit(limit);
  }

  async getAllChunksWithEmbeddings(): Promise<Chunk[]> {
    return await db
      .select()
      .from(chunks)
      .where(isNotNull(chunks.embedding));
  }

  async deleteDocumentChunks(documentId: string): Promise<void> {
    await db.delete(chunks).where(eq(chunks.documentId, documentId));
  }

  // Session operations
  async createSession(session: InsertSession): Promise<Session> {
    const [newSession] = await db.insert(sessions).values(session).returning();
    return newSession;
  }

  async getSession(id: string): Promise<Session | undefined> {
    const [session] = await db.select().from(sessions).where(eq(sessions.id, id));
    return session || undefined;
  }

  async getUserSessions(userId: string, limit: number = 50): Promise<Session[]> {
    return await db
      .select()
      .from(sessions)
      .where(eq(sessions.ownerId, userId))
      .orderBy(desc(sessions.lastMessageAt))
      .limit(limit);
  }

  async updateSession(id: string, updates: Partial<Session>): Promise<Session> {
    const [session] = await db
      .update(sessions)
      .set({ ...updates, lastMessageAt: new Date() })
      .where(eq(sessions.id, id))
      .returning();
    return session;
  }

  async endSession(id: string): Promise<void> {
    await db
      .update(sessions)
      .set({ endedAt: new Date() })
      .where(eq(sessions.id, id));
  }

  // Message operations
  async createMessage(message: InsertMessage): Promise<Message> {
    const [newMessage] = await db.insert(messages).values(message).returning();
    
    // Update session's last message time
    await db
      .update(sessions)
      .set({ lastMessageAt: new Date() })
      .where(eq(sessions.id, message.sessionId));
    
    return newMessage;
  }

  async getSessionMessages(sessionId: string, limit: number = 100): Promise<Message[]> {
    return await db
      .select()
      .from(messages)
      .where(eq(messages.sessionId, sessionId))
      .orderBy(desc(messages.createdAt))
      .limit(limit);
  }

  async updateMessage(id: string, updates: Partial<Message>): Promise<Message> {
    const [message] = await db
      .update(messages)
      .set(updates)
      .where(eq(messages.id, id))
      .returning();
    return message;
  }

  // Memory operations
  async createMemory(memory: InsertMemory): Promise<Memory> {
    const [newMemory] = await db.insert(memories).values(memory).returning();
    return newMemory;
  }

  async getUserMemories(userId: string, type?: string): Promise<Memory[]> {
    const conditions = [eq(memories.ownerId, userId)];

    if (type) {
      conditions.push(eq(memories.type, type as any));
    }

    return await db
      .select()
      .from(memories)
      .where(and(...conditions))
      .orderBy(desc(memories.lastAccessed));
  }

  async getRecentMemories(userId: string, limit: number = 20): Promise<Memory[]> {
    return await db
      .select()
      .from(memories)
      .where(eq(memories.ownerId, userId))
      .orderBy(desc(memories.lastAccessed))
      .limit(limit);
  }

  async updateMemoryStrength(id: string, strength: number): Promise<void> {
    await db
      .update(memories)
      .set({ strength, lastAccessed: new Date() })
      .where(eq(memories.id, id));
  }

  async updateMemoryAccess(id: string): Promise<void> {
    await db
      .update(memories)
      .set({ lastAccessed: new Date() })
      .where(eq(memories.id, id));
  }

  async deleteExpiredMemories(): Promise<void> {
    await db
      .delete(memories)
      .where(and(
        isNotNull(memories.expiresAt),
        lte(memories.expiresAt, new Date())
      ));
  }

  // Tool run operations
  async createToolRun(toolRun: InsertToolRun): Promise<ToolRun> {
    const [newToolRun] = await db.insert(toolRuns).values(toolRun).returning();
    return newToolRun;
  }

  async getToolRun(id: string): Promise<ToolRun | undefined> {
    const [toolRun] = await db.select().from(toolRuns).where(eq(toolRuns.id, id));
    return toolRun || undefined;
  }

  async getSessionToolRuns(sessionId: string): Promise<ToolRun[]> {
    return await db
      .select()
      .from(toolRuns)
      .where(eq(toolRuns.sessionId, sessionId))
      .orderBy(desc(toolRuns.createdAt));
  }

  async updateToolRun(id: string, updates: Partial<ToolRun>): Promise<ToolRun> {
    const [toolRun] = await db
      .update(toolRuns)
      .set(updates)
      .where(eq(toolRuns.id, id))
      .returning();
    return toolRun;
  }

  async getPendingToolRuns(userId: string): Promise<ToolRun[]> {
    const results = await db
      .select({ toolRuns: getTableColumns(toolRuns) })
      .from(toolRuns)
      .innerJoin(sessions, eq(toolRuns.sessionId, sessions.id))
      .where(
        and(
          eq(sessions.ownerId, userId),
          eq(toolRuns.status, "pending"),
          eq(toolRuns.approvalRequired, true)
        )
      )
      .orderBy(desc(toolRuns.createdAt));
    return results.map(r => r.toolRuns);
  }

  // Finding operations
  async createFinding(finding: InsertFinding): Promise<Finding> {
    const [newFinding] = await db.insert(findings).values(finding).returning();
    return newFinding;
  }

  async getSessionFindings(sessionId: string): Promise<Finding[]> {
    return await db
      .select()
      .from(findings)
      .where(eq(findings.sessionId, sessionId))
      .orderBy(desc(findings.createdAt));
  }

  async getUserFindings(userId: string, severity?: string): Promise<Finding[]> {
    const conditions = [eq(sessions.ownerId, userId)];

    if (severity) {
      conditions.push(eq(findings.severity, severity as any));
    }

    const results = await db
      .select({ findings: getTableColumns(findings) })
      .from(findings)
      .innerJoin(sessions, eq(findings.sessionId, sessions.id))
      .where(and(...conditions))
      .orderBy(desc(findings.createdAt));

    return results.map(r => r.findings);
  }

  async updateFinding(id: string, updates: Partial<Finding>): Promise<Finding> {
    const [finding] = await db
      .update(findings)
      .set({ ...updates, updatedAt: new Date() })
      .where(eq(findings.id, id))
      .returning();
    return finding;
  }

  // Voice interaction operations
  async createVoiceInteraction(interaction: InsertVoiceInteraction): Promise<VoiceInteraction> {
    const [newInteraction] = await db.insert(voiceInteractions).values(interaction).returning();
    return newInteraction;
  }

  async getUserVoiceInteractions(userId: string, limit: number = 50): Promise<VoiceInteraction[]> {
    return await db
      .select()
      .from(voiceInteractions)
      .where(eq(voiceInteractions.userId, userId))
      .orderBy(desc(voiceInteractions.createdAt))
      .limit(limit);
  }

  async getSessionVoiceInteractions(sessionId: string): Promise<VoiceInteraction[]> {
    return await db
      .select()
      .from(voiceInteractions)
      .where(eq(voiceInteractions.sessionId, sessionId))
      .orderBy(desc(voiceInteractions.createdAt));
  }
}

export const storage = new DatabaseStorage();
