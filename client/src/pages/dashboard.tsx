import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/lib/auth";
import NavigationRail from "@/components/layout/navigation-rail";
import MainContent from "@/components/layout/main-content";
import ContextPanel from "@/components/layout/context-panel";
import CommandPalette from "@/components/ui/command-palette";
import { MotionDemo } from "@/components/ui/motion-demo";
import { motion } from "framer-motion";
import { motionPresets } from "@/motion";
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
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="min-h-screen terminal-bg flex items-center justify-center"
      >
        <motion.div
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="glass rounded-lg p-8 text-center space-y-6"
        >
          <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-cyber-blue to-cyber-green flex items-center justify-center">
            <motion.div
              variants={motionPresets.pulse}
              initial="initial"
              animate="animate"
              className="w-12 h-12 bg-cyan-400/20 rounded-full flex items-center justify-center border border-cyan-400/30"
            >
              <i className="fas fa-brain text-white text-xl" />
            </motion.div>
          </div>
          <motion.h1
            variants={motionPresets.fadeInUp}
            initial="initial"
            animate="animate"
            className="text-white font-mono font-bold tracking-wider text-2xl"
          >
            LOADING AKKI AI...
          </motion.h1>
          <motion.p
            variants={motionPresets.fadeInUp}
            initial="initial"
            animate="animate"
            className="text-gray-300 text-sm"
          >
            Initializing neural pathways...
          </motion.p>
          <MotionDemo className="max-w-md mx-auto mt-6" />
        </motion.div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="h-screen terminal-bg text-white overflow-hidden" data-testid="dashboard"
    >
      <div className="flex h-full">
        <NavigationRail />
        <MainContent onInitAudio={handleInitAudio} audioInitialized={!!audioContext} audioContext={audioContext} />
        <ContextPanel />
      </div>
      <CommandPalette />
    </motion.div>
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