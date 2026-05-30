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
if (!process.env.JWT_SECRET) {
  console.warn("[SECURITY WARNING] JWT_SECRET env var is not set — using insecure default. Set JWT_SECRET in your environment.");
}

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
        // Enhanced AI agent processing with cybersecurity focus
        agentResponse = await agentService.processMessage({
          message: data.content,
          sessionId,
          userId,
          voiceInput: data.voiceInput || false,
          context: {
            emotionalTone: data.emotionalTone,
            workspace: "chat",
            capabilities: ["multimodal", "exploits", "osint", "reports", "rag"]
          }
        });
      } catch (agentError) {
        console.error("Agent Service Error:", agentError);
        // Enhanced error handling with context
        const assistantErrorMessage = await storage.createMessage({
          sessionId,
          role: "assistant",
          content: `I encountered an issue processing your cybersecurity request. This might be due to:
          
• Network connectivity for external tools
• API rate limits for advanced analysis
• Complex queries requiring more context

Please try rephrasing your request or provide more specific details about what you'd like me to help you with.`,
          metadata: { 
            error: true
          }
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

  // Advanced multi-modal cybersecurity analysis routes
  app.post("/api/protected/analysis/multimodal", upload.array("files", 10), async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      
      const { text, context } = req.body;
      const files = req.files as Express.Multer.File[];
      
      // Separate images from other files
      const images = files?.filter(file => file.mimetype.startsWith('image/'))
        .map(file => file.buffer) || [];
      
      const analysis = await aiService.analyzeMultiModalContent(
        text || "Analyze the provided content for cybersecurity insights",
        images.length > 0 ? images : undefined
      );
      
      res.json({
        analysis,
        filesAnalyzed: files?.length || 0,
        imagesAnalyzed: images.length,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      console.error("Multi-modal analysis error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Analysis failed" });
    }
  });

  app.post("/api/protected/exploits/generate", async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      
      const { vulnerability, target, constraints } = req.body;
      
      if (!vulnerability || !target) {
        return res.status(400).json({ message: "Vulnerability and target are required" });
      }
      
      const exploit = await aiService.generateExploitPoC(vulnerability, target, constraints);
      
      // Log the exploit generation for audit purposes
      console.log(`Exploit PoC generated for user ${(req.user as any).id}: ${vulnerability}`);
      
      res.json({
        exploit,
        timestamp: new Date().toISOString(),
        warnings: [
          "This is for educational and authorized testing only",
          "Ensure you have proper authorization before testing",
          "Use only in controlled environments"
        ]
      });
    } catch (error) {
      console.error("Exploit generation error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Exploit generation failed" });
    }
  });

  app.post("/api/protected/osint/strategy", async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      
      const { target, objectives, constraints } = req.body;
      
      if (!target || !objectives || !Array.isArray(objectives)) {
        return res.status(400).json({ message: "Target and objectives array are required" });
      }
      
      const strategy = await aiService.generateOSINTStrategy(target, objectives, constraints);
      
      res.json({
        strategy,
        timestamp: new Date().toISOString(),
        disclaimer: "Ensure all reconnaissance activities are authorized and legal"
      });
    } catch (error) {
      console.error("OSINT strategy error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Strategy generation failed" });
    }
  });

  app.post("/api/protected/reports/generate", async (req, res) => {
    try {
      if (!req.user) {
        return res.status(401).json({ message: "User not authenticated" });
      }
      
      const { findings, executiveSummary, scope } = req.body;
      
      if (!findings || !Array.isArray(findings)) {
        return res.status(400).json({ message: "Findings array is required" });
      }
      
      const report = await aiService.generatePentestReport(findings, executiveSummary, scope);
      
      res.json({
        report,
        timestamp: new Date().toISOString(),
        downloadUrl: `/api/protected/reports/download/${Date.now()}` // Would implement actual file serving
      });
    } catch (error) {
      console.error("Report generation error:", error);
      res.status(500).json({ message: error instanceof Error ? error.message : "Report generation failed" });
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

// Coding workspace routes
app.post("/api/coding/analyze", authMiddleware, async (req, res) => {
  try {
    const { code, language } = req.body;
    
    const analysisPrompt = `You are a cybersecurity expert performing code security analysis. Analyze the following ${language} code for vulnerabilities, security issues, and provide recommendations.

Code to analyze:
\`\`\`${language}
${code}
\`\`\`

Provide your analysis in the following JSON format:
{
  "vulnerabilities": [
    {
      "type": "SQL Injection",
      "severity": "high",
      "description": "User input not properly sanitized before database query",
      "line": 15,
      "suggestion": "Use parameterized queries or prepared statements"
    }
  ],
  "securityScore": 65,
  "mitreTags": ["T1059", "T1055"],
  "exploitPotential": "SQL injection could allow data extraction or modification",
  "recommendations": ["Input validation", "Parameterized queries", "Least privilege access"]
}`;

    const analysis = await aiService.chatCompletion(
      [{ role: "user", content: analysisPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const parsedAnalysis = JSON.parse(analysis);
    
    res.json({
      id: Date.now().toString(),
      code,
      language,
      ...parsedAnalysis,
      createdAt: new Date().toISOString()
    });
  } catch (error) {
    console.error("Code analysis error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Analysis failed" });
  }
});

app.post("/api/coding/generate-exploit", authMiddleware, async (req, res) => {
  try {
    const { code, exploitType, language } = req.body;
    
    const exploitPrompt = `You are an ethical security researcher creating educational proof-of-concept exploits. Generate a ${exploitType} exploit for the following ${language} code.

Target code:
\`\`\`${language}
${code}
\`\`\`

IMPORTANT: This is for educational purposes and authorized testing only.

Provide your exploit in the following JSON format:
{
  "payload": "' OR 1=1 --",
  "description": "SQL injection payload that bypasses authentication by making the WHERE clause always true",
  "mitreTechnique": "T1190",
  "riskLevel": "high",
  "preventions": ["Input validation", "Parameterized queries", "WAF implementation"],
  "educational_note": "This exploit should only be used in authorized penetration testing environments"
}`;

    const exploit = await aiService.chatCompletion(
      [{ role: "user", content: exploitPrompt }],
      { jsonMode: true, temperature: 0.4 }
    );

    const parsedExploit = JSON.parse(exploit);
    
    res.json({
      id: Date.now().toString(),
      targetCode: code,
      exploitType,
      ...parsedExploit,
      createdAt: new Date().toISOString()
    });
  } catch (error) {
    console.error("Exploit generation error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Generation failed" });
  }
});

// Red Team workspace routes
app.post("/api/redteam/simulations", async (req, res) => {
  try {
    const { target, attackType, name } = req.body;
    
    const simulationPrompt = `You are a red team specialist planning an attack simulation. Create a realistic attack simulation plan for:

Target: ${target}
Attack Type: ${attackType}
Simulation Name: ${name}

Provide your simulation plan in the following JSON format:
{
  "phase": "reconnaissance",
  "progress": 25,
  "findings": [
    {
      "type": "Open Port Discovery",
      "severity": "medium",
      "description": "Multiple open ports discovered on target system",
      "mitreTechnique": "T1046"
    }
  ],
  "status": "active",
  "steps": ["Network scanning", "Service enumeration", "Vulnerability assessment"]
}

IMPORTANT: This is for authorized testing and educational purposes only.`;

    const simulation = await aiService.chatCompletion(
      [{ role: "user", content: simulationPrompt }],
      { jsonMode: true, temperature: 0.4 }
    );

    const parsedSimulation = JSON.parse(simulation);
    
    res.json({
      id: Date.now().toString(),
      name,
      target,
      attackType,
      ...parsedSimulation,
      createdAt: new Date().toISOString()
    });
  } catch (error) {
    console.error("Simulation creation error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Creation failed" });
  }
});

app.post("/api/redteam/campaigns", async (req, res) => {
  try {
    const { name, template, targets } = req.body;
    
    const campaignPrompt = `You are creating an educational phishing campaign for security awareness training.

Campaign: ${name}
Template: ${template}
Target Count: ${targets.length}

Generate a realistic phishing campaign plan in JSON format:
{
  "template": "Dear {{name}}, Your account requires immediate verification. Click here to secure your account: {{malicious_link}}",
  "targetList": ${JSON.stringify(targets.slice(0, 3))},
  "sendsCompleted": 0,
  "opensTracked": 0,
  "clicksTracked": 0,
  "credentialsHarvested": 0,
  "status": "draft",
  "educational_tips": ["Look for urgent language", "Check sender email carefully", "Verify links before clicking"],
  "detection_methods": ["Email header analysis", "Link inspection", "Domain verification"]
}

IMPORTANT: This is for authorized security awareness training only.`;

    const campaign = await aiService.chatCompletion(
      [{ role: "user", content: campaignPrompt }],
      { jsonMode: true, temperature: 0.4 }
    );

    const parsedCampaign = JSON.parse(campaign);
    
    res.json({
      id: Date.now().toString(),
      name,
      ...parsedCampaign,
      createdAt: new Date().toISOString()
    });
  } catch (error) {
    console.error("Campaign creation error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Creation failed" });
  }
});

app.post("/api/redteam/chains/generate", async (req, res) => {
  try {
    const { target, objective } = req.body;
    
    const chainPrompt = `You are a red team specialist creating a multi-step attack chain. Plan an attack chain for:

Target: ${target}
Objective: ${objective}

Create a realistic attack chain in JSON format:
{
  "steps": [
    {
      "technique": "Initial Access - Phishing",
      "mitreTactic": "TA0001",
      "description": "Send targeted phishing emails to gain initial foothold",
      "automated": false,
      "status": "pending"
    },
    {
      "technique": "Privilege Escalation",
      "mitreTactic": "TA0004", 
      "description": "Exploit local vulnerabilities to gain elevated privileges",
      "automated": true,
      "status": "pending"
    }
  ],
  "currentStep": 0,
  "overallProgress": 0,
  "riskLevel": "high",
  "timeline": "2-3 weeks for full chain execution",
  "prerequisites": ["Email delivery infrastructure", "Payload development", "C2 setup"]
}

IMPORTANT: This is for authorized testing and educational purposes only.`;

    const chain = await aiService.chatCompletion(
      [{ role: "user", content: chainPrompt }],
      { jsonMode: true, temperature: 0.4 }
    );

    const parsedChain = JSON.parse(chain);
    
    res.json({
      id: Date.now().toString(),
      name: `Attack Chain - ${target}`,
      ...parsedChain,
      createdAt: new Date().toISOString()
    });
  } catch (error) {
    console.error("Chain generation error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Generation failed" });
  }
});

// OSINT workspace routes
app.post("/api/osint/domain", async (req, res) => {
  try {
    const { domain } = req.body;
    
    const osintPrompt = `You are an OSINT specialist performing domain reconnaissance. Analyze the domain: ${domain}

Generate realistic domain intelligence in JSON format:
{
  "subdomains": ["www.${domain}", "mail.${domain}", "ftp.${domain}"],
  "ipAddresses": ["203.0.113.1", "203.0.113.2"],
  "technologies": [
    {
      "name": "nginx",
      "version": "1.18.0",
      "category": "Web Server"
    },
    {
      "name": "WordPress",
      "version": "6.0",
      "category": "CMS"
    }
  ],
  "certificates": [
    {
      "issuer": "Let's Encrypt Authority X3",
      "subject": "*.${domain}",
      "validFrom": "2024-01-01T00:00:00Z",
      "validTo": "2024-12-31T23:59:59Z"
    }
  ],
  "dnsRecords": {
    "A": ["203.0.113.1"],
    "MX": ["10 mail.${domain}"],
    "NS": ["ns1.${domain}", "ns2.${domain}"]
  },
  "socialMedia": [
    {
      "platform": "Twitter",
      "url": "https://twitter.com/${domain.split('.')[0]}",
      "verified": false
    }
  ],
  "breaches": [],
  "riskScore": 35,
  "reconnaissance_tips": ["Check for exposed admin panels", "Enumerate subdirectories", "Analyze certificate transparency logs"],
  "further_analysis": ["Subdomain brute forcing", "Technology stack fingerprinting", "Social media profiling"]
}

IMPORTANT: Only perform reconnaissance on authorized targets.`;

    const intelligence = await aiService.chatCompletion(
      [{ role: "user", content: osintPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const parsedIntel = JSON.parse(intelligence);
    
    res.json({
      domain,
      ...parsedIntel,
      lastUpdated: new Date().toISOString()
    });
  } catch (error) {
    console.error("Domain OSINT error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "OSINT failed" });
  }
});

app.post("/api/osint/github", async (req, res) => {
  try {
    const { target } = req.body;
    
    const githubPrompt = `You are an OSINT specialist analyzing GitHub organization: ${target}

Generate realistic GitHub intelligence in JSON format:
{
  "organization": "${target}",
  "repositories": [
    {
      "name": "web-app",
      "description": "Main web application repository",
      "language": "JavaScript",
      "stars": 127,
      "forks": 23,
      "isPrivate": false,
      "hasSecrets": true,
      "vulnerabilities": [
        {
          "type": "Dependency vulnerability",
          "severity": "medium",
          "description": "Outdated package with known security issues"
        }
      ]
    }
  ],
  "users": [
    {
      "username": "developer-john",
      "email": "john@${target}.com",
      "name": "John Developer",
      "location": "San Francisco, CA",
      "company": "${target}"
    }
  ],
  "sensitiveFiles": [
    {
      "repository": "web-app",
      "filename": ".env.example",
      "type": "config",
      "content": "API_KEY=example_key_here"
    }
  ],
  "totalRepos": 12,
  "riskLevel": "medium",
  "analysis_notes": ["Several repositories with potential secrets", "Active development with frequent commits"],
  "recommendations": ["Implement secret scanning", "Review public repository contents", "Enable 2FA for all users"]
}

IMPORTANT: Only analyze authorized or public repositories.`;

    const intelligence = await aiService.chatCompletion(
      [{ role: "user", content: githubPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const parsedIntel = JSON.parse(intelligence);
    
    res.json(parsedIntel);
  } catch (error) {
    console.error("GitHub OSINT error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "GitHub analysis failed" });
  }
});

app.post("/api/osint/shodan", async (req, res) => {
  try {
    const { query } = req.body;
    
    const shodanPrompt = `You are an OSINT specialist using Shodan search for: ${query}

Generate realistic Shodan search results in JSON format:
{
  "query": "${query}",
  "results": [
    {
      "ip": "198.51.100.42",
      "port": 22,
      "protocol": "tcp",
      "service": "ssh",
      "banner": "SSH-2.0-OpenSSH_7.4",
      "location": {
        "country": "United States",
        "city": "Los Angeles",
        "latitude": 34.0522,
        "longitude": -118.2437
      },
      "vulns": ["CVE-2018-15473"],
      "lastSeen": "2024-01-20T15:30:00Z"
    },
    {
      "ip": "198.51.100.43",
      "port": 80,
      "protocol": "tcp", 
      "service": "http",
      "banner": "Apache/2.4.41 (Ubuntu)",
      "location": {
        "country": "United States",
        "city": "Denver",
        "latitude": 39.7392,
        "longitude": -104.9903
      },
      "vulns": [],
      "lastSeen": "2024-01-19T12:15:00Z"
    }
  ],
  "totalResults": 2847,
  "countriesFound": ["United States", "Canada", "Germany", "United Kingdom"],
  "topServices": [
    {
      "name": "http",
      "count": 1204
    },
    {
      "name": "ssh",
      "count": 892
    }
  ],
  "vulnerabilities": [
    {
      "cve": "CVE-2018-15473",
      "count": 156,
      "severity": "medium"
    }
  ],
  "analysis_insights": ["High concentration of services in US datacenters", "Many systems running outdated software"],
  "search_tips": ["Try narrowing by geographic region", "Filter by specific service versions", "Look for exposed admin interfaces"]
}

IMPORTANT: Only search for authorized targets and educational purposes.`;

    const intelligence = await aiService.chatCompletion(
      [{ role: "user", content: shodanPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const parsedIntel = JSON.parse(intelligence);
    
    res.json(parsedIntel);
  } catch (error) {
    console.error("Shodan search error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Shodan search failed" });
  }
});

// Reports workspace routes
app.post("/api/reports/generate", async (req, res) => {
  try {
    const { title, type, template, sections } = req.body;
    
    const reportPrompt = `You are a cybersecurity analyst generating a professional ${type} security report.

Report Title: ${title}
Report Type: ${type}
Custom Sections: ${sections ? sections.join(', ') : 'Standard sections'}

Generate a comprehensive security report in JSON format:
{
  "title": "${title}",
  "type": "${type}",
  "status": "completed",
  "progress": 100,
  "findings": [
    {
      "id": "finding-001",
      "title": "Weak SSH Configuration",
      "severity": "high",
      "category": "Configuration",
      "description": "SSH service allows password authentication and root login",
      "recommendation": "Disable password authentication and root login, use key-based authentication",
      "mitreTechnique": "T1110",
      "cvss": 7.5
    },
    {
      "id": "finding-002", 
      "title": "Outdated Web Server",
      "severity": "medium",
      "category": "Patch Management",
      "description": "Web server running outdated version with known vulnerabilities",
      "recommendation": "Update to latest stable version and establish patch management process",
      "mitreTechnique": "T1190",
      "cvss": 6.1
    }
  ],
  "summary": {
    "totalFindings": 8,
    "criticalCount": 1,
    "highCount": 2,
    "mediumCount": 3,
    "lowCount": 2,
    "overallRisk": "high"
  },
  "mitreMapping": [
    {
      "tactic": "Initial Access",
      "techniques": ["T1110", "T1190", "T1078"]
    },
    {
      "tactic": "Persistence", 
      "techniques": ["T1053", "T1543"]
    }
  ],
  "recommendations": [
    "Implement multi-factor authentication across all systems",
    "Establish regular security patching schedule",
    "Deploy network segmentation and monitoring",
    "Conduct regular security awareness training",
    "Implement endpoint detection and response (EDR)"
  ],
  "executiveSummary": "This security assessment identified significant vulnerabilities that pose substantial risk to the organization. Immediate attention is required for critical and high-severity findings, particularly around access controls and patch management. The overall security posture requires improvement through implementation of the provided recommendations.",
  "technicalDetails": "The assessment utilized industry-standard penetration testing methodologies including network scanning, vulnerability assessment, and manual testing. Key findings include weak authentication mechanisms, outdated software components, and insufficient logging capabilities. Detailed remediation steps are provided for each finding.",
  "methodology": "External and internal network penetration testing following OWASP and NIST guidelines",
  "scope": "All internet-facing systems and internal network infrastructure within the 192.168.1.0/24 subnet"
}`;

    const report = await aiService.chatCompletion(
      [{ role: "user", content: reportPrompt }],
      { jsonMode: true, temperature: 0.3 }
    );

    const parsedReport = JSON.parse(report);
    
    res.json({
      id: Date.now().toString(),
      ...parsedReport,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    });
  } catch (error) {
    console.error("Report generation error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Report generation failed" });
  }
});

app.get("/api/reports/:reportId/download", async (req, res) => {
  try {
    const { reportId } = req.params;
    
    // In production, fetch report from database and generate PDF
    const samplePDF = Buffer.from("Sample PDF content - would be actual PDF in production");
    
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="security-report-${reportId}.pdf"`);
    res.send(samplePDF);
  } catch (error) {
    console.error("Report download error:", error);
    res.status(500).json({ message: error instanceof Error ? error.message : "Download failed" });
  }
});

app.get("/api/reports/templates", async (req, res) => {
  res.json([
    {
      id: "pentest-template",
      name: "Penetration Test Report", 
      type: "technical",
      description: "Comprehensive penetration testing report template",
      sections: ["Executive Summary", "Methodology", "Findings", "Recommendations"],
      customizable: true
    },
    {
      id: "compliance-template",
      name: "Compliance Assessment",
      type: "compliance", 
      description: "Regulatory compliance assessment template",
      sections: ["Compliance Status", "Gaps", "Remediation Plan"],
      customizable: true
    }
  ]);
});

app.get("/api/findings", async (req, res) => {
  res.json([
    {
      title: "Weak Password Policy",
      severity: "medium",
      category: "Authentication",
      description: "Password complexity requirements are insufficient",
      mitreTechnique: "T1110"
    },
    {
      title: "Unencrypted Data Transmission", 
      severity: "high",
      category: "Encryption",
      description: "Sensitive data transmitted without encryption",
      mitreTechnique: "T1040"
    }
  ]);
});

// Missing route stubs for data retrieval
app.get("/api/coding/analyses", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/coding/exploits", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/redteam/simulations", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/redteam/campaigns", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/redteam/chains", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/osint/domain/recent", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/osint/github/recent", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/osint/shodan/recent", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

app.get("/api/reports", async (req, res) => {
  res.json([]); // Return empty for now - in production, fetch from database
});

// Health check
app.get("/api/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

  const httpServer = createServer(app);
  return httpServer;
}
