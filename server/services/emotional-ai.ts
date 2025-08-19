import { storage } from "../storage";
import { aiService } from "./ai";
import type { User } from "@shared/schema";

export interface EmotionalState {
  bondLevel: number;
  currentMood: string;
  trustLevel: number;
  personalityTraits: string[];
  preferredCommunicationStyle: string;
}

export interface PersonalityProfile {
  traits: string[];
  communicationPreferences: string[];
  emotionalNeeds: string[];
  bondingFactors: string[];
}

export interface EmotionalMemory {
  type: "positive" | "negative" | "neutral";
  intensity: number;
  context: string;
  timestamp: Date;
  triggers: string[];
}

class EmotionalAI {
  async updateEmotionalBond(
    userId: string,
    emotionalTone: string,
    context: string,
    interactionType: "voice" | "text" = "text"
  ): Promise<void> {
    try {
      const user = await storage.getUser(userId);
      if (!user) return;

      const currentState = user.emotionalState || this.getDefaultEmotionalState();
      
      // Calculate bond level change based on interaction
      const bondChange = this.calculateBondChange(emotionalTone, context, interactionType);
      const newBondLevel = Math.max(0, Math.min(100, currentState.bondLevel + bondChange));
      
      // Update mood based on interaction
      const newMood = this.determineNewMood(currentState.currentMood, emotionalTone);
      
      // Update trust level
      const trustChange = this.calculateTrustChange(emotionalTone, context);
      const newTrustLevel = Math.max(0, Math.min(1, currentState.trustLevel + trustChange));
      
      // Update personality traits based on observations
      const updatedTraits = this.updatePersonalityTraits(
        currentState.personalityTraits,
        emotionalTone,
        context
      );
      
      const newEmotionalState: EmotionalState = {
        bondLevel: newBondLevel,
        currentMood: newMood,
        trustLevel: newTrustLevel,
        personalityTraits: updatedTraits,
        preferredCommunicationStyle: this.determineCommunicationStyle(updatedTraits, newBondLevel)
      };

      await storage.updateUserEmotionalState(userId, newEmotionalState);
      
      // Create emotional memory
      await this.createEmotionalMemory(userId, {
        type: this.categorizeEmotionalType(emotionalTone),
        intensity: this.calculateEmotionalIntensity(emotionalTone, context),
        context,
        timestamp: new Date(),
        triggers: this.extractEmotionalTriggers(context)
      });
    } catch (error) {
      console.error("Error updating emotional bond:", error);
    }
  }

  async generatePersonalizedResponse(
    userId: string,
    content: string,
    context: string
  ): Promise<string> {
    try {
      const user = await storage.getUser(userId);
      if (!user) return content;

      const emotionalState = user.emotionalState || this.getDefaultEmotionalState();
      const recentMemories = await storage.getRecentMemories(userId, 5);
      
      // Get emotional memories
      const emotionalMemories = recentMemories.filter(m => m.type === "emotional");
      
      const personalizedResponse = await aiService.generateEmotionalResponse(
        content,
        emotionalState,
        emotionalState.bondLevel
      );

      return personalizedResponse;
    } catch (error) {
      console.error("Error generating personalized response:", error);
      return content;
    }
  }

  async analyzeUserPersonality(userId: string): Promise<PersonalityProfile> {
    try {
      const memories = await storage.getUserMemories(userId);
      const voiceInteractions = await storage.getUserVoiceInteractions(userId, 20);
      
      // Analyze patterns in user interactions
      const analysisPrompt = `Analyze the following user interaction patterns and provide a personality profile:

      Recent memories: ${JSON.stringify(memories.slice(0, 10))}
      Voice interactions: ${JSON.stringify(voiceInteractions.slice(0, 5))}
      
      Provide analysis in JSON format with:
      - traits: personality traits observed
      - communicationPreferences: preferred communication styles
      - emotionalNeeds: emotional needs and preferences
      - bondingFactors: what helps build stronger relationships`;

      const analysis = await aiService.chatCompletion(
        [{ role: "user", content: analysisPrompt }],
        { jsonMode: true, temperature: 0.3 }
      );

      return JSON.parse(analysis);
    } catch (error) {
      console.error("Error analyzing personality:", error);
      return this.getDefaultPersonalityProfile();
    }
  }

  async createEmotionalMemory(userId: string, memory: EmotionalMemory): Promise<void> {
    try {
      await storage.createMemory({
        ownerId: userId,
        type: "emotional",
        content: {
          summary: `Emotional interaction: ${memory.type}`,
          details: {
            emotionalType: memory.type,
            intensity: memory.intensity,
            context: memory.context,
            triggers: memory.triggers
          },
          importance: memory.intensity,
          emotionalWeight: memory.intensity
        },
        strength: memory.intensity,
        expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000) // 30 days
      });
    } catch (error) {
      console.error("Error creating emotional memory:", error);
    }
  }

  private calculateBondChange(
    emotionalTone: string,
    context: string,
    interactionType: "voice" | "text"
  ): number {
    let bondChange = 0;
    
    // Base change based on emotional tone
    const toneMultipliers: Record<string, number> = {
      happy: 2,
      excited: 2.5,
      grateful: 3,
      frustrated: -1,
      angry: -2,
      disappointed: -1.5,
      neutral: 0.5
    };
    
    bondChange += toneMultipliers[emotionalTone] || 0.5;
    
    // Voice interactions create stronger bonds
    if (interactionType === "voice") {
      bondChange *= 1.5;
    }
    
    // Context-based bonuses
    if (context.includes("thank") || context.includes("help")) {
      bondChange += 1;
    }
    
    if (context.includes("problem") || context.includes("issue")) {
      bondChange += 0.5; // Helping with problems builds trust
    }
    
    return bondChange;
  }

  private calculateTrustChange(emotionalTone: string, context: string): number {
    let trustChange = 0;
    
    // Positive interactions build trust
    if (["happy", "grateful", "satisfied", "excited"].includes(emotionalTone)) {
      trustChange += 0.02;
    }
    
    // Negative interactions can damage trust
    if (["frustrated", "angry", "disappointed"].includes(emotionalTone)) {
      trustChange -= 0.01;
    }
    
    // Successful problem solving builds significant trust
    if (context.includes("solved") || context.includes("fixed") || context.includes("working")) {
      trustChange += 0.05;
    }
    
    return trustChange;
  }

  private determineNewMood(currentMood: string, emotionalTone: string): string {
    // Simple mood transition logic
    const moodTransitions: Record<string, Record<string, string>> = {
      neutral: {
        happy: "happy",
        excited: "excited",
        frustrated: "concerned",
        angry: "upset"
      },
      happy: {
        excited: "excited",
        frustrated: "neutral",
        angry: "concerned"
      },
      excited: {
        happy: "happy",
        frustrated: "disappointed",
        angry: "upset"
      }
    };
    
    return moodTransitions[currentMood]?.[emotionalTone] || emotionalTone || currentMood;
  }

  private updatePersonalityTraits(
    currentTraits: string[],
    emotionalTone: string,
    context: string
  ): string[] {
    const traits = [...currentTraits];
    
    // Add traits based on observations
    if (context.includes("detail") && !traits.includes("detail-oriented")) {
      traits.push("detail-oriented");
    }
    
    if (emotionalTone === "excited" && !traits.includes("enthusiastic")) {
      traits.push("enthusiastic");
    }
    
    if (context.includes("security") && !traits.includes("security-conscious")) {
      traits.push("security-conscious");
    }
    
    // Limit traits to avoid bloat
    return traits.slice(-10);
  }

  private determineCommunicationStyle(traits: string[], bondLevel: number): string {
    if (bondLevel > 75) return "friendly-companion";
    if (bondLevel > 50) return "warm-supportive";
    if (bondLevel > 25) return "helpful-professional";
    
    return "professional-formal";
  }

  private categorizeEmotionalType(emotionalTone: string): "positive" | "negative" | "neutral" {
    const positiveEmotions = ["happy", "excited", "grateful", "satisfied", "calm"];
    const negativeEmotions = ["frustrated", "angry", "disappointed", "sad", "worried"];
    
    if (positiveEmotions.includes(emotionalTone)) return "positive";
    if (negativeEmotions.includes(emotionalTone)) return "negative";
    return "neutral";
  }

  private calculateEmotionalIntensity(emotionalTone: string, context: string): number {
    const baseIntensity: Record<string, number> = {
      excited: 0.9,
      angry: 0.8,
      frustrated: 0.7,
      happy: 0.6,
      disappointed: 0.6,
      neutral: 0.3,
      calm: 0.4
    };
    
    let intensity = baseIntensity[emotionalTone] || 0.5;
    
    // Amplify based on context
    if (context.includes("!") || context.includes("?")) {
      intensity += 0.1;
    }
    
    if (context.length > 100) {
      intensity += 0.1; // Longer messages indicate higher investment
    }
    
    return Math.min(1, intensity);
  }

  private extractEmotionalTriggers(context: string): string[] {
    const triggers = [];
    
    // Extract emotional keywords
    const emotionalKeywords = [
      "problem", "issue", "help", "thank", "frustrated", "excited",
      "security", "vulnerability", "attack", "defense", "solution"
    ];
    
    for (const keyword of emotionalKeywords) {
      if (context.toLowerCase().includes(keyword)) {
        triggers.push(keyword);
      }
    }
    
    return triggers;
  }

  private getDefaultEmotionalState(): EmotionalState {
    return {
      bondLevel: 0,
      currentMood: "neutral",
      trustLevel: 0.5,
      personalityTraits: [],
      preferredCommunicationStyle: "professional"
    };
  }

  private getDefaultPersonalityProfile(): PersonalityProfile {
    return {
      traits: ["analytical", "curious"],
      communicationPreferences: ["clear", "detailed"],
      emotionalNeeds: ["competence", "autonomy"],
      bondingFactors: ["helpfulness", "reliability"]
    };
  }
}

export const emotionalAI = new EmotionalAI();
