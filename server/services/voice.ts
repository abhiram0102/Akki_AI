import { aiService } from "./ai";
import { emotionalAI } from "./emotional-ai";

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

export interface SpeechSynthesisOptions {
  emotionalTone?: string;
  speed?: number;
  pitch?: number;
  voice?: string;
}

class VoiceService {
  private wakeWords = ["hey ammu", "ammu", "hello ammu"];
  
  async transcribeAudio(audioData: string): Promise<VoiceTranscriptionResult> {
    const startTime = Date.now();
    
    try {
      // Convert base64 to buffer
      const audioBuffer = Buffer.from(audioData, 'base64');
      
      // Transcribe using Gemini (Note: Gemini doesn't have native audio transcription, using fallback)
      const transcription = { text: "Audio transcription not available yet", confidence: 0.5 };
      
      // Detect wake word
      const wakeWordDetected = this.detectWakeWord(transcription.text);
      
      // Analyze emotional tone
      let emotionalTone = "neutral";
      let voicePattern = {
        pitch: 0.5,
        speed: 0.5,
        energy: 0.5,
        characteristics: []
      };
      
      if (transcription.text.length > 10) {
        // Analyze emotional tone using Gemini
        const analysis = await aiService.chatCompletion(
          [{ role: "user", content: `Analyze the emotional tone of this text: "${transcription.text}". Respond with just the tone word (happy, sad, angry, neutral, etc.)` }],
          { temperature: 0.3 }
        );
        emotionalTone = analysis.trim().toLowerCase();
        
        // Simulate voice pattern analysis (in production, use actual audio analysis)
        voicePattern = this.analyzeVoicePattern(audioBuffer, transcription.text);
      }
      
      const processingTime = Date.now() - startTime;
      
      return {
        text: transcription.text,
        confidence: transcription.confidence,
        emotionalTone,
        voicePattern,
        wakeWordDetected,
        processingTime
      };
    } catch (error) {
      console.error("Voice transcription error:", error);
      throw new Error(`Voice transcription failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  async synthesizeSpeech(
    text: string, 
    emotionalTone?: string,
    options: SpeechSynthesisOptions = {}
  ): Promise<string> {
    try {
      // In a real implementation, you would use a TTS service like ElevenLabs or Azure Speech
      // For now, we'll return a placeholder indicating browser TTS should be used
      
      const enhancedText = this.enhanceTextForEmotion(text, emotionalTone);
      
      // Return metadata for client-side TTS
      return JSON.stringify({
        text: enhancedText,
        emotionalTone,
        options: {
          rate: this.getSpeedForEmotion(emotionalTone),
          pitch: this.getPitchForEmotion(emotionalTone),
          voice: options.voice || "default"
        }
      });
    } catch (error) {
      console.error("Speech synthesis error:", error);
      throw new Error(`Speech synthesis failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  async processWakeWord(
    audioData: string,
    userId: string
  ): Promise<{ detected: boolean; confidence: number }> {
    try {
      const audioBuffer = Buffer.from(audioData, 'base64');
      const transcription = { text: "Wake word detection pending", confidence: 0.5 };
      
      const detected = this.detectWakeWord(transcription.text);
      const confidence = detected ? transcription.confidence : 0;
      
      if (detected) {
        // Update user's emotional bond for voice interaction
        await emotionalAI.updateEmotionalBond(userId, "engaged", "Voice activation");
      }
      
      return { detected, confidence };
    } catch (error) {
      console.error("Wake word processing error:", error);
      return { detected: false, confidence: 0 };
    }
  }

  private detectWakeWord(text: string): boolean {
    const lowercaseText = text.toLowerCase().trim();
    
    return this.wakeWords.some(wakeWord => 
      lowercaseText.includes(wakeWord) ||
      this.calculateSimilarity(lowercaseText, wakeWord) > 0.8
    );
  }

  private calculateSimilarity(str1: string, str2: string): number {
    // Simple Levenshtein distance-based similarity
    const len1 = str1.length;
    const len2 = str2.length;
    
    if (len1 === 0) return len2 === 0 ? 1 : 0;
    if (len2 === 0) return 0;
    
    const matrix = Array(len1 + 1).fill(null).map(() => Array(len2 + 1).fill(null));
    
    for (let i = 0; i <= len1; i++) matrix[i][0] = i;
    for (let j = 0; j <= len2; j++) matrix[0][j] = j;
    
    for (let i = 1; i <= len1; i++) {
      for (let j = 1; j <= len2; j++) {
        const cost = str1[i - 1] === str2[j - 1] ? 0 : 1;
        matrix[i][j] = Math.min(
          matrix[i - 1][j] + 1,      // deletion
          matrix[i][j - 1] + 1,      // insertion
          matrix[i - 1][j - 1] + cost // substitution
        );
      }
    }
    
    const maxLen = Math.max(len1, len2);
    return (maxLen - matrix[len1][len2]) / maxLen;
  }

  private analyzeVoicePattern(audioBuffer: Buffer, text: string): any {
    // Placeholder for voice pattern analysis
    // In production, you would use audio processing libraries to analyze:
    // - Fundamental frequency (pitch)
    // - Speaking rate (speed)
    // - Volume/energy levels
    // - Voice characteristics
    
    const textLength = text.length;
    const estimatedDuration = audioBuffer.length / 16000; // Assuming 16kHz sample rate
    
    return {
      pitch: Math.random() * 0.4 + 0.3, // 0.3-0.7
      speed: textLength / estimatedDuration / 5, // Rough WPM estimation
      energy: Math.random() * 0.6 + 0.2, // 0.2-0.8
      characteristics: this.deriveVoiceCharacteristics(text)
    };
  }

  private deriveVoiceCharacteristics(text: string): string[] {
    const characteristics = [];
    
    if (text.includes("!") || text.includes("?")) {
      characteristics.push("expressive");
    }
    
    if (text.length > 100) {
      characteristics.push("detailed");
    }
    
    if (/[A-Z]{2,}/.test(text)) {
      characteristics.push("emphatic");
    }
    
    return characteristics;
  }

  private enhanceTextForEmotion(text: string, emotionalTone?: string): string {
    if (!emotionalTone || emotionalTone === "neutral") {
      return text;
    }
    
    // Add emotional cues to text for better TTS rendering
    const emotionalMarkers: Record<string, { prefix: string; suffix: string }> = {
      happy: { prefix: "", suffix: " 😊" },
      excited: { prefix: "", suffix: "!" },
      concerned: { prefix: "*sighs* ", suffix: "" },
      supportive: { prefix: "", suffix: " I'm here to help." },
      confident: { prefix: "", suffix: "" },
      empathetic: { prefix: "I understand... ", suffix: "" }
    };
    
    const marker = emotionalMarkers[emotionalTone];
    if (marker) {
      return `${marker.prefix}${text}${marker.suffix}`;
    }
    
    return text;
  }

  private getSpeedForEmotion(emotionalTone?: string): number {
    const speedMap: Record<string, number> = {
      excited: 1.2,
      happy: 1.1,
      neutral: 1.0,
      concerned: 0.9,
      sad: 0.8,
      empathetic: 0.9
    };
    
    return speedMap[emotionalTone || "neutral"] || 1.0;
  }

  private getPitchForEmotion(emotionalTone?: string): number {
    const pitchMap: Record<string, number> = {
      excited: 1.2,
      happy: 1.1,
      neutral: 1.0,
      concerned: 0.9,
      sad: 0.8,
      empathetic: 1.0
    };
    
    return pitchMap[emotionalTone || "neutral"] || 1.0;
  }
}

export const voiceService = new VoiceService();
