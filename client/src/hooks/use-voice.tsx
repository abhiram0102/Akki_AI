import { useState, useEffect, useCallback, useRef } from "react";
import { useVoiceStore } from "@/store/voice";
import { useChat } from "@/store/chat";
import { useToast } from "@/hooks/use-toast";

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

// ─── Singleton state (survives re-renders) ────────────────────────────────────
function getG() {
  if (!(window as any).__voiceG) {
    (window as any).__voiceG = {
      wakeRecog: null as any,        // SpeechRecognition for wake-word loop
      cmdRecog: null as any,         // SpeechRecognition for command capture
      wakeActive: false,             // is wake-word loop currently running?
      permissionGranted: false,      // has the user granted mic permission?
      supported: !!(
        window.SpeechRecognition || window.webkitSpeechRecognition
      ),
    };
  }
  return (window as any).__voiceG as {
    wakeRecog: any;
    cmdRecog: any;
    wakeActive: boolean;
    permissionGranted: boolean;
    supported: boolean;
  };
}

export function useVoice(audioContext: AudioContext | null) {
  const {
    isListening,
    isActive,
    setListening,
    setActive,
    wakeWordDetected,
    setWakeWordDetected,
    setAudioLevel,
    setLastTranscription,
  } = useVoiceStore();

  const { sendMessage } = useChat();
  const { toast } = useToast();

  // Live transcript state so callers can show it in the input
  const [liveTranscript, setLiveTranscript] = useState("");
  const isListeningRef = useRef(isListening);
  useEffect(() => { isListeningRef.current = isListening; }, [isListening]);

  // ── Helpers ──────────────────────────────────────────────────────────────

  const SpeechRecognitionAPI = useCallback(() =>
    window.SpeechRecognition || window.webkitSpeechRecognition, []);

  /** Stop wake-word loop gracefully */
  const stopWakeLoop = useCallback(() => {
    const g = getG();
    if (g.wakeRecog) {
      try { g.wakeRecog.abort(); } catch {}
      g.wakeActive = false;
    }
  }, []);

  /** Start (or restart) the low-priority wake-word loop */
  const startWakeLoop = useCallback(() => {
    const g = getG();
    if (!g.supported || !g.permissionGranted) return;
    if (g.wakeActive) return;

    const API = SpeechRecognitionAPI();
    if (!API) return;

    if (!g.wakeRecog) {
      g.wakeRecog = new API();
      g.wakeRecog.continuous = true;
      g.wakeRecog.interimResults = false;
      g.wakeRecog.lang = "en-US";
    }

    const rec = g.wakeRecog;
    rec.onresult = (event: any) => {
      const text = Array.from(event.results as any[])
        .slice(event.resultIndex)
        .map((r: any) => r[0].transcript)
        .join(" ")
        .toLowerCase();

      const WAKE_WORDS = ["hey akki", "hey ammu", "akki", "ammu", "hello akki"];
      if (WAKE_WORDS.some((w) => text.includes(w))) {
        setWakeWordDetected(true);
        setTimeout(() => setWakeWordDetected(false), 3000);
        // auto-start command capture
        stopWakeLoop();
        setTimeout(() => startCommandCapture(), 300);
      }
    };

    rec.onerror = (e: any) => {
      if (e.error === "not-allowed") {
        g.permissionGranted = false;
        setActive(false);
      }
      g.wakeActive = false;
    };

    rec.onend = () => {
      g.wakeActive = false;
      // restart unless we're in command mode or listening
      if (!isListeningRef.current && g.permissionGranted) {
        setTimeout(() => startWakeLoop(), 1500);
      }
    };

    try {
      rec.start();
      g.wakeActive = true;
    } catch {}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [SpeechRecognitionAPI, setActive, setWakeWordDetected, stopWakeLoop]);

  // ── Command capture ───────────────────────────────────────────────────────

  const startCommandCapture = useCallback(() => {
    const g = getG();
    const API = SpeechRecognitionAPI();
    if (!API) return;

    stopWakeLoop();

    const rec: any = new API();
    g.cmdRecog = rec;
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.maxAlternatives = 1;

    setListening(true);
    setLiveTranscript("");
    let finalText = "";

    rec.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += (finalText ? " " : "") + t.trim();
        } else {
          interim = t;
        }
      }
      setLiveTranscript(finalText || interim);
      setLastTranscription(finalText || interim);
    };

    rec.onerror = (e: any) => {
      console.warn("[Voice] command recognition error:", e.error);
      setListening(false);
      setLiveTranscript("");
      if (e.error !== "no-speech" && e.error !== "aborted") {
        toast({
          title: "Voice error",
          description: `Speech recognition error: ${e.error}`,
          variant: "destructive",
        });
      }
      setTimeout(() => startWakeLoop(), 800);
    };

    rec.onend = async () => {
      setListening(false);
      const text = finalText.trim();
      setLiveTranscript("");

      if (text) {
        setLastTranscription(text);
        try {
          await sendMessage(text, { voiceInput: true });
        } catch (err) {
          toast({
            title: "Failed to send voice message",
            description: String(err),
            variant: "destructive",
          });
        }
      } else {
        toast({
          title: "No speech detected",
          description: "Please try again and speak clearly.",
          variant: "default",
        });
      }
      setTimeout(() => startWakeLoop(), 800);
    };

    try {
      rec.start();
    } catch (err) {
      console.error("[Voice] failed to start command recognition:", err);
      setListening(false);
      setTimeout(() => startWakeLoop(), 800);
    }
  }, [SpeechRecognitionAPI, sendMessage, setLastTranscription, setListening, startWakeLoop, stopWakeLoop, toast]);

  // ── Public API ────────────────────────────────────────────────────────────

  /** Call once (e.g. on first mic-button click) to request permission & activate */
  const initializeVoice = useCallback(async () => {
    const g = getG();

    if (!g.supported) {
      toast({
        title: "Voice not supported",
        description: "Your browser doesn't support speech recognition. Try Chrome or Edge.",
        variant: "destructive",
      });
      return;
    }

    if (g.permissionGranted) {
      // already ready — just start wake loop
      setActive(true);
      startWakeLoop();
      return;
    }

    try {
      // Trigger mic permission prompt
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Stop tracks immediately — we only needed the permission prompt
      stream.getTracks().forEach((t) => t.stop());
      g.permissionGranted = true;
      setActive(true);
      startWakeLoop();
      toast({
        title: "Voice activated",
        description: 'Say "Hey AKKI" or click 🎤 to speak',
      });
    } catch (err: any) {
      const denied = err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError";
      toast({
        title: denied ? "Microphone access denied" : "Microphone unavailable",
        description: denied
          ? "Please allow microphone access in your browser settings."
          : "Could not access your microphone. Check that it's connected.",
        variant: "destructive",
      });
      setActive(false);
    }
  }, [setActive, startWakeLoop, toast]);

  const stopListening = useCallback(() => {
    const g = getG();
    if (g.cmdRecog) {
      try { g.cmdRecog.stop(); } catch {}
    }
    setListening(false);
    setLiveTranscript("");
    setAudioLevel(0);
  }, [setAudioLevel, setListening]);

  const toggleListening = useCallback(async () => {
    const g = getG();

    if (isListening) {
      stopListening();
      return;
    }

    if (!g.supported) {
      toast({
        title: "Voice not supported",
        description: "Your browser doesn't support speech recognition.",
        variant: "destructive",
      });
      return;
    }

    if (!g.permissionGranted) {
      // Initialize on first click
      await initializeVoice();
      // After permission granted, start command capture
      if (getG().permissionGranted) {
        setTimeout(() => startCommandCapture(), 200);
      }
      return;
    }

    startCommandCapture();
  }, [initializeVoice, isListening, startCommandCapture, stopListening, toast]);

  // Auto-initialize if previously active (persisted in store)
  useEffect(() => {
    const g = getG();
    if (isActive && !g.permissionGranted && g.supported) {
      // We were active before — try to re-init silently
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((s) => {
          s.getTracks().forEach((t) => t.stop());
          g.permissionGranted = true;
          startWakeLoop();
        })
        .catch(() => {
          // Permission revoked — reset active state
          setActive(false);
        });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // only on mount

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopWakeLoop();
      const g = getG();
      if (g.cmdRecog) {
        try { g.cmdRecog.abort(); } catch {}
      }
    };
  }, [stopWakeLoop]);

  return {
    isListening,
    isActive: getG().supported, // always show button if browser supports it
    wakeWordDetected,
    liveTranscript,
    initializeVoice,
    startListening: startCommandCapture,
    stopListening,
    toggleListening,
    audioLevel: useVoiceStore.getState().audioLevel,
    lastTranscription: useVoiceStore.getState().lastTranscription,
  };
}
