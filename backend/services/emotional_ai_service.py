"""
AKKI Emotional AI Service — Bond/trust dynamics, mood tracking,
personality adaptation, and emotionally-aware response generation.

Migrated from TypeScript: server/services/emotional-ai.ts (350 lines)
"""
import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models import User, Memory

import asyncio
logger = logging.getLogger("akki.emotional_ai")

# ── Constants ─────────────────────────────────────────────────────────────────

BOND_MULTIPLIERS: dict[str, float] = {
    "happy": 2.0,
    "excited": 2.5,
    "grateful": 3.0,
    "frustrated": -1.0,
    "angry": -2.0,
    "disappointed": -1.5,
    "neutral": 0.5,
    "curious": 1.5,
    "confused": 0.5,
    "anxious": -0.5,
    "confident": 1.5,
    "focused": 1.0,
}

VOICE_BOND_MULTIPLIER = 1.5
EMOTIONAL_MEMORY_TTL_DAYS = 30
PERSONALITY_ANALYSIS_INTERVAL = 10  # Analyze personality every 10 interactions

POSITIVE_TONES = {"happy", "excited", "grateful", "confident", "curious", "focused"}
NEGATIVE_TONES = {"frustrated", "angry", "disappointed", "anxious"}

PROBLEM_SOLVING_KEYWORDS = [
    "solve", "fix", "debug", "analyze", "investigate", "research",
    "help", "understand", "learn", "find", "figure out", "work through",
]

MOOD_TRANSITIONS: dict[str, dict[str, str]] = {
    "neutral": {
        "happy": "content", "excited": "engaged", "grateful": "warm",
        "frustrated": "concerned", "angry": "alert", "disappointed": "reflective",
        "curious": "engaged", "anxious": "attentive", "confident": "assured",
        "focused": "engaged",
    },
    "content": {
        "happy": "happy", "excited": "excited", "frustrated": "concerned",
        "angry": "alert", "neutral": "content", "curious": "engaged",
    },
    "concerned": {
        "happy": "relieved", "grateful": "warm", "frustrated": "empathetic",
        "neutral": "attentive", "curious": "analytical",
    },
    "engaged": {
        "happy": "enthusiastic", "excited": "energised", "frustrated": "focused",
        "neutral": "content", "curious": "deeply-engaged",
    },
}


class EmotionalAI:
    """Manages user-AI emotional bonding, trust dynamics, and personality adaptation."""

    # ── Public Methods ────────────────────────────────────────────────────────

    async def update_emotional_bond(
        self,
        user_id: str,
        emotional_tone: str,
        context: str,
        interaction_type: str = "text",
    ) -> None:
        """Update the user's emotional bond after an interaction."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    return

                current_state = user.emotional_state or self._get_default_emotional_state()

                # Calculate changes
                bond_change = self._calculate_bond_change(
                    emotional_tone, context, interaction_type
                )
                trust_change = self._calculate_trust_change(emotional_tone, context)
                new_mood = self._determine_new_mood(
                    current_state.get("currentMood", "neutral"), emotional_tone
                )
                new_traits = self._update_personality_traits(
                    current_state.get("personalityTraits", []),
                    emotional_tone,
                    context,
                )

                # Apply changes with clamping
                new_bond = max(0, min(100, current_state.get("bondLevel", 0) + bond_change))
                new_trust = max(0.0, min(1.0, current_state.get("trustLevel", 0.5) + trust_change))
                new_style = self._determine_communication_style(new_traits, new_bond)

                new_state = {
                    "bondLevel": round(new_bond, 2),
                    "currentMood": new_mood,
                    "trustLevel": round(new_trust, 4),
                    "personalityTraits": new_traits,
                    "preferredCommunicationStyle": new_style,
                }

                # Persist to database
                user.emotional_state = new_state
                await session.commit()

                # Create emotional memory with TTL
                await self._store_emotional_memory(
                    session, user_id, emotional_tone, context, interaction_type
                )

                # Periodically update personality profile for deeper personalization
                interaction_count = current_state.get("_interactionCount", 0) + 1
                new_state["_interactionCount"] = interaction_count

                # Update interaction count in user state
                user.emotional_state = new_state
                await session.commit()

                # Run personality analysis periodically (every 10 interactions) or at key milestones
                if interaction_count % self.PERSONALITY_ANALYSIS_INTERVAL == 0:
                    # Fire and forget - don't wait for personality analysis
                    asyncio.create_task(self._update_personalized_bond_factors(user_id, session))

        except Exception as e:
            logger.error("Failed to update emotional bond for user %s: %s", user_id, e)

    async def _update_personalized_bond_factors(self, user_id: str, session: AsyncSession):
        """Update bond factors based on personality analysis for deeper personalization."""
        try:
            # Get current user state
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return

            current_state = user.emotional_state or self._get_default_emotional_state()

            # Analyze personality from interaction history
            personality_profile = await self.analyze_user_personality(user_id)

            # Adjust bond factors based on personality compatibility
            bond_modifier = self._calculate_personality_bond_modifier(
                personality_profile, current_state.get("personalityTraits", [])
            )

            # Apply subtle bond adjustment based on personality alignment
            if bond_modifier != 0.0:
                current_bond = current_state.get("bondLevel", 0)
                new_bond = max(0, min(100, current_bond + bond_modifier))

                # Update bond level with personality-based adjustment
                updated_state = current_state.copy()
                updated_state["bondLevel"] = round(new_bond, 2)
                user.emotional_state = updated_state
                await session.commit()

                logger.info(f"[EmotionalAI] Applied personality-based bond adjustment: {bond_modifier} for user {user_id}")

        except Exception as e:
            logger.debug(f"[EmotionalAI] Failed to update personalized bond factors: {e}")

    def _calculate_personality_bond_modifier(self, personality_profile: dict, current_traits: list[str]) -> float:
        """Calculate bond modifier based on personality alignment."""
        try:
            # Get user's preferred traits from personality profile
            preferred_traits = set(personality_profile.get("traits", []))
            current_traits_set = set(current_traits)

            # Calculate overlap
            if not preferred_traits:
                return 0.0

            overlap = len(preferred_traits.intersection(current_traits_set))
            total_preferred = len(preferred_traits)

            if total_preferred == 0:
                return 0.0

            alignment_ratio = overlap / total_preferred

            # Convert to bond modifier: -0.5 to +0.5
            # 0.0 alignment = -0.5 modifier (misalignment)
            # 1.0 alignment = +0.5 modifier (perfect alignment)
            modifier = (alignment_ratio - 0.5) * 2.0 * 0.5  # Scale to ±0.5

            return round(modifier, 3)
        except Exception:
            return 0.0

    async def generate_personalized_response(
        self, user_id: str, content: str, context: str
    ) -> str:
        """Generate an emotionally-tuned response based on the user's emotional state."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    return content

                state = user.emotional_state or self._get_default_emotional_state()
                bond_level = state.get("bondLevel", 0)
                mood = state.get("currentMood", "neutral")
                style = state.get("preferredCommunicationStyle", "professional")

                # Get recent emotional memories for context
                mem_result = await session.execute(
                    select(Memory)
                    .where(Memory.user_id == user_id, Memory.type == "emotional")
                    .order_by(desc(Memory.last_accessed_at))
                    .limit(5)
                )
                recent_memories = mem_result.scalars().all()
                memory_context = "; ".join(
                    str(m.content)[:100] for m in recent_memories
                ) if recent_memories else "No recent emotional context"

                # Use AI service for emotionally-tuned response
                from backend.services.ai_service import ai_service

                prompt = f"""Adapt the following response to match this emotional context:
- Communication style: {style}
- User mood: {mood}
- Bond level: {bond_level}/100
- Recent emotional context: {memory_context}

Original response:
{content[:2000]}

Maintain all technical accuracy. Only adjust tone and warmth level.
If bond level > 50, use a warmer, more personal tone.
If bond level < 25, keep it strictly professional."""

                adapted = await ai_service.chat_completion(
                    [{"role": "user", "content": prompt}],
                    temperature=0.4,
                    user_id=user_id,
                )
                return adapted

        except Exception as e:
            logger.error("Failed to generate personalized response: %s", e)
            return content  # Graceful degradation: return original

    async def analyze_user_personality(self, user_id: str) -> dict:
        """Analyze user personality from interaction history."""
        try:
            async with AsyncSessionLocal() as session:
                # Get user memories
                mem_result = await session.execute(
                    select(Memory)
                    .where(Memory.user_id == user_id)
                    .order_by(desc(Memory.last_accessed_at))
                    .limit(50)
                )
                memories = mem_result.scalars().all()

                if not memories:
                    return self._get_default_personality_profile()

                memory_summary = "\n".join(
                    f"- [{m.type}] {str(m.content)[:120]}" for m in memories[:20]
                )

                from backend.services.ai_service import ai_service

                prompt = f"""Analyze this user's personality based on their interaction history:

{memory_summary}

Return ONLY valid JSON:
{{
  "traits": ["analytical", "curious"],
  "communicationPreferences": ["technical detail", "structured responses"],
  "emotionalNeeds": ["validation", "encouragement"],
  "bondingFactors": ["shared problem-solving", "technical discussions"]
}}"""

                result = await ai_service.chat_completion(
                    [{"role": "user", "content": prompt}],
                    json_mode=True,
                    temperature=0.3,
                    user_id=user_id,
                )
                return json.loads(result)

        except Exception as e:
            logger.error("Failed to analyze personality for user %s: %s", user_id, e)
            return self._get_default_personality_profile()

    async def create_emotional_memory(
        self, user_id: str, memory: dict
    ) -> None:
        """Store an emotional memory with 30-day TTL."""
        try:
            async with AsyncSessionLocal() as session:
                intensity = memory.get("intensity", 0.5)
                mem = Memory(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    type="emotional",
                    content={
                        "summary": f"Emotional interaction: {memory.get('type', 'neutral')}",
                        "details": {
                            "emotionalType": memory.get("type", "neutral"),
                            "intensity": intensity,
                            "context": memory.get("context", ""),
                            "triggers": memory.get("triggers", []),
                        },
                        "importance": intensity,
                        "emotionalWeight": intensity,
                    },
                    strength=intensity,
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                )
                session.add(mem)
                await session.commit()
        except Exception as e:
            logger.error("Failed to create emotional memory: %s", e)

    async def analyze_emotional_tone(self, text: str) -> str:
        """Detect the emotional tone of a text. Returns a tone key from BOND_MULTIPLIERS."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["thank", "grateful", "awesome", "great job", "perfect"]):
            return "grateful"
        if any(w in text_lower for w in ["excited", "amazing", "wow", "incredible", "fantastic"]):
            return "excited"
        if any(w in text_lower for w in ["happy", "glad", "pleased", "good", "nice"]):
            return "happy"
        if any(w in text_lower for w in ["frustrated", "annoying", "ugh", "doesn't work", "broken", "wrong"]):
            return "frustrated"
        if any(w in text_lower for w in ["angry", "upset", "hate", "terrible", "awful"]):
            return "angry"
        if any(w in text_lower for w in ["confused", "don't understand", "unclear", "what do you mean"]):
            return "confused"
        if any(w in text_lower for w in ["curious", "interesting", "tell me more", "how does", "why", "what is"]):
            return "curious"
        if any(w in text_lower for w in ["learn", "understand", "study", "explain", "teach"]):
            return "focused"
        if any(w in text_lower for w in ["confident", "sure", "definitely", "absolutely", "of course"]):
            return "confident"
        return "neutral"

    # ── Private Methods ───────────────────────────────────────────────────────

    def _calculate_bond_change(
        self, emotional_tone: str, context: str, interaction_type: str
    ) -> float:
        """Calculate bond level change from an interaction."""
        base = 1.0
        tone_multiplier = BOND_MULTIPLIERS.get(emotional_tone.lower(), 0.5)
        voice_multiplier = VOICE_BOND_MULTIPLIER if interaction_type == "voice" else 1.0
        return base * tone_multiplier * voice_multiplier

    def _calculate_trust_change(self, emotional_tone: str, context: str) -> float:
        """Calculate trust level change from an interaction."""
        tone_lower = emotional_tone.lower()

        if tone_lower in POSITIVE_TONES:
            change = 0.02
        elif tone_lower in NEGATIVE_TONES:
            change = -0.01
        else:
            change = 0.005

        # Bonus for problem-solving interactions
        context_lower = context.lower()
        if any(kw in context_lower for kw in PROBLEM_SOLVING_KEYWORDS):
            change += 0.05

        return change

    def _determine_new_mood(self, current_mood: str, emotional_tone: str) -> str:
        """Determine new AI mood based on current mood and user's emotional tone."""
        tone_lower = emotional_tone.lower()
        mood_lower = current_mood.lower()

        transitions = MOOD_TRANSITIONS.get(mood_lower, MOOD_TRANSITIONS["neutral"])
        return transitions.get(tone_lower, mood_lower)

    def _update_personality_traits(
        self, current_traits: list[str], emotional_tone: str, context: str
    ) -> list[str]:
        """Update personality traits based on interaction patterns."""
        traits = list(current_traits)
        context_lower = context.lower()

        # Infer new traits from context
        trait_indicators = {
            "analytical": ["analyze", "investigate", "research", "data", "metrics"],
            "creative": ["idea", "creative", "design", "innovative", "brainstorm"],
            "methodical": ["step by step", "systematic", "procedure", "process"],
            "curious": ["why", "how does", "explain", "learn", "understand"],
            "decisive": ["decide", "choose", "action", "execute", "implement"],
            "collaborative": ["team", "together", "help", "share", "collaborate"],
            "detail-oriented": ["specific", "detail", "exact", "precise", "thorough"],
            "security-minded": ["security", "vulnerability", "threat", "risk", "attack"],
        }

        for trait, keywords in trait_indicators.items():
            if any(kw in context_lower for kw in keywords) and trait not in traits:
                traits.append(trait)

        # Cap at 10 traits (keep most recent)
        return traits[-10:]

    def _determine_communication_style(
        self, traits: list[str], bond_level: float
    ) -> str:
        """Determine communication style based on bond level and personality."""
        if bond_level > 75:
            return "friendly-companion"
        elif bond_level > 50:
            return "warm-supportive"
        elif bond_level > 25:
            return "helpful-professional"
        else:
            return "professional-formal"

    def _categorize_emotional_type(self, emotional_tone: str) -> str:
        """Categorize an emotional tone as positive, negative, or neutral."""
        tone = emotional_tone.lower()
        if tone in POSITIVE_TONES:
            return "positive"
        elif tone in NEGATIVE_TONES:
            return "negative"
        return "neutral"

    def _calculate_emotional_intensity(
        self, emotional_tone: str, context: str
    ) -> float:
        """Calculate emotional intensity (0.0 - 1.0)."""
        base_intensities = {
            "excited": 0.9, "angry": 0.85, "grateful": 0.8,
            "frustrated": 0.7, "happy": 0.7, "disappointed": 0.6,
            "anxious": 0.6, "confident": 0.65, "curious": 0.5,
            "focused": 0.5, "confused": 0.4, "neutral": 0.2,
        }
        intensity = base_intensities.get(emotional_tone.lower(), 0.3)

        # Intensity boost for longer/more detailed context
        if len(context) > 200:
            intensity = min(1.0, intensity + 0.1)

        return round(intensity, 2)

    def _extract_emotional_triggers(self, context: str) -> list[str]:
        """Extract emotional triggers from interaction context."""
        triggers: list[str] = []
        context_lower = context.lower()

        trigger_patterns = {
            "achievement": ["solved", "completed", "succeeded", "finished", "achieved"],
            "frustration": ["error", "failed", "broken", "stuck", "can't", "doesn't work"],
            "learning": ["learned", "understood", "discovered", "realized"],
            "challenge": ["difficult", "complex", "challenging", "hard"],
            "collaboration": ["help", "together", "team", "share"],
            "security-concern": ["vulnerability", "breach", "attack", "compromised"],
        }

        for trigger, keywords in trigger_patterns.items():
            if any(kw in context_lower for kw in keywords):
                triggers.append(trigger)

        return triggers

    async def _store_emotional_memory(
        self,
        session: AsyncSession,
        user_id: str,
        emotional_tone: str,
        context: str,
        interaction_type: str,
    ) -> None:
        """Create and persist an emotional memory with TTL."""
        try:
            emotional_type = self._categorize_emotional_type(emotional_tone)
            intensity = self._calculate_emotional_intensity(emotional_tone, context)
            triggers = self._extract_emotional_triggers(context)

            mem = Memory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                type="emotional",
                content={
                    "summary": f"Emotional interaction: {emotional_type}",
                    "details": {
                        "emotionalType": emotional_type,
                        "tone": emotional_tone,
                        "context": context[:500],
                        "triggers": triggers,
                        "interactionType": interaction_type,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    "importance": intensity,
                    "emotionalWeight": intensity,
                },
                strength=intensity,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
            session.add(mem)
            await session.commit()
        except Exception as e:
            logger.debug("Failed to store emotional memory: %s", e)

    def _get_default_emotional_state(self) -> dict:
        """Return the default emotional state for new users."""
        return {
            "bondLevel": 0,
            "currentMood": "neutral",
            "trustLevel": 0.5,
            "personalityTraits": [],
            "preferredCommunicationStyle": "professional",
        }

    def _get_default_personality_profile(self) -> dict:
        """Return the default personality profile."""
        return {
            "traits": ["analytical"],
            "communicationPreferences": ["technical detail", "structured responses"],
            "emotionalNeeds": ["clarity", "efficiency"],
            "bondingFactors": ["problem-solving", "knowledge sharing"],
        }

    # ── Personality-Aware Bonding Enhancements ────────────────────────
    async def _update_personalized_bond_factors(self, user_id: str, session: AsyncSession):
        """Update bond factors based on personality analysis for deeper personalization."""
        try:
            # Get current user state
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return

            current_state = user.emotional_state or self._get_default_emotional_state()

            # Analyze personality from interaction history
            personality_profile = await self.analyze_user_personality(user_id)

            # Adjust bond factors based on personality compatibility
            bond_modifier = self._calculate_personality_bond_modifier(
                personality_profile, current_state.get("personalityTraits", [])
            )

            # Apply subtle bond adjustment based on personality alignment
            if bond_modifier != 0.0:
                current_bond = current_state.get("bondLevel", 0)
                new_bond = max(0, min(100, current_bond + bond_modifier))

                # Update bond level with personality-based adjustment
                updated_state = current_state.copy()
                updated_state["bondLevel"] = round(new_bond, 2)
                user.emotional_state = updated_state
                await session.commit()

                logger.info(f"[EmotionalAI] Applied personality-based bond adjustment: {bond_modifier} for user {user_id}")

        except Exception as e:
            logger.debug(f"[EmotionalAI] Failed to update personalized bond factors: {e}")

    def _calculate_personality_bond_modifier(self, personality_profile: dict, current_traits: list[str]) -> float:
        """Calculate bond modifier based on personality alignment."""
        try:
            # Get user's preferred traits from personality profile
            preferred_traits = set(personality_profile.get("traits", []))
            current_traits_set = set(current_traits)

            # Calculate overlap
            if not preferred_traits:
                return 0.0

            overlap = len(preferred_traits.intersection(current_traits_set))
            total_preferred = len(preferred_traits)

            if total_preferred == 0:
                return 0.0

            alignment_ratio = overlap / total_preferred

            # Convert to bond modifier: -0.5 to +0.5
            # 0.0 alignment = -0.5 modifier (misalignment)
            # 1.0 alignment = +0.5 modifier (perfect alignment)
            modifier = (alignment_ratio - 0.5) * 2.0 * 0.5  # Scale to ±0.5

            return round(modifier, 3)
        except Exception:
            return 0.0


# ── Singleton ─────────────────────────────────────────────────────────────────
emotional_ai = EmotionalAI()
