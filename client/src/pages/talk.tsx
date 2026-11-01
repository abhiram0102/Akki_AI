import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "@/lib/auth";
import { useVoice } from "@/hooks/use-voice";
import { useVoiceStore } from "@/store/voice";

interface Bubble { id: string; role: "user" | "akki"; text: string; born: number; }
type OrbState = "idle" | "wake" | "listening" | "thinking" | "speaking";

// ── Sound-wave bar animation ──────────────────────────────────────────────────
function SoundWave({ active, color = "#22d3ee" }: { active: boolean; color?: string }) {
  const bars = [3, 5, 8, 12, 8, 5, 3];
  return (
    <div className="flex items-center justify-center gap-[3px]" style={{ height: 24 }}>
      {bars.map((base, i) => (
        <div
          key={i}
          style={{
            width: 3,
            borderRadius: 2,
            backgroundColor: color,
            height: active ? `${base + Math.random() * 8}px` : "3px",
            transition: "height 0.15s ease",
            animation: active ? `waveBar 0.6s ease-in-out ${i * 0.08}s infinite alternate` : "none",
            opacity: active ? 1 : 0.3,
          }}
        />
      ))}
    </div>
  );
}

// ── Ripple ring component ─────────────────────────────────────────────────────
function RippleRings({ state }: { state: OrbState }) {
  const rings = [1, 2, 3];
  const active = state === "listening" || state === "speaking" || state === "wake";
  const color =
    state === "listening" ? "34,197,94" :
    state === "speaking"  ? "251,191,36" :
    state === "wake"      ? "52,211,153" :
                            "6,182,212";
  return (
    <>
      {rings.map(r => (
        <div
          key={r}
          className="absolute rounded-full border pointer-events-none"
          style={{
            width:  120 + r * 44,
            height: 120 + r * 44,
            left: `calc(50% - ${(120 + r * 44) / 2}px)`,
            top:  `calc(50% - ${(120 + r * 44) / 2}px)`,
            borderColor: `rgba(${color}, ${active ? 0.35 - r * 0.08 : 0.06})`,
            animation: active ? `rippleRing 2s ease-out ${r * 0.4}s infinite` : "none",
            transition: "border-color 0.5s ease",
          }}
        />
      ))}
    </>
  );
}

export default function TalkPage() {
  const { user } = useAuth();
  const [audioCtx, setAudioCtx] = useState<AudioContext | null>(null);
  const initAudio = useCallback(() => {
    if (!audioCtx) {
      try { setAudioCtx(new ((window as any).AudioContext || (window as any).webkitAudioContext)()); } catch {}
    }
  }, [audioCtx]);

  const [orbState, setOrbState]   = useState<OrbState>("idle");
  const [bubbles, setBubbles]     = useState<Bubble[]>([]);
  const [streamText, setStreamText] = useState("");
  const [liveText, setLiveText]   = useState("");   // mic transcript display
  const [isThinking, setIsThinking] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [inputText, setInputText]   = useState("");
  const [showInput, setShowInput]   = useState(false);
  const inputRef   = useRef<HTMLInputElement>(null);
  const bottomRef  = useRef<HTMLDivElement>(null);
  const speakFn    = useRef<(t: string) => Promise<void>>(() => Promise.resolve());
  const historyRef = useRef<{role:string; content:string}[]>([]);  // inline history, no DB

  // ── Send to AKKI ────────────────────────────────────────────────────────────
  const sendToAkki = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isThinking) return;

    initAudio();
    setInputText("");
    setLiveText("");
    setBubbles(prev => [...prev.slice(-8), { id: `u${Date.now()}`, role: "user", text: trimmed, born: Date.now() }]);
    setIsThinking(true);
    setStreamText("");

    // Build minimal history (last 6 turns) to send inline — no DB round-trip
    const history = historyRef.current.slice(-6);
    historyRef.current = [...history, { role: "user", content: trimmed }];

    const token = localStorage.getItem("auth_token");
    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          content: trimmed,
          agent: "planner",
          talk_mode: true,
          history,                // ← send context inline, bypass DB
        }),
      });

      const reader  = res.body?.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";
      setIsThinking(false);

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "token") { accumulated += evt.text; setStreamText(accumulated); }
          } catch {}
        }
      }

      const final = accumulated.trim();
      setStreamText("");
      if (final) {
        // Store reply in history so next turn has context (no DB)
        historyRef.current = [...historyRef.current, { role: "assistant", content: final }];
        setBubbles(prev => [...prev.slice(-8), { id: `a${Date.now()}`, role: "akki", text: final, born: Date.now() }]);
        if (useVoiceStore.getState().isActive) {
          setIsSpeaking(true);
          // await speak() — resolves when audio actually ends (ElevenLabs or browser TTS)
          speakFn.current(final).finally(() => setIsSpeaking(false));
        }
      }
    } catch {
      setIsThinking(false);
      setStreamText("");
      setBubbles(prev => [...prev, { id: `e${Date.now()}`, role: "akki", text: "Something went wrong — try again.", born: Date.now() }]);
    }
  }, [initAudio, isThinking]);

  // ── Wire voice hook with onCapture so voice goes HERE not to main chat ──────
  const { isListening, isActive, wakeWordDetected, liveTranscript,
    initializeVoice, toggleListening, speak } = useVoice(audioCtx, {
    onCapture: sendToAkki,   // ← KEY FIX: voice text routes to this page's handler
  });

  // Keep speakFn ref in sync
  useEffect(() => { speakFn.current = speak; }, [speak]);

  // Mirror live transcript
  useEffect(() => { if (liveTranscript) setLiveText(liveTranscript); }, [liveTranscript]);
  useEffect(() => { if (!isListening) setLiveText(""); }, [isListening]);

  // Orb state machine
  useEffect(() => {
    if (wakeWordDetected) { setOrbState("wake");      return; }
    if (isListening)      { setOrbState("listening"); return; }
    if (isThinking)       { setOrbState("thinking");  return; }
    if (isSpeaking)       { setOrbState("speaking");  return; }
    setOrbState("idle");
  }, [wakeWordDetected, isListening, isThinking, isSpeaking]);

  // Scroll to bottom
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [bubbles, streamText]);

  // Auto-dismiss old bubbles after 20s
  useEffect(() => {
    const timer = setInterval(() => {
      const cutoff = Date.now() - 20000;
      setBubbles(prev => prev.filter(b => b.born > cutoff));
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const ORB_GRADIENT: Record<OrbState, string> = {
    idle:      "from-cyan-700/50 via-cyan-600/30 to-teal-700/50",
    wake:      "from-emerald-400 via-green-400 to-teal-400",
    listening: "from-green-500 via-emerald-500 to-cyan-500",
    thinking:  "from-purple-600 via-violet-500 to-fuchsia-600",
    speaking:  "from-amber-400 via-orange-400 to-yellow-400",
  };
  const ORB_SHADOW: Record<OrbState, string> = {
    idle:      "rgba(6,182,212,0.15)",
    wake:      "rgba(52,211,153,0.6)",
    listening: "rgba(34,197,94,0.5)",
    thinking:  "rgba(168,85,247,0.45)",
    speaking:  "rgba(251,191,36,0.4)",
  };
  const STATUS_TEXT: Record<OrbState, string> = {
    idle:      isActive ? 'Say "Hey AKKI"' : "Tap orb to speak",
    wake:      "Wake word detected!",
    listening: "Listening...",
    thinking:  "Thinking...",
    speaking:  "Speaking...",
  };
  const STATUS_COLOR: Record<OrbState, string> = {
    idle:      "text-gray-600",
    wake:      "text-emerald-400",
    listening: "text-green-400",
    thinking:  "text-purple-400",
    speaking:  "text-amber-400",
  };
  const WAVE_COLOR: Record<OrbState, string> = {
    idle:      "#22d3ee33",
    wake:      "#34d399",
    listening: "#22c55e",
    thinking:  "#a855f7",
    speaking:  "#fbbf24",
  };
  const NEBULA_CLASS: Record<OrbState, string> = {
    idle:      "opacity-[0.05] bg-cyan-600",
    wake:      "opacity-[0.15] bg-green-400",
    listening: "opacity-[0.12] bg-green-500",
    thinking:  "opacity-[0.10] bg-purple-600",
    speaking:  "opacity-[0.09] bg-amber-500",
  };

  const userName = user?.username?.[0]?.toUpperCase() || "U";

  return (
    <>
      {/* Inject keyframe for ripple and wave bar */}
      <style>{`
        @keyframes rippleRing {
          0%   { transform: scale(0.9); opacity: 0.5; }
          100% { transform: scale(1.3); opacity: 0; }
        }
        @keyframes waveBar {
          0%   { transform: scaleY(0.4); }
          100% { transform: scaleY(1.6); }
        }
        @keyframes orbPulse {
          0%, 100% { box-shadow: 0 0 40px 8px var(--orb-shadow); }
          50%       { box-shadow: 0 0 70px 20px var(--orb-shadow); }
        }
        @keyframes wakeFlash {
          0%,100% { opacity: 1; } 30%,70% { opacity: 0.5; }
        }
        .orb-pulse { animation: orbPulse 2s ease-in-out infinite; }
        .wake-flash { animation: wakeFlash 0.4s ease-in-out 3; }
      `}</style>

      <div
        className="relative flex flex-col items-center justify-between h-full overflow-hidden bg-[#050709]"
        onClick={initAudio}
      >
        {/* ── Ambient background ─────────────────────────────────────────── */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className={`absolute top-[-20%] left-1/2 -translate-x-1/2
            w-[800px] h-[800px] rounded-full blur-[140px] transition-all duration-&lsqb;2500ms&rsqb;
            ${NEBULA_CLASS[orbState]}`} />
          <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 rounded-full blur-[100px]
            opacity-[0.04] bg-violet-600 transition-all duration-&lsqb;2000ms&rsqb;" />
          {/* Subtle grid */}
          <div className="absolute inset-0 opacity-[0.025]"
            style={{ backgroundImage: "linear-gradient(rgba(6,182,212,1) 1px,transparent 1px),linear-gradient(90deg,rgba(6,182,212,1) 1px,transparent 1px)", backgroundSize: "48px 48px" }} />
          {/* Bottom fade */}
          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[#050709] to-transparent" />
        </div>

        {/* ── Top bar ────────────────────────────────────────────────────── */}
        <div className="relative z-10 w-full flex items-center justify-between px-6 py-4 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full transition-colors duration-500
              ${orbState === "idle" ? "bg-gray-700" :
                orbState === "wake" || orbState === "listening" ? "bg-green-400 animate-pulse" :
                orbState === "thinking" ? "bg-purple-400 animate-pulse" :
                "bg-amber-400 animate-pulse"}`} />
            <span className="text-[11px] font-mono text-gray-600 tracking-[0.2em] uppercase">AKKI · Talk</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={initializeVoice}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-mono border transition-all duration-300
                ${isActive
                  ? "border-green-500/40 bg-green-500/10 text-green-400"
                  : "border-white/10 bg-white/5 text-gray-500 hover:border-cyan-400/30 hover:text-cyan-400"}`}
            >
              <i className={`fas fa-microphone text-[9px] ${isActive ? "text-green-400" : ""}`} />
              {isActive ? "Voice ON" : "Enable Voice"}
            </button>
            <button
              onClick={() => { setShowInput(p => !p); setTimeout(() => inputRef.current?.focus(), 80); }}
              className={`w-7 h-7 rounded-full border flex items-center justify-center transition-all
                ${showInput ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-400" : "border-white/10 text-gray-600 hover:text-gray-400"}`}
            >
              <i className="fas fa-keyboard text-[9px]" />
            </button>
          </div>
        </div>

        {/* ── Bubbles ─────────────────────────────────────────────────────── */}
        <div className="relative z-10 w-full max-w-xl flex-1 flex flex-col justify-end px-5 pb-2 overflow-hidden gap-2 min-h-0">
          {bubbles.map(b => (
            <div key={b.id}
              className={`flex gap-2 items-end transition-all duration-500
                ${b.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
              {/* Avatar */}
              <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold
                ${b.role === "akki"
                  ? "bg-gradient-to-br from-cyan-500 to-teal-500 text-black"
                  : "bg-gradient-to-br from-violet-500 to-pink-500 text-white"}`}>
                {b.role === "akki" ? <i className="fas fa-brain text-[8px]" /> : userName}
              </div>
              {/* Bubble */}
              <div className={`max-w-[78%] text-sm px-4 py-2.5 rounded-2xl leading-relaxed backdrop-blur-sm
                ${b.role === "user"
                  ? "bg-cyan-500/10 border border-cyan-400/15 text-gray-200 rounded-br-sm"
                  : "bg-white/5 border border-white/8 text-gray-100 rounded-bl-sm"}`}>
                {b.text}
              </div>
            </div>
          ))}

          {/* Streaming */}
          {streamText && (
            <div className="flex gap-2 items-end">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gradient-to-br from-cyan-500 to-teal-500 flex items-center justify-center">
                <i className="fas fa-brain text-[8px] text-black" />
              </div>
              <div className="max-w-[78%] bg-white/5 border border-white/8 rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm text-gray-100">
                {streamText}
                <span className="inline-block w-0.5 h-4 bg-cyan-400 ml-0.5 animate-pulse align-middle" />
              </div>
            </div>
          )}

          {/* Live mic transcript */}
          {liveText && isListening && (
            <div className="flex gap-2 items-end flex-row-reverse">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gradient-to-br from-violet-500 to-pink-500 flex items-center justify-center text-[10px] font-bold text-white">
                {userName}
              </div>
              <div className="max-w-[78%] bg-green-500/10 border border-green-400/20 rounded-2xl rounded-br-sm px-4 py-2.5 text-sm text-green-300">
                {liveText}
                <span className="inline-block w-0.5 h-4 bg-green-400 ml-0.5 animate-pulse align-middle" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* ── Central orb ─────────────────────────────────────────────────── */}
        <div className="relative z-10 flex flex-col items-center gap-5 py-6 flex-shrink-0">
          {/* Ripple rings behind orb */}
          <div className="relative flex items-center justify-center" style={{ width: 240, height: 240 }}>
            <RippleRings state={orbState} />

            {/* The orb */}
            <button
              onClick={() => { initAudio(); isActive ? toggleListening() : initializeVoice(); }}
              className={`relative w-32 h-32 rounded-full bg-gradient-to-br ${ORB_GRADIENT[orbState]}
                flex items-center justify-center cursor-pointer select-none
                transition-all duration-700 orb-pulse hover:scale-105 active:scale-95
                ${orbState === "wake" ? "wake-flash" : ""}`}
              style={{ "--orb-shadow": ORB_SHADOW[orbState] } as React.CSSProperties}
            >
              {/* Glass inner */}
              <div className="absolute inset-3 rounded-full bg-white/10 backdrop-blur-md" />
              {/* Icon */}
              <div className="relative z-10 flex flex-col items-center gap-1.5">
                <i className={`fas text-2xl text-white/90 transition-all duration-400
                  ${orbState === "thinking"  ? "fa-circle-notch fa-spin" :
                    orbState === "speaking"  ? "fa-volume-up" :
                    orbState === "wake"      ? "fa-bolt" :
                    orbState === "listening" ? "fa-microphone" :
                                               isActive ? "fa-microphone" : "fa-microphone-slash"}`} />
                {/* Wave bars inside orb */}
                <SoundWave
                  active={orbState === "listening" || orbState === "speaking"}
                  color={orbState === "speaking" ? "#fbbf24" : "#ffffff"}
                />
              </div>
            </button>
          </div>

          {/* Status */}
          <div className="flex flex-col items-center gap-1.5">
            <p className={`text-sm font-mono font-medium tracking-wider transition-all duration-500 ${STATUS_COLOR[orbState]}`}>
              {STATUS_TEXT[orbState]}
            </p>
            {/* Wave bars below orb when active */}
            {(orbState === "listening" || orbState === "speaking") && (
              <div className="flex items-end gap-[3px] h-5">
                {[4,7,12,9,14,9,12,7,4].map((h, i) => (
                  <div
                    key={i}
                    className={`w-[3px] rounded-full transition-all
                      ${orbState === "listening" ? "bg-green-400" : "bg-amber-400"}`}
                    style={{
                      height: h,
                      animation: `waveBar 0.5s ease-in-out ${i * 0.07}s infinite alternate`,
                    }}
                  />
                ))}
              </div>
            )}
            {orbState === "thinking" && (
              <div className="flex gap-1.5">
                {[0,1,2].map(i => (
                  <div key={i} className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce"
                    style={{ animationDelay: `${i * 0.18}s` }} />
                ))}
              </div>
            )}
            {isActive && orbState === "idle" && (
              <div className="flex items-center gap-2 text-[10px] font-mono text-gray-700 mt-0.5">
                <span className="w-1 h-1 rounded-full bg-green-500 animate-pulse" />
                Listening for wake word
              </div>
            )}
          </div>
        </div>

        {/* ── Text input ──────────────────────────────────────────────────── */}
        <div className={`relative z-10 w-full max-w-xl px-5 pb-6 transition-all duration-400 flex-shrink-0
          ${showInput ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3 pointer-events-none"}`}>
          <div className={`flex items-center gap-3 px-5 py-3 rounded-full backdrop-blur-sm
            border transition-all duration-300
            ${isListening ? "border-green-400/40 bg-green-500/5" : "border-white/10 bg-white/5 focus-within:border-cyan-400/30"}`}>
            <input
              ref={inputRef}
              type="text"
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && inputText.trim()) { sendToAkki(inputText); setShowInput(false); }}}
              disabled={isThinking}
              placeholder="Type to AKKI..."
              className="flex-1 bg-transparent text-white placeholder-gray-700 outline-none text-sm"
            />
            <button
              onClick={() => { if (inputText.trim()) { sendToAkki(inputText); setShowInput(false); }}}
              disabled={!inputText.trim() || isThinking}
              className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center transition-all
                ${inputText.trim() && !isThinking
                  ? "bg-gradient-to-br from-cyan-500 to-teal-500 text-black"
                  : "bg-white/5 text-gray-700 cursor-not-allowed"}`}
            >
              <i className={`fas text-xs ${isThinking ? "fa-circle-notch fa-spin" : "fa-arrow-up"}`} />
            </button>
          </div>
          <p className="text-center text-[10px] text-gray-700 font-mono mt-2">
            Enter to send · Say <span className="text-cyan-700">"Hey AKKI"</span> hands-free
          </p>
        </div>

        {/* ── Bottom controls ──────────────────────────────────────────────── */}
        {!showInput && (
          <div className="relative z-10 pb-6 flex-shrink-0 flex flex-col items-center gap-2">
            {!isActive ? (
              <button onClick={initializeVoice}
                className="text-xs font-mono text-gray-600 hover:text-cyan-500 transition-colors underline underline-offset-2">
                Enable voice to speak hands-free
              </button>
            ) : (
              <p className="text-[11px] font-mono text-gray-700">
                Tap orb to speak · <span className="text-cyan-800">"Hey AKKI"</span> for hands-free
              </p>
            )}
            {/* ElevenLabs test button */}
            <button
              onClick={async () => {
                const token = localStorage.getItem("auth_token");
                try {
                  const resp = await fetch("/api/voice/test", {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                  });

                  const ct = resp.headers.get("content-type") || "";
                  if (ct.includes("audio")) {
                    // Test endpoint returned real audio — play it directly
                    const ab = await resp.arrayBuffer();
                    const blob = new Blob([ab], { type: "audio/mpeg" });
                    const url = URL.createObjectURL(blob);
                    const audio = new Audio(url);
                    audio.onended = () => URL.revokeObjectURL(url);
                    audio.onerror = () => { URL.revokeObjectURL(url); alert("Audio decode error — check browser console"); };
                    await audio.play();
                  } else {
                    const data = await resp.json() as { status: string; message?: string; code?: number };
                    alert(`ElevenLabs error:\n\nStatus: ${data.status}\nCode: ${data.code ?? "n/a"}\nMessage: ${data.message ?? "No message"}`);
                  }
                } catch (err) {
                  alert("Request failed: " + String(err));
                }
              }}
              style={{
                fontSize: 10, fontFamily: "monospace",
                color: "rgba(0,216,255,0.35)",
                background: "none", border: "1px solid rgba(0,216,255,0.15)",
                borderRadius: 999, padding: "3px 12px", cursor: "pointer",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "#00d8ff"; (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,216,255,0.40)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "rgba(0,216,255,0.35)"; (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,216,255,0.15)"; }}
            >
              <i className="fas fa-volume-up" style={{ marginRight: 5 }} />
              Test ElevenLabs Voice
            </button>
          </div>
        )}
      </div>
    </>
  );
}
