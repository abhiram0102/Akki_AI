import { create } from "zustand";
import { api } from "@/lib/api";

export interface AgentInfo {
  agent: string;
  agentName: string;
  agentRole: string;
  agentColor: string;
}

export interface ToolCallResult {
  id: string;
  name: string;
  displayName: string;
  params: Record<string, any>;
  result: Record<string, any>;
  status: "success" | "error" | "running";
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt: string;
  isStreaming?: boolean;
  agentInfo?: AgentInfo;
  toolCalls?: ToolCallResult[];
  metadata?: {
    voiceInput?: boolean;
    emotionalTone?: string;
    sources?: string[];
    ragUsed?: boolean;
    confidence?: number;
  };
}

interface AgentPlan {
  goal: string;
  steps: Array<{
    id: string;
    description: string;
    status: "pending" | "executing" | "completed" | "failed" | "skipped";
    toolName?: string;
    result?: any;
  }>;
  currentStep: number;
  status: "planning" | "executing" | "completed" | "failed";
  riskAssessment: "low" | "medium" | "high";
}

interface ChatStore {
  messages: Message[];
  currentSessionId: string | null;
  currentPlan: AgentPlan | null;
  isLoading: boolean;
  isStreaming: boolean;
  activeAgent: AgentInfo | null;
  error: string | null;

  sendMessage: (content: string, options?: { voiceInput?: boolean; emotionalTone?: string; useStream?: boolean }) => Promise<void>;
  setCurrentSession: (sessionId: string) => void;
  clearChat: () => void;
  addMessage: (message: Message) => void;
  updatePlan: (plan: AgentPlan) => void;
  approveToolExecution: (toolRunId: string) => Promise<void>;
  setError: (error: string | null) => void;
  retryLastMessage: () => Promise<void>;
}

export const useChat = create<ChatStore>((set, get) => ({
  messages: [],
  currentSessionId: null,
  currentPlan: null,
  isLoading: false,
  isStreaming: false,
  activeAgent: null,
  error: null,

  sendMessage: async (content: string, options = {}) => {
    const { voiceInput = false, emotionalTone, useStream = false } = options;

    set({ isLoading: true, error: null });

    const tempUserMsgId = `temp-user-${Date.now()}`;

    // Add user message immediately
    const userMessage: Message = {
      id: tempUserMsgId,
      role: "user",
      content,
      createdAt: new Date().toISOString(),
      metadata: { voiceInput, emotionalTone }
    };
    set(state => ({ messages: [...state.messages, userMessage] }));

    if (useStream) {
      // ── STREAMING mode ────────────────────────────────────────────
      const streamMsgId = `stream-${Date.now()}`;
      const streamMsg: Message = {
        id: streamMsgId,
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
        isStreaming: true,
      };
      set(state => ({ messages: [...state.messages, streamMsg], isStreaming: true }));

      try {
        const token = localStorage.getItem("auth_token");
        const res = await fetch("/api/chat/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify({ content, sessionId: get().currentSessionId }),
        });

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let accumulated = "";
        let agentInfo: AgentInfo | null = null;

        while (reader) {
          const { done, value } = await reader.read();
          if (done) break;
          const text = decoder.decode(value, { stream: true });
          const lines = text.split("\n");
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === "agent") {
                agentInfo = {
                  agent: evt.agent,
                  agentName: evt.agentName,
                  agentRole: evt.agentRole,
                  agentColor: "cyber-blue",
                };
                set({ activeAgent: agentInfo });
                set(state => ({
                  messages: state.messages.map(m =>
                    m.id === streamMsgId ? { ...m, agentInfo: agentInfo! } : m
                  )
                }));
              } else if (evt.type === "token") {
                accumulated += evt.text;
                set(state => ({
                  messages: state.messages.map(m =>
                    m.id === streamMsgId ? { ...m, content: accumulated } : m
                  )
                }));
              } else if (evt.type === "done") {
                set(state => ({
                  messages: state.messages.map(m =>
                    m.id === streamMsgId ? { ...m, isStreaming: false } : m
                  ),
                  isStreaming: false,
                  currentSessionId: evt.sessionId ?? state.currentSessionId,
                }));
              }
            } catch { /* skip malformed lines */ }
          }
        }
      } catch (error) {
        set(state => ({
          messages: state.messages.filter(m => m.id !== streamMsgId),
          error: error instanceof Error ? error.message : "Streaming failed",
          isStreaming: false,
        }));
      }
    } else {
      // ── REGULAR mode ──────────────────────────────────────────────
      try {
        const response = await api.post("/api/protected/chat/message", {
          content,
          sessionId: get().currentSessionId,
          voiceInput,
          emotionalTone,
        });

        const data = response ?? {};
        const nextSessionId = data.sessionId ?? get().currentSessionId ?? null;
        const nextPlan = data.agentPlan ?? get().currentPlan ?? null;

        // Extract agent info from response
        const assistantMsg = data.assistantMessage;
        const agentInfo: AgentInfo | undefined = assistantMsg ? {
          agent: assistantMsg.agent || "planner",
          agentName: assistantMsg.agentName || "NEXUS",
          agentRole: assistantMsg.agentRole || "Orchestration",
          agentColor: assistantMsg.agentColor || "cyber-blue",
        } : undefined;

        if (agentInfo) set({ activeAgent: agentInfo });

        const normalized: Message[] = [];
        if (data.userMessage && data.assistantMessage) {
          normalized.push(
            { ...data.userMessage, role: "user" },
            {
              ...data.assistantMessage,
              role: "assistant",
              agentInfo,
              toolCalls: data.assistantMessage.toolCalls || [],
            }
          );
        } else if (Array.isArray(data.messages) && data.messages.length) {
          normalized.push(...data.messages);
        } else {
          normalized.push({
            id: `asst-${Date.now()}`,
            role: "assistant",
            content: "I encountered an issue. Please try again.",
            createdAt: new Date().toISOString(),
          });
        }

        set(state => ({
          messages: [
            ...state.messages.filter(m => m.id !== tempUserMsgId),
            ...normalized,
          ],
          currentSessionId: nextSessionId,
          currentPlan: nextPlan,
        }));
      } catch (error) {
        set(state => ({
          messages: state.messages.filter(m => m.id !== tempUserMsgId),
          error: error instanceof Error ? error.message : "Failed to send message",
        }));
        throw error;
      }
    }

    set({ isLoading: false });
  },

  retryLastMessage: async () => {
    const { messages } = get();
    const lastUserMessage = [...messages].reverse().find(m => m.role === "user");
    if (lastUserMessage) {
      await get().sendMessage(lastUserMessage.content, lastUserMessage.metadata);
    }
  },

  approveToolExecution: async (toolRunId: string) => {
    try {
      set({ isLoading: true, error: null });
      await api.post(`/api/protected/tools/${toolRunId}/approve`);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Failed to approve" });
      throw error;
    } finally {
      set({ isLoading: false });
    }
  },

  setCurrentSession: (sessionId: string) => {
    set({ currentSessionId: sessionId, messages: [], currentPlan: null, error: null, activeAgent: null });
  },

  clearChat: () => {
    set({ messages: [], currentSessionId: null, currentPlan: null, error: null, isLoading: false, isStreaming: false, activeAgent: null });
  },

  addMessage: (message: Message) => {
    set(state => ({ messages: [...state.messages, message] }));
  },

  updatePlan: (plan: AgentPlan) => {
    set({ currentPlan: plan });
  },

  setError: (error: string | null) => {
    set({ error });
  },
}));
