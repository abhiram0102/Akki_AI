import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/lib/auth";
import NavigationRail from "@/components/layout/navigation-rail";
import MainContent from "@/components/layout/main-content";
import ContextPanel from "@/components/layout/context-panel";
import CommandPalette from "@/components/ui/command-palette";
import { useVoice } from "@/hooks/use-voice";

interface ClientDashboardProps {
  audioContext: AudioContext | null;
  setAudioContext: (ctx: AudioContext | null) => void;
}

function ClientOnlyDashboard({ audioContext, setAudioContext }: ClientDashboardProps) {
  const { user, isLoading } = useAuth();
  const [, setLocation] = useLocation();
  const { initializeVoice, wakeWordDetected } = useVoice(audioContext);

  useEffect(() => {
    if (!isLoading && !user) {
      setLocation("/login");
    } else if (!isLoading && user && audioContext) {
      initializeVoice();
    }
  }, [user, isLoading, audioContext, setLocation, initializeVoice]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey && e.key === "u") {
        const uploadButton = document.querySelector('[data-testid="button-upload"]') as HTMLButtonElement;
        uploadButton?.click();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleInitAudio = () => {
    const win = window as any;
    win.__audioContext = win.__audioContext || null;
    let ctx: AudioContext | null = win.__audioContext;
    if (!ctx) {
      ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      win.__audioContext = ctx;
    }
    if (ctx.state === "suspended") {
      ctx.resume?.().catch(() => {});
    }
    setAudioContext(ctx);
  };

  if (isLoading || !user) {
    return (
      <div className="min-h-screen terminal-bg flex items-center justify-center">
        <div className="glass rounded-lg p-8 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-cyber-blue to-cyber-green flex items-center justify-center animate-pulse">
            <i className="fas fa-brain text-white text-2xl" />
          </div>
          <p className="text-white font-mono font-bold tracking-wider">LOADING AKKI AI...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen terminal-bg text-white overflow-hidden" data-testid="dashboard">
      <div className="flex h-full">
        <NavigationRail />
        <MainContent onInitAudio={handleInitAudio} audioInitialized={!!audioContext} audioContext={audioContext} />
        <ContextPanel />
      </div>
      <CommandPalette />
    </div>
  );
}

export default function DashboardPage() {
  const [audioContext, setAudioContext] = useState<AudioContext | null>(null);
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  return isClient ? <ClientOnlyDashboard audioContext={audioContext} setAudioContext={setAudioContext} /> : null;
}
