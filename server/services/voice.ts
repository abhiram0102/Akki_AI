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
  private wakeWords = ["hey ammu", "ammu", "hello ammu", "hey assistant", "start listening"];
  private securityKeywords = ["exploit", "vulnerability", "attack", "recon", "osint", "pentest", "hack"];
  
  async transcribeAudio(audioData: string): Promise<VoiceTranscriptionResult> {
    const startTime = Date.now();
    
    try {
      // Convert base64 to buffer
      const audioBuffer = Buffer.from(audioData, 'base64');
      
      // Enhanced transcription with security context awareness
      const transcription = await this.performAdvancedTranscription(audioBuffer);
      
      // Detect wake word with cybersecurity context
      const wakeWordDetected = this.detectWakeWord(transcription.text);
      
      // Analyze emotional tone and security intent
      let emotionalTone = "professional";
      let voicePattern = {
        pitch: 0.5,
        speed: 0.5,
        energy: 0.6,
        characteristics: ["focused", "analytical"]
      };
      
      if (transcription.text.length > 10) {
        // Enhanced emotional and intent analysis using Gemini
        const analysis = await aiService.chatCompletion(
          [{ 
            role: "user", 
            content: `As AMMU, analyze this cybersecurity professional's speech for:
1. Emotional tone (professional, excited, concerned, focused, urgent)
2. Security intent (reconnaissance, exploitation, defense, analysis, reporting)
3. Confidence level (1-10)

Text: "${transcription.text}"

Respond in JSON format:
{
  "emotionalTone": "professional|excited|concerned|focused|urgent",
  "securityIntent": "reconnaissance|exploitation|defense|analysis|reporting|general",
  "confidence": 8,
  "urgency": "low|medium|high",
  "containsSecurityTerms": true|false
}` 
          }],
          { temperature: 0.2, jsonMode: true }
        );
        
        try {
          const parsed = JSON.parse(analysis);
          emotionalTone = parsed.emotionalTone || "professional";
          voicePattern.characteristics = [
            parsed.securityIntent || "general",
            parsed.urgency || "medium",
            parsed.containsSecurityTerms ? "security-focused" : "general"
          ];
          voicePattern.energy = Math.min(parsed.confidence / 10, 1.0);
        } catch (parseError) {
          console.log("Failed to parse voice analysis, using defaults");
        }
        
        // Advanced voice pattern analysis for cybersecurity context
        voicePattern = this.analyzeCybersecurityVoicePattern(audioBuffer, transcription.text);
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
      // Fallback to basic transcription
      return {
        text: "Voice transcription currently unavailable",
        confidence: 0.1,
        emotionalTone: "neutral",
        voicePattern: {
          pitch: 0.5,
          speed: 0.5,
          energy: 0.5,
          characteristics: ["fallback"]
        },
        wakeWordDetected: false,
        processingTime: Date.now() - startTime
      };
    }
  }

  private async performAdvancedTranscription(audioBuffer: Buffer): Promise<{ text: string; confidence: number }> {
    // Note: In production, this would integrate with actual speech-to-text service
    // For now, return simulated transcription that would be replaced with real implementation
    return {
      text: "Enhanced transcription would be implemented here with real audio processing",
      confidence: 0.8
    };
  }

  private analyzeCybersecurityVoicePattern(audioBuffer: Buffer, text: string): any {
    // Simulate voice pattern analysis with cybersecurity context
    const securityTermsCount = this.securityKeywords.filter(keyword => 
      text.toLowerCase().includes(keyword)
    ).length;
    
    const urgencyIndicators = ["urgent", "critical", "immediate", "asap", "emergency"];
    const urgencyCount = urgencyIndicators.filter(indicator => 
      text.toLowerCase().includes(indicator)
    ).length;
    
    return {
      pitch: 0.5 + (securityTermsCount * 0.1),
      speed: 0.5 + (urgencyCount * 0.15),
      energy: Math.min(0.9, 0.4 + (securityTermsCount * 0.2) + (urgencyCount * 0.1)),
      characteristics: [
        securityTermsCount > 0 ? "security-focused" : "general",
        urgencyCount > 0 ? "urgent" : "calm",
        text.length > 50 ? "detailed" : "concise"
      ]
    };
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
    // Add emotional context to TTS text based on cybersecurity scenarios
    const tone = emotionalTone || "professional";
    
    switch (tone) {
      case "urgent":
        return `[URGENT] ${text}`;
      case "focused":
        return `[ANALYSIS] ${text}`;
      case "concerned":
        return `[ALERT] ${text}`;
      case "excited":
        return `[DISCOVERY] ${text}`;
      default:
        return text;
    }
  }

  private getSpeedForEmotion(emotionalTone?: string): number {
    switch (emotionalTone) {
      case "urgent": return 1.2;
      case "excited": return 1.1;
      case "concerned": return 0.9;
      case "focused": return 1.0;
      default: return 1.0;
    }
  }

  private getPitchForEmotion(emotionalTone?: string): number {
    switch (emotionalTone) {
      case "urgent": return 1.1;
      case "excited": return 1.2;
      case "concerned": return 0.9;
      case "focused": return 1.0;
      default: return 1.0;
    }
  }
}

export const voiceService = new VoiceService();
