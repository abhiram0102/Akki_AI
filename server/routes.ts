import type { Express } from "express";
import { createServer, type Server } from "http";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";
import multer from "multer";
import { z } from "zod";
import { storage } from "./storage";

import { authMiddleware } from "./middleware/auth";
import { aiService } from "./services/ai";
import { ragService } from "./services/rag";
import { voiceService } from "./services/voice";
import { emotionalAI } from "./services/emotional-ai";
import { toolsService } from "./services/tools";
import { agentService } from "./services/agent";
import { insertUserSchema, insertSessionSchema, insertMessageSchema } from "@shared/schema";

const upload = multer({ 
  storage: multer.memoryStorage(),
  limits: { fileSize: 50 * 1024 * 1024 } // 50MB limit
});

const JWT_SECRET = process.env.JWT_SECRET || "your-secret-key";

// Validation schemas
const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

const registerSchema = insertUserSchema.extend({
  confirmPassword: z.string(),
}).refine(data => data.password === data.confirmPassword, {
  message: "Passwords don't match",
  path: ["confirmPassword"],
});

const chatMessageSchema = z.object({
  content: z.string().min(1),
  sessionId: z.string().uuid().nullable().optional(),
  voiceInput: z.boolean().optional(),
  emotionalTone: z.string().optional(),
});

const voiceTranscriptionSchema = z.object({
  audioData: z.string(), // Base64 encoded audio
  sessionId: z.string().uuid().optional(),
});

const ragQuerySchema = z.object({
  query: z.string().min(1),
  topK: z.number().int().min(1).max(20).default(5),
  filters: z.record(z.any()).optional(),
});

const toolExecutionSchema = z.object({
  toolName: z.string(),
  arguments: z.record(z.any()),
  sessionId: z.string().uuid(),
  requiresApproval: z.boolean().optional(),
});

export async function registerRoutes(app: Express): Promise<Server> {
  
  // Authentication routes
  app.post("/api/auth/register", async (req, res) => {
    try {
      const data = registerSchema.parse(req.body);
      
      // Check if user exists
      const existingUser = await storage.getUserByEmail(data.email);
      if (existingUser) {
        return res.status(400).json({ message: "User already exists" });
      }
      
      // Hash password
      const hashedPassword = await bcrypt.hash(data.password, 12);
      
      // Create user
      const user = await storage.createUser({
        email: data.email,
        username: data.username,
        password: hashedPassword,
        role: data.role || "analyst",
        preferences: data.preferences || {},
        emotionalState: {
          bondLevel: 0,
          currentMood: "neutral",
          trustLevel: 0.5,
          personalityTraits: [],
          preferredCommunicationStyle: "professional"
        }
      });
      
      // Generate JWT
      const token = jwt.sign({ userId: user.id, role: user.role }, JWT_SECRET, { expiresIn: "7d" });
      
      res.json({
        user: { ...user, password: undefined },
        token
      });
    } catch (error) {
      console.error("Registration error:", error);
      res.status(400).json({ message: error instanceof Error ? error.message : "Registration failed" });
    }
  });

  app.post("/api/auth/login", async (req, res) => {
    try {
      const { email, password } = loginSchema.parse(req.body);
      
      // Find user
      const user = await storage.getUserByEmail(email);
      if (!user) {
        return res.status(401).json({ message: "Invalid credentials" });
      }
      
      // Verify password
      const validPassword = await bcrypt.compare(password, user.password);
      if (!validPassword) {
        return res.status(401).json({ message: "Invalid credentials" });
      }
      
      // Update last active
      await storage.updateUser(user.id, { lastActiveAt: new Date() });
      
      // Generate JWT
      const token = jwt.sign({ userId: user.id, role: user.role }, JWT_SECRET, { expiresIn: "7d" });
      
      res.json({
        user: { ...user, password: undefined },
        token
      });
    } catch (error) {
      console.error("Login error:", error);
      res.status(400).json({ message: error instanceof Error ? error.message : "Login failed" });
    }
  });

  // Protected routes
  app.use("/api/protected", authMiddleware);

  // Chat routes
  app.post("/api/protected/chat/message", async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }

      const data = chatMessageSchema.parse(req.body);
      const userId = (req.user as import("@shared/schema").User).id;
      let sessionId = data.sessionId;
      
      // Create new session if not provided
      if (!sessionId) {
        const newSession = await storage.createSession({
          ownerId: userId,
          title: `Chat Session - ${new Date().toLocaleString()}`,
          mode: "chat",
          context: { workspace: "chat" }
        });
        sessionId = newSession.id;
      }
      
      // 2. Save user message
      const userMessage = await storage.createMessage({
        sessionId,
        role: "user",
        content: data.content,
        metadata: {
          voiceInput: data.voiceInput || false,
          emotionalTone: data.emotionalTone
        }
      });

      // Update emotional state based on interaction
      if (data.emotionalTone) {
        await emotionalAI.updateEmotionalBond(userId, data.emotionalTone, data.content);
      }

      let agentResponse;
      try {
        // Get response from AI agent
        agentResponse = await agentService.processMessage({
        message: data.content,
        sessionId,
        userId,
        voiceInput: data.voiceInput || false
      });
      } catch (agentError) {
        console.error("Agent Service Error:", agentError);
        // Create a user-friendly error message to send back
        const assistantErrorMessage = await storage.createMessage({
          sessionId,
          role: "assistant",
          content: "I apologize, but I encountered an error while processing your request. Please try again shortly.",
          metadata: { error: true }
        });
        return res.status(200).json({
          userMessage,
          assistantMessage: assistantErrorMessage,
          sessionId
        });
      }

      // Create assistant message
      const assistantMessage = await storage.createMessage({
        sessionId,
        role: "assistant",
        content: agentResponse.content,
        toolCalls: agentResponse.toolCalls || [],
        metadata: {
          ragUsed: agentResponse.ragUsed,
          sources: agentResponse.sources,
          emotionalTone: agentResponse.emotionalTone
        }
      });

      res.json({
        userMessage,
        assistantMessage,
        sessionId,
        agentPlan: agentResponse.plan
      });
    } catch (error) {
      console.error("Chat error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Chat failed" });
    }
  });

  // Voice routes
  app.post("/api/protected/voice/transcribe", async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      const userId = (req.user as import("@shared/schema").User).id;
      const data = voiceTranscriptionSchema.parse(req.body);
      
      const transcription = await voiceService.transcribeAudio(data.audioData);
      
      // Store voice interaction
      const voiceInteraction = await storage.createVoiceInteraction({
        sessionId: data.sessionId || "",
        userId,
        transcription: transcription.text,
        audioData: data.audioData,
        confidence: transcription.confidence,
        emotionalTone: transcription.emotionalTone,
        voicePattern: transcription.voicePattern,
        wakeWordDetected: transcription.wakeWordDetected,
        processingTime: transcription.processingTime
      });

      res.json(voiceInteraction);
    } catch (error) {
      console.error("Voice transcription error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Transcription failed" });
    }
  });

  app.post("/api/protected/voice/synthesize", async (req, res) => {
    try {
      const { text, emotionalTone } = req.body;
      
      const audioData = await voiceService.synthesizeSpeech(text, emotionalTone);
      
      res.json({ audioData });
    } catch (error) {
      console.error("Voice synthesis error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Speech synthesis failed" });
    }
  });

  // RAG routes
  app.post("/api/protected/rag/ingest", upload.single("file"), async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      const userId = (req.user as import("@shared/schema").User).id;
      
      if (!req.file) {
        return res.status(400).json({ message: "No file uploaded" });
      }
      
      const document = await ragService.ingestDocument({
        file: req.file,
        userId,
        title: req.body.title || req.file.originalname,
        tags: req.body.tags ? JSON.parse(req.body.tags) : []
      });

      res.json(document);
    } catch (error) {
      console.error("Document ingestion error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Document ingestion failed" });
    }
  });

  app.post("/api/protected/rag/query", async (req, res) => {
    try {
      const data = ragQuerySchema.parse(req.body);
      
      const results = await ragService.query({
        query: data.query,
        topK: data.topK,
        filters: data.filters
      });

      res.json(results);
    } catch (error) {
      console.error("RAG query error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "RAG query failed" });
    }
  });

  // Tool execution routes
  app.post("/api/protected/tools/execute", async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      const userId = (req.user as import("@shared/schema").User).id;
      const data = toolExecutionSchema.parse(req.body);
      
      // Create tool run record
      const toolRun = await storage.createToolRun({
        sessionId: data.sessionId,
        toolName: data.toolName,
        arguments: data.arguments,
        status: data.requiresApproval ? "pending" : "running",
        approvalRequired: data.requiresApproval || false,
        riskLevel: toolsService.assessRiskLevel(data.toolName, data.arguments)
      });

      // Execute tool if no approval required
      if (!data.requiresApproval) {
        const result = await toolsService.executeTool(data.toolName, data.arguments);
        
        await storage.updateToolRun(toolRun.id, {
          status: "completed",
          result,
          executedAt: new Date(),
          completedAt: new Date()
        });

        return res.json({ toolRun, result, requiresApproval: false });
      }

      res.json({ toolRun, requiresApproval: true });
    } catch (error) {
      console.error("Tool execution error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Tool execution failed" });
    }
  });

  app.post("/api/protected/tools/:id/approve", async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      const userId = (req.user as import("@shared/schema").User).id;
      const toolRunId = req.params.id;
      
      const toolRun = await storage.getToolRun(toolRunId);
      if (!toolRun) {
        return res.status(404).json({ message: "Tool run not found" });
      }

      // Execute approved tool
      const result = await toolsService.executeTool(toolRun.toolName, toolRun.arguments);
      
      await storage.updateToolRun(toolRunId, {
        status: "completed",
        result,
        approvedBy: userId,
        approvedAt: new Date(),
        executedAt: new Date(),
        completedAt: new Date()
      });

      res.json({ success: true, result });
    } catch (error) {
      console.error("Tool approval error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Tool approval failed" });
    }
  });

  // Memory routes
  app.get("/api/protected/memory", async (req, res) => {
  try {
    if (!req.user) {
      return res.status(401).json({ message: "User not authenticated" });
    }
    const userId: string = (req.user as import("@shared/schema").User).id;
    const type = req.query.type as string;
    
    const memories = await storage.getUserMemories(userId, type);
    
    res.json(memories);
  } catch (error) {
    console.error("Memory retrieval error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Memory retrieval failed" });
  }
});

// Session routes
app.get("/api/protected/sessions", async (req, res) => {
  try {
    if (!req.user) {
      return res.status(401).json({ message: "User not authenticated" });
    }
    const userId: string = (req.user as import("@shared/schema").User).id;
    const limit = parseInt(req.query.limit as string) || 50;
    
    const sessions = await storage.getUserSessions(userId, limit);
    
    res.json(sessions);
  } catch (error) {
    console.error("Sessions retrieval error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Sessions retrieval failed" });
  }
});

app.get("/api/protected/sessions/:id/messages", async (req, res) => {
  try {
    const sessionId = req.params.id;
    const limit = parseInt(req.query.limit as string) || 100;
    
    const messages = await storage.getSessionMessages(sessionId, limit);
    
    res.json(messages.reverse()); // Return in chronological order
  } catch (error) {
    console.error("Messages retrieval error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Messages retrieval failed" });
  }
});

// User profile routes
app.get("/api/protected/profile", async (req, res) => {
  try {
    if (!req.user) {
      return res.status(401).json({ message: "User not authenticated" });
    }
    const userId: string = (req.user as import("@shared/schema").User).id;
    
    const user = await storage.getUser(userId);
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }
    
    res.json({ ...user, password: undefined });
  } catch (error) {
    console.error("Profile retrieval error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Profile retrieval failed" });
  }
});

app.put("/api/protected/profile", async (req, res) => {
  try {
    if (!req.user) {
      return res.status(401).json({ message: "User not authenticated" });
    }
    const userId: string = (req.user as import("@shared/schema").User).id;
    const updates = req.body;
    
    // Remove sensitive fields
    delete updates.id;
    delete updates.password;
    delete updates.createdAt;
    
    const user = await storage.updateUser(userId, updates);
    
    res.json({ ...user, password: undefined });
  } catch (error) {
    console.error("Profile update error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Profile update failed" });
  }
});

// Health check
app.get("/api/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

  const httpServer = createServer(app);
  return httpServer;
}
