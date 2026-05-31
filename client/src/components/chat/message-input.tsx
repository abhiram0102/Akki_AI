import { useState, useRef, useCallback, useEffect } from "react";
import { useChat } from "@/store/chat";
import { useVoice } from "@/hooks/use-voice";
import { useEmotionalState } from "@/store/emotional-state";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";

interface MessageInputProps {
  audioInitialized: boolean;
  audioContext: AudioContext | null;
}

const QUICK_PROMPTS = [
  { label: "DNS Lookup", prompt: "Perform a DNS lookup for google.com", icon: "fas fa-search" },
  { label: "Explain SQLi", prompt: "Explain SQL injection with a working example", icon: "fas fa-code" },
  { label: "Port Scan", prompt: "Scan common ports on scanme.nmap.org", icon: "fas fa-network-wired" },
  { label: "Kerberoasting", prompt: "How does Kerberoasting work in Active Directory?", icon: "fas fa-key" },
];

export default function MessageInput({ audioInitialized, audioContext }: MessageInputProps) {
  const [message, setMessage] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [showQuick, setShowQuick] = useState(false);
  const [useStream, setUseStream] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { sendMessage, isLoading, isStreaming, activeAgent } = useChat();
  const { isListening, isActive, liveTranscript, toggleListening } = useVoice(audioContext);
  const { emotionalState } = useEmotionalState();
  const { toast } = useToast();

  // Show live voice transcript in the textarea as the user speaks
  useEffect(() => {
    if (liveTranscript) setMessage(liveTranscript);
  }, [liveTranscript]);

  const isBusy = isLoading || isStreaming;

  const handleSubmit = async (e: React.FormEvent, overrideMsg?: string) => {
    e.preventDefault();
    const content = (overrideMsg || message).trim();
    if (!content || isBusy) return;

    setMessage("");
    setShowQuick(false);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    try {
      await sendMessage(content, {
        voiceInput: false,
        emotionalTone: emotionalState.currentMood,
        useStream,
      });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to send",
        variant: "destructive",
      });
    }
  };

  const handleFileUpload = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    if (file.size > 50 * 1024 * 1024) {
      toast({ title: "File too large", description: "Max 50MB", variant: "destructive" });
      return;
    }
    try {
      await api.uploadFile("/api/protected/rag/ingest", file, {
        title: file.name,
        tags: ["uploaded-via-chat"],
      });
      toast({ title: "Document uploaded", description: `${file.name} added to knowledge base` });
      await sendMessage(`I just uploaded "${file.name}". What did you learn from it?`, { useStream });
    } catch (error) {
      toast({ title: "Upload failed", description: error instanceof Error ? error.message : "Failed", variant: "destructive" });
    }
  }, [toast, sendMessage, useStream]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  };

  return (
    <div
      className={`border-t p-4 transition-colors ${isDragOver ? "border-cyan-400/50 bg-cyan-400/5" : "border-white/5"}`}
      onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setIsDragOver(false); handleFileUpload(e.dataTransfer.files); }}
    >
      {/* Drop overlay */}
      {isDragOver && (
        <div className="absolute inset-0 bg-cyan-400/10 backdrop-blur-sm flex items-center justify-center z-10 rounded-lg border-2 border-dashed border-cyan-400/50">
          <div className="text-center">
            <i className="fas fa-cloud-upload-alt text-cyan-400 text-3xl mb-2" />
            <p className="text-white text-sm font-mono">Drop file to upload to knowledge base</p>
          </div>
        </div>
      )}

      {/* Quick prompts */}
      {showQuick && (
        <div className="mb-3 grid grid-cols-2 gap-2">
          {QUICK_PROMPTS.map((qp) => (
            <button
              key={qp.label}
              onClick={(e) => { setMessage(qp.prompt); setShowQuick(false); }}
              className="flex items-center gap-2 px-3 py-2 glass-card rounded-lg border border-cyan-400/20 hover:border-cyan-400/40 text-left transition-colors group"
            >
              <i className={`${qp.icon} text-xs text-cyan-400`} />
              <span className="text-xs font-mono text-gray-300 group-hover:text-white">{qp.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Active agent status bar */}
      {activeAgent && (
        <div className="mb-2 flex items-center gap-2 text-xs font-mono text-gray-500">
          <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
          <span>Last response from</span>
          <span className="text-cyan-400">{activeAgent.agentName}</span>
          <span className="text-gray-600">·</span>
          <span>{activeAgent.agentRole}</span>
        </div>
      )}

      {/* Main input area */}
      <form onSubmit={handleSubmit}>
        <div className="glass-card rounded-xl border border-white/10 hover:border-cyan-400/20 transition-colors focus-within:border-cyan-400/30">
          {/* Text area */}
          <div className="px-4 pt-3">
            <textarea
              ref={textareaRef}
              value={message}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder={
                isListening
                  ? "🎤 Listening for voice input..."
                  : isBusy
                  ? "AKKI is responding..."
                  : "Ask anything — AKKI routes to the right agent automatically..."
              }
              className="w-full bg-transparent text-white placeholder-gray-600 border-none outline-none resize-none font-mono text-sm min-h-[36px] max-h-[160px] leading-relaxed"
              disabled={isBusy || isListening}
              data-testid="textarea-message"
              rows={1}
            />
          </div>

          {/* Actions bar */}
          <div className="flex items-center justify-between px-3 pb-3 pt-2 border-t border-white/5">
            <div className="flex items-center gap-1">
              {/* Quick prompts */}
              <button
                type="button"
                onClick={() => setShowQuick(p => !p)}
                className={`p-1.5 rounded-lg text-xs transition-colors border ${showQuick ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-400" : "border-white/10 text-gray-500 hover:text-gray-300"}`}
                title="Quick prompts"
              >
                <i className="fas fa-bolt" />
              </button>

              {/* Upload */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isBusy}
                className="p-1.5 rounded-lg text-xs border border-white/10 text-gray-500 hover:text-gray-300 transition-colors disabled:opacity-40"
                title="Upload document"
                data-testid="button-upload"
              >
                <i className="fas fa-paperclip" />
              </button>

              {/* Voice */}
              <button
                type="button"
                onClick={toggleListening}
                disabled={isBusy}
                className={`p-1.5 rounded-lg text-xs border transition-all disabled:opacity-40 ${
                  isListening
                    ? "border-green-400/50 bg-green-400/10 text-green-400 animate-pulse"
                    : isActive
                    ? "border-cyan-400/30 text-cyan-400/70 hover:text-cyan-400"
                    : "border-white/10 text-gray-500 hover:text-gray-300"
                }`}
                title={
                  isListening
                    ? "Stop listening (click to cancel)"
                    : isActive
                    ? "Voice input (ready)"
                    : "Voice input (click to activate)"
                }
                data-testid="button-voice-input"
              >
                <i className={`fas fa-microphone${isListening ? "" : "-slash"} ${isListening ? "text-green-400" : ""}`} />
              </button>

              {/* Stream toggle */}
              <button
                type="button"
                onClick={() => setUseStream(p => !p)}
                className={`p-1.5 rounded-lg text-xs border transition-colors ${
                  useStream
                    ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-400"
                    : "border-white/10 text-gray-500 hover:text-gray-300"
                }`}
                title={`Streaming: ${useStream ? "ON" : "OFF"}`}
              >
                <i className="fas fa-stream" />
              </button>
            </div>

            <div className="flex items-center gap-2">
              {/* Status text */}
              <span className="text-xs font-mono text-gray-600 hidden md:block">
                {isBusy ? (isStreaming ? "streaming..." : "thinking...") : "⏎ send · ⇧⏎ newline"}
              </span>

              {/* Send button */}
              <button
                type="submit"
                disabled={!message.trim() || isBusy}
                className="px-4 py-1.5 bg-gradient-to-r from-cyan-500 to-green-500 text-black font-bold text-xs font-mono rounded-lg hover:shadow-lg hover:shadow-cyan-500/25 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                data-testid="button-send"
              >
                {isBusy ? (
                  <><div className="w-3 h-3 border border-black/40 border-t-black rounded-full animate-spin" /> {isStreaming ? "STREAMING" : "THINKING"}</>
                ) : (
                  <><i className="fas fa-paper-plane" /> SEND</>
                )}
              </button>
            </div>
          </div>
        </div>
      </form>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.md,.txt,.log,.png,.jpg,.jpeg,.json,.csv"
        className="hidden"
        onChange={(e) => { handleFileUpload(e.target.files); e.target.value = ""; }}
      />
    </div>
  );
}
