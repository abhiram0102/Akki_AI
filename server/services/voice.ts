import { GoogleGenerativeAI } from "@google/generative-ai";

const apiKey = process.env.GEMINI_API_KEY;
const genAI = apiKey ? new GoogleGenerativeAI(apiKey) : null;

export interface VoiceTranscriptionResult {
  text: string;
  confidence: number;
  emotionalTone?: string;
  voicePattern?: {
    pitch: number;
    speed: number;
    energy: number;
    characteristics: string[];
  };
  wakeWordDetected: boolean;
  processingTime: number;
}

const WAKE_WORDS = ["hey akki", "hey ammu", "akki", "ammu", "hello akki", "hello ammu"];

class VoiceService {
  /**
   * Transcribe audio using Gemini multimodal API.
   * Accepts either a base64 string or a Buffer.
   */
  async transcribeAudio(
    audioData: string | Buffer,
    mimeType = "audio/webm"
  ): Promise<VoiceTranscriptionResult> {
    const startTime = Date.now();

    try {
      if (!genAI) throw new Error("GEMINI_API_KEY not configured");

      // Normalise to base64 string
      const base64 =
        Buffer.isBuffer(audioData)
          ? audioData.toString("base64")
          : audioData;

      const model = genAI.getGenerativeModel({ model: "gemini-2.0-flash" });

      const result = await model.generateContent([
        {
          inlineData: {
            mimeType,
            data: base64,
          },
        },
        {
          text: `Transcribe this audio exactly. Return ONLY the spoken words, nothing else. If there is no speech, return an empty string.`,
        },
      ]);

      const text = result.response.text().trim();
      const wakeWordDetected = WAKE_WORDS.some((w) =>
        text.toLowerCase().includes(w)
      );

      return {
        text,
        confidence: text.length > 0 ? 0.9 : 0.1,
        emotionalTone: "professional",
        voicePattern: {
          pitch: 0.5,
          speed: 0.5,
          energy: 0.6,
          characteristics: ["transcribed"],
        },
        wakeWordDetected,
        processingTime: Date.now() - startTime,
      };
    } catch (error: any) {
      console.error("[VoiceService] transcribeAudio error:", error?.message ?? error);
      // Return a clear error so the caller knows transcription failed
      return {
        text: "",
        confidence: 0,
        emotionalTone: "neutral",
        voicePattern: { pitch: 0.5, speed: 0.5, energy: 0.5, characteristics: ["error"] },
        wakeWordDetected: false,
        processingTime: Date.now() - startTime,
      };
    }
  }

  async synthesizeSpeech(
    text: string,
    emotionalTone?: string
  ): Promise<string> {
    // Return metadata for client-side Web Speech TTS
    return JSON.stringify({
      text,
      emotionalTone: emotionalTone || "professional",
      options: {
        rate: this.getSpeedForEmotion(emotionalTone),
        pitch: this.getPitchForEmotion(emotionalTone),
      },
    });
  }

  private getSpeedForEmotion(tone?: string): number {
    const map: Record<string, number> = {
      urgent: 1.2, excited: 1.1, concerned: 0.9, focused: 1.0,
    };
    return map[tone ?? ""] ?? 1.0;
  }

  private getPitchForEmotion(tone?: string): number {
    const map: Record<string, number> = {
      urgent: 1.1, excited: 1.2, concerned: 0.9, focused: 1.0,
    };
    return map[tone ?? ""] ?? 1.0;
  }
}

export const voiceService = new VoiceService();
