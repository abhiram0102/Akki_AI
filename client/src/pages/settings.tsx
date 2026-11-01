import { useState, useCallback } from "react";
import type { CSSProperties, ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { useVoiceStore } from "@/store/voice";
import { useChat } from "@/store/chat";
import { useToast } from "@/hooks/use-toast";
import { useVoice } from "@/hooks/use-voice";
import { api } from "@/lib/api";
import { useTheme } from "@/theme/ThemeProvider";

// ─── ElevenLabs preset voices ─────────────────────────────────────────────────
const ELEVENLABS_VOICES = [
  { label: "Adam",   id: "pNInz6obpgDQGcFmaJgB" },
  { label: "Rachel", id: "21m00Tcm4TlvDq8ikWAM" },
  { label: "Josh",   id: "TxGEqnHWrfWFTfGW9XjX" },
  { label: "Antoni", id: "ErXwobaYiN019PkySvjV"  },
  { label: "Bella",  id: "EXAVITQu4vr4xnSDxMaL"  },
];

// ─── Shared style primitives ───────────────────────────────────────────────────
const PANEL: CSSProperties = {
  background: "rgba(8,13,26,0.95)",
  border: "1px solid rgba(0,216,255,0.15)",
  borderRadius: 14,
  padding: "20px 24px",
  marginBottom: 16,
};

const SECTION_HEADER: CSSProperties = {
  fontFamily: "monospace",
  fontSize: 11,
  fontWeight: 700,
  color: "rgba(255,255,255,0.60)",
  textTransform: "uppercase",
  letterSpacing: "0.12em",
  marginBottom: 16,
  margin: 0,
};

const LABEL: CSSProperties = {
  fontFamily: "monospace",
  fontSize: 12,
  color: "rgba(255,255,255,0.55)",
  marginBottom: 6,
  display: "block",
};

const INPUT: CSSProperties = {
  width: "100%",
  padding: "9px 12px",
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(0,216,255,0.18)",
  borderRadius: 8,
  color: "#e2e8f0",
  fontFamily: "monospace",
  fontSize: 13,
  outline: "none",
  boxSizing: "border-box",
};

const SELECT_STYLE: CSSProperties = {
  ...INPUT,
  appearance: "none" as const,
  cursor: "pointer",
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2300d8ff' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  paddingRight: 32,
};

const BTN_PRIMARY: CSSProperties = {
  background: "linear-gradient(135deg,#00d8ff,#00ff88)",
  color: "#04080f",
  border: "none",
  borderRadius: 8,
  padding: "9px 20px",
  fontFamily: "monospace",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
  letterSpacing: "0.05em",
};

const BTN_DANGER: CSSProperties = {
  background: "rgba(255,59,59,0.15)",
  color: "#ff6b6b",
  border: "1px solid rgba(255,59,59,0.35)",
  borderRadius: 8,
  padding: "9px 20px",
  fontFamily: "monospace",
  fontSize: 12,
  fontWeight: 700,
  cursor: "pointer",
  letterSpacing: "0.05em",
};

const BTN_GHOST: CSSProperties = {
  background: "rgba(255,255,255,0.06)",
  color: "rgba(255,255,255,0.75)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 8,
  padding: "9px 20px",
  fontFamily: "monospace",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  letterSpacing: "0.05em",
};

const TOGGLE_TRACK = (on: boolean): CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  width: 44,
  height: 24,
  borderRadius: 12,
  background: on ? "linear-gradient(135deg,#00d8ff,#00ff88)" : "rgba(255,255,255,0.12)",
  border: "none",
  cursor: "pointer",
  padding: 2,
  transition: "background 0.2s",
  flexShrink: 0,
});

const TOGGLE_THUMB = (on: boolean): CSSProperties => ({
  width: 20,
  height: 20,
  borderRadius: "50%",
  background: on ? "#04080f" : "rgba(255,255,255,0.55)",
  transform: on ? "translateX(20px)" : "translateX(0)",
  transition: "transform 0.2s",
});

const NOTE: CSSProperties = {
  fontFamily: "monospace",
  fontSize: 11,
  color: "rgba(255,216,0,0.65)",
  marginTop: 5,
};

const ROW: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  marginBottom: 14,
};

const SLIDER_STYLE: CSSProperties = {
  flex: 1,
  appearance: "none" as const,
  height: 4,
  borderRadius: 2,
  background: "rgba(0,216,255,0.18)",
  outline: "none",
  cursor: "pointer",
};

// ─── Radio group ───────────────────────────────────────────────────────────────
function RadioGroup({
  options,
  value,
  onChange,
}: {
  options: { label: string; value: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" as const }}>
      {options.map((opt) => {
        const selected = opt.value === value;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            style={{
              padding: "7px 16px",
              borderRadius: 8,
              fontFamily: "monospace",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              border: selected
                ? "1px solid rgba(0,216,255,0.7)"
                : "1px solid rgba(255,255,255,0.12)",
              background: selected
                ? "rgba(0,216,255,0.12)"
                : "rgba(255,255,255,0.04)",
              color: selected ? "#00d8ff" : "rgba(255,255,255,0.6)",
              transition: "all 0.15s",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

// ─── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={PANEL}>
      <p style={SECTION_HEADER}>{title}</p>
      <div style={{ marginTop: 16 }}>{children}</div>
    </div>
  );
}

// ─── Field wrapper ─────────────────────────────────────────────────────────────
function Field({ label, note, children }: { label: string; note?: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={LABEL}>{label}</label>
      {children}
      {note && <p style={NOTE}>{note}</p>}
    </div>
  );
}

// ─── Settings page ─────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const { user } = useAuth();
  const { voiceSettings, updateVoiceSettings } = useVoiceStore();
  const { clearChat } = useChat();
  const { toast } = useToast();
  const { theme, toggleTheme } = useTheme();

  // useVoice for speak — audioContext not needed for TTS
  const { speak } = useVoice(null);

  // ── Section 1: AI Config ─────────────────────────────────────────────────────
  const [geminiKey, setGeminiKey] = useState<string>(
    () => (typeof window !== "undefined" ? localStorage.getItem("gemini_api_key_display") ?? "" : "")
  );
  const [elevenKey, setElevenKey] = useState<string>(
    () => (typeof window !== "undefined" ? localStorage.getItem("elevenlabs_api_key_display") ?? "" : "")
  );
  const [embeddingProvider, setEmbeddingProvider] = useState<string>("gemini");

  const saveGeminiKey = () => {
    if (typeof window !== "undefined") localStorage.setItem("gemini_api_key_display", geminiKey);
    toast({ title: "Saved", description: "Gemini key stored locally for display. Update backend .env for actual use." });
  };

  const saveElevenKey = () => {
    if (typeof window !== "undefined") localStorage.setItem("elevenlabs_api_key_display", elevenKey);
    toast({ title: "Saved", description: "ElevenLabs key stored locally for display. Update backend .env for actual use." });
  };

  // ── Section 2: Voice Settings ─────────────────────────────────────────────────
  const [testingVoice, setTestingVoice] = useState(false);

  const handleTestVoice = useCallback(async () => {
    setTestingVoice(true);
    try {
      await speak("Hello! Voice settings are configured correctly.");
    } catch {
      toast({ title: "Voice test failed", description: "Could not play audio.", variant: "destructive" });
    } finally {
      setTestingVoice(false);
    }
  }, [speak, toast]);

  // ── Section 3: Display Settings ───────────────────────────────────────────────
  const [fontSize, setFontSize] = useState<string>(() =>
    typeof window !== "undefined" ? localStorage.getItem("ui_font_size") ?? "medium" : "medium"
  );

  const saveFontSize = (size: string) => {
    setFontSize(size);
    if (typeof window !== "undefined") localStorage.setItem("ui_font_size", size);
    toast({ title: "Font size updated" });
  };

  // ── Section 4: Account ────────────────────────────────────────────────────────
  const [pwCurrent, setPwCurrent] = useState("");
  const [pwNew, setPwNew]         = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [savingPw, setSavingPw]   = useState(false);

  const handleChangePassword = async () => {
    if (!pwNew || pwNew !== pwConfirm) {
      toast({ title: "Password mismatch", description: "New passwords do not match.", variant: "destructive" });
      return;
    }
    if (pwNew.length < 8) {
      toast({ title: "Too short", description: "Password must be at least 8 characters.", variant: "destructive" });
      return;
    }
    setSavingPw(true);
    try {
      await api.put("/api/protected/profile", {
        currentPassword: pwCurrent,
        newPassword: pwNew,
      });
      setPwCurrent(""); setPwNew(""); setPwConfirm("");
      toast({ title: "Password updated", description: "Your password has been changed successfully." });
    } catch (err: unknown) {
      toast({
        title: "Update failed",
        description: err instanceof Error ? err.message : "Could not update password.",
        variant: "destructive",
      });
    } finally {
      setSavingPw(false);
    }
  };

  // ── Section 5: Data & Privacy ─────────────────────────────────────────────────
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleClearHistory = () => {
    clearChat();
    toast({ title: "History cleared", description: "All conversation messages have been removed." });
  };

  const handleExportData = () => {
    const data = {
      user: { username: user?.username, email: user?.email, createdAt: user?.createdAt },
      voiceSettings,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `akki-data-export-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: "Data exported", description: "Your data has been downloaded as JSON." });
  };

  const handleDeleteAccount = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    try {
      await api.delete("/api/protected/profile");
      toast({ title: "Account deleted", description: "Your account has been removed." });
    } catch (err: unknown) {
      toast({
        title: "Delete failed",
        description: err instanceof Error ? err.message : "Could not delete account.",
        variant: "destructive",
      });
    }
    setConfirmDelete(false);
  };

  // ── Formatted creation date ───────────────────────────────────────────────────
  const createdAt = user?.createdAt
    ? new Date(user.createdAt).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "—";

  // ─────────────────────────────────────────────────────────────────────────────
  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        overflowY: "auto",
        background: "linear-gradient(135deg,#020812 0%,#040d1a 50%,#020c18 100%)",
        color: "#e2e8f0",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      {/* ── Page header ── */}
      <div
        style={{
          padding: "28px 32px 20px",
          borderBottom: "1px solid rgba(0,216,255,0.1)",
          background: "rgba(8,13,26,0.7)",
          backdropFilter: "blur(8px)",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <h1
          style={{
            margin: 0,
            fontFamily: "monospace",
            fontSize: 20,
            fontWeight: 700,
            color: "#fff",
            letterSpacing: "0.04em",
          }}
        >
          <span style={{ color: "#00d8ff" }}>⚙</span>&nbsp;Settings
        </h1>
        <p style={{ margin: "4px 0 0", fontFamily: "monospace", fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
          Manage your AI assistant preferences
        </p>
      </div>

      {/* ── Content ── */}
      <div style={{ maxWidth: 680, margin: "0 auto", padding: "24px 24px 60px" }}>

        {/* ─── Section 1: AI Configuration ─────────────────────────────────────── */}
        <Section title="AI Configuration">

          <Field
            label="Gemini API Key"
            note="Stored locally for display only — set GEMINI_API_KEY in your backend .env for actual use."
          >
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIza…"
                style={{ ...INPUT, flex: 1 }}
              />
              <button onClick={saveGeminiKey} style={BTN_PRIMARY}>Save</button>
            </div>
          </Field>

          <Field
            label="ElevenLabs API Key"
            note="Stored locally for display only — set ELEVENLABS_API_KEY in your backend .env for actual use."
          >
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="password"
                value={elevenKey}
                onChange={(e) => setElevenKey(e.target.value)}
                placeholder="sk_…"
                style={{ ...INPUT, flex: 1 }}
              />
              <button onClick={saveElevenKey} style={BTN_PRIMARY}>Save</button>
            </div>
          </Field>

          <Field label="Voice ID">
            <select
              value={voiceSettings.elevenlabsVoiceId}
              onChange={(e) => updateVoiceSettings({ elevenlabsVoiceId: e.target.value })}
              style={SELECT_STYLE}
            >
              {ELEVENLABS_VOICES.map((v) => (
                <option key={v.id} value={v.id}>{v.label}</option>
              ))}
            </select>
          </Field>

          <Field label="Embedding Provider">
            <RadioGroup
              options={[
                { label: "Gemini", value: "gemini" },
                { label: "Ollama", value: "ollama" },
                { label: "None",   value: "none"   },
              ]}
              value={embeddingProvider}
              onChange={setEmbeddingProvider}
            />
          </Field>

        </Section>

        {/* ─── Section 2: Voice Settings ───────────────────────────────────────── */}
        <Section title="Voice Settings">

          <Field label={`Voice Speed — ${voiceSettings.voiceSpeed.toFixed(2)}x`}>
            <input
              type="range"
              min={0.5}
              max={1.5}
              step={0.05}
              value={voiceSettings.voiceSpeed}
              onChange={(e) => updateVoiceSettings({ voiceSpeed: parseFloat(e.target.value) })}
              style={SLIDER_STYLE}
            />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <span style={LABEL}>0.5×</span>
              <span style={LABEL}>1.5×</span>
            </div>
          </Field>

          <Field label={`Voice Pitch — ${voiceSettings.voicePitch.toFixed(2)}`}>
            <input
              type="range"
              min={0.5}
              max={1.5}
              step={0.05}
              value={voiceSettings.voicePitch}
              onChange={(e) => updateVoiceSettings({ voicePitch: parseFloat(e.target.value) })}
              style={SLIDER_STYLE}
            />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <span style={LABEL}>0.5</span>
              <span style={LABEL}>1.5</span>
            </div>
          </Field>

          <div style={{ ...ROW, justifyContent: "space-between", marginBottom: 20 }}>
            <span style={{ fontFamily: "monospace", fontSize: 13, color: "rgba(255,255,255,0.75)" }}>
              Enable ElevenLabs TTS
            </span>
            <button
              onClick={() => updateVoiceSettings({ useElevenlabs: !voiceSettings.useElevenlabs })}
              style={TOGGLE_TRACK(voiceSettings.useElevenlabs)}
            >
              <div style={TOGGLE_THUMB(voiceSettings.useElevenlabs)} />
            </button>
          </div>

          <button
            onClick={handleTestVoice}
            disabled={testingVoice}
            style={{
              ...BTN_PRIMARY,
              opacity: testingVoice ? 0.6 : 1,
              cursor: testingVoice ? "default" : "pointer",
            }}
          >
            {testingVoice ? "▶ Speaking…" : "▶ Test Voice"}
          </button>

        </Section>

        {/* ─── Section 3: Display Settings ─────────────────────────────────────── */}
        <Section title="Display Settings">

          <Field label="Theme">
            <RadioGroup
              options={[
                { label: "Dark", value: "dark" },
                { label: "Light", value: "light" },
              ]}
              value={theme}
              onChange={(val: string) => { if (val !== theme) toggleTheme(); }}
            />
          </Field>

          <Field label="Font Size">
            <RadioGroup
              options={[
                { label: "Small",  value: "small"  },
                { label: "Medium", value: "medium" },
                { label: "Large",  value: "large"  },
              ]}
              value={fontSize}
              onChange={saveFontSize}
            />
          </Field>

        </Section>

        {/* ─── Section 4: Account ───────────────────────────────────────────────── */}
        <Section title="Account">

          <div style={{ marginBottom: 20 }}>
            <div style={{ ...ROW, marginBottom: 8 }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  background: "linear-gradient(135deg,#00d8ff,#00ff88)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontFamily: "monospace",
                  fontSize: 16,
                  fontWeight: 800,
                  color: "#04080f",
                  flexShrink: 0,
                }}
              >
                {user?.username?.[0]?.toUpperCase() ?? "?"}
              </div>
              <div>
                <p style={{ margin: 0, fontFamily: "monospace", fontSize: 14, fontWeight: 700, color: "#fff" }}>
                  {user?.username ?? "—"}
                </p>
                <p style={{ margin: "2px 0 0", fontFamily: "monospace", fontSize: 12, color: "rgba(255,255,255,0.45)" }}>
                  {user?.email ?? "—"}
                </p>
              </div>
            </div>
            <p style={{ margin: 0, fontFamily: "monospace", fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
              Member since {createdAt}
            </p>
          </div>

          <div
            style={{
              borderTop: "1px solid rgba(0,216,255,0.1)",
              paddingTop: 18,
            }}
          >
            <p style={{ ...LABEL, marginBottom: 14, fontSize: 13, color: "rgba(255,255,255,0.55)" }}>
              Change Password
            </p>

            <Field label="Current Password">
              <input
                type="password"
                value={pwCurrent}
                onChange={(e) => setPwCurrent(e.target.value)}
                placeholder="Enter current password"
                style={INPUT}
              />
            </Field>

            <Field label="New Password">
              <input
                type="password"
                value={pwNew}
                onChange={(e) => setPwNew(e.target.value)}
                placeholder="At least 8 characters"
                style={INPUT}
              />
            </Field>

            <Field label="Confirm New Password">
              <input
                type="password"
                value={pwConfirm}
                onChange={(e) => setPwConfirm(e.target.value)}
                placeholder="Repeat new password"
                style={INPUT}
              />
            </Field>

            <button
              onClick={handleChangePassword}
              disabled={savingPw}
              style={{
                ...BTN_PRIMARY,
                opacity: savingPw ? 0.6 : 1,
                cursor: savingPw ? "default" : "pointer",
              }}
            >
              {savingPw ? "Saving…" : "Update Password"}
            </button>
          </div>

        </Section>

        {/* ─── Section 5: Data & Privacy ────────────────────────────────────────── */}
        <Section title="Data & Privacy">

          <div style={{ display: "flex", flexDirection: "column" as const, gap: 12 }}>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" as const, gap: 10 }}>
              <div>
                <p style={{ margin: 0, fontFamily: "monospace", fontSize: 13, color: "rgba(255,255,255,0.80)" }}>
                  Clear Conversation History
                </p>
                <p style={{ margin: "3px 0 0", fontFamily: "monospace", fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
                  Removes all messages from the current session
                </p>
              </div>
              <button onClick={handleClearHistory} style={BTN_GHOST}>Clear History</button>
            </div>

            <div
              style={{
                borderTop: "1px solid rgba(255,255,255,0.07)",
                paddingTop: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap" as const,
                gap: 10,
              }}
            >
              <div>
                <p style={{ margin: 0, fontFamily: "monospace", fontSize: 13, color: "rgba(255,255,255,0.80)" }}>
                  Export All Data
                </p>
                <p style={{ margin: "3px 0 0", fontFamily: "monospace", fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
                  Download your account data as JSON
                </p>
              </div>
              <button onClick={handleExportData} style={BTN_GHOST}>Export JSON</button>
            </div>

            <div
              style={{
                borderTop: "1px solid rgba(255,59,59,0.15)",
                paddingTop: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap" as const,
                gap: 10,
              }}
            >
              <div>
                <p style={{ margin: 0, fontFamily: "monospace", fontSize: 13, color: "#ff6b6b" }}>
                  Delete Account
                </p>
                <p style={{ margin: "3px 0 0", fontFamily: "monospace", fontSize: 11, color: "rgba(255,107,107,0.55)" }}>
                  {confirmDelete
                    ? "Click again to confirm — this cannot be undone"
                    : "Permanently removes your account and all data"}
                </p>
              </div>
              <button
                onClick={handleDeleteAccount}
                style={{
                  ...BTN_DANGER,
                  background: confirmDelete ? "rgba(255,59,59,0.30)" : "rgba(255,59,59,0.15)",
                  boxShadow: confirmDelete ? "0 0 12px rgba(255,59,59,0.25)" : "none",
                }}
              >
                {confirmDelete ? "Confirm Delete" : "Delete Account"}
              </button>
            </div>

          </div>
        </Section>

      </div>
    </div>
  );
}
