"""
Personalization Service — Manages user personalization preferences and
parameter-efficient fine-tuning for customized AI behavior within ethical boundaries.
Enhanced with learning capabilities to improve personalization over time.
"""
import logging
from typing import Any, Dict, Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import User
from backend.database import get_db

logger = logging.getLogger("akki.personalization")


class PersonalizationService:
    """Service for managing user personalization preferences with learning capabilities."""

    # Default personalization preferences
    DEFAULT_PREFS = {
        # Communication style
        "communicationStyle": "professional",  # professional, casual, technical, friendly
        "responseLength": "medium",  # short, medium, long
        "detailLevel": "medium",  # low, medium, high
        "technicalDepth": "medium",  # low, medium, high

        # Expertise domains
        "expertiseAreas": [],  # e.g., ["cybersecurity", "machine_learning", "networking"]
        "preferredTopics": [],  # Topics user wants emphasis on

        # Safety and behavior (with minimum thresholds for safety)
        "safetySensitivity": "medium",  # low, medium, high (cannot go below medium)
        "creativityLevel": "medium",  # low, medium, high
        "formalityLevel": "medium",  # low, medium, high

        # Learning preferences
        "learningStyle": "reading",  # visual, auditory, reading, kinesthetic
        "explanationDepth": "medium",  # low, medium, high

        # Personalization status
        "personalizationEnabled": True,
        "trainedModelId": None,  # ID of fine-tuned model if applicable
        "lastUpdated": None,
    }

    def __init__(self):
        pass

    async def get_personalization_preferences(
        self, user_id: str, db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get personalization preferences for a user.

        Args:
            user_id: The user's ID
            db: Database session

        Returns:
            Dictionary of personalization preferences
        """
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"User {user_id} not found")
                return self.DEFAULT_PREFS.copy()

            # Get existing preferences or use defaults
            existing_prefs = user.preferences or {}

            # Merge with defaults to ensure all keys exist
            prefs = self.DEFAULT_PREFS.copy()
            prefs.update(existing_prefs)

            # Apply safety constraints (ensure safety isn't reduced below minimum)
            prefs["safetySensitivity"] = max(
                prefs["safetySensitivity"], "medium"
            ) if isinstance(prefs["safetySensitivity"], str) else "medium"

            return prefs

        except Exception as e:
            logger.error(f"Error getting personalization preferences for user {user_id}: {e}")
            return self.DEFAULT_PREFS.copy()

    async def update_personalization_preferences(
        self, user_id: str, preferences: Dict[str, Any], db: AsyncSession
    ) -> bool:
        """
        Update personalization preferences for a user.

        Args:
            user_id: The user's ID
            preferences: Dictionary of preferences to update
            db: Database session

        Returns:
            True if successful, False otherwise
        """
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"User {user_id} not found")
                return False

            # Get existing preferences
            existing_prefs = user.preferences or {}

            # Update with new preferences
            updated_prefs = existing_prefs.copy()
            updated_prefs.update(preferences)

            # Apply safety constraints
            if "safetySensitivity" in updated_prefs:
                # Ensure safety sensitivity doesn't go below medium
                safety_levels = {"low": 0, "medium": 1, "high": 2}
                current_level = safety_levels.get(
                    updated_prefs["safetySensitivity"], 1
                )
                min_level = safety_levels["medium"]
                if current_level < min_level:
                    updated_prefs["safetySensitivity"] = "medium"

            # Update timestamp
            updated_prefs["lastUpdated"] = (
                logger.handlers[0].formatter.formatTime(
                    logger.handlers[0].formatter, None
                ) if logger.handlers else None
            )

            # Save to database
            user.preferences = updated_prefs
            await db.commit()

            logger.info(f"Updated personalization preferences for user {user_id}")
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating personalization preferences for user {user_id}: {e}")
            return False

    def get_system_prompt_modifications(
        self, preferences: Dict[str, Any]
    ) -> str:
        """
        Generate system prompt modifications based on personalization preferences.

        Args:
            preferences: User's personalization preferences

        Returns:
            String containing modifications to append to system prompt
        """
        if not preferences.get("personalizationEnabled", True):
            return ""

        modifications = []

        # Communication style
        style = preferences.get("communicationStyle", "professional")
        if style == "casual":
            modifications.append("Use a casual and friendly tone in your responses.")
        elif style == "technical":
            modifications.append("Use technical terminology and precise language appropriate for technical audiences.")
        elif style == "friendly":
            modifications.append("Be warm, approachable, and friendly in your communication.")
        # professional is default, so no modification needed

        # Response length
        length = preferences.get("responseLength", "medium")
        if length == "short":
            modifications.append("Keep responses concise and to the point.")
        elif length == "long":
            modifications.append("Provide detailed, comprehensive responses with thorough explanations.")
        # medium is default

        # Detail level
        detail = preferences.get("detailLevel", "medium")
        if detail == "low":
            modifications.append("Focus on key points and avoid excessive detail unless specifically asked.")
        elif detail == "high":
            modifications.append("Include comprehensive details, examples, and background information.")
        # medium is default

        # Technical depth
        tech_depth = preferences.get("technicalDepth", "medium")
        if tech_depth == "low":
            modifications.append("Explain concepts in simple terms, avoiding jargon unless necessary.")
        elif tech_depth == "high":
            modifications.append("Assume technical familiarity and use appropriate technical depth.")
        # medium is default

        # Expertise areas
        expertise_areas = preferences.get("expertiseAreas", [])
        if expertise_areas:
            areas_str = ", ".join(expertise_areas)
            modifications.append(f"Show particular expertise and interest in: {areas_str}.")

        # Preferred topics
        preferred_topics = preferences.get("preferredTopics", [])
        if preferred_topics:
            topics_str = ", ".join(preferred_topics)
            modifications.append(f"When relevant, emphasize topics related to: {topics_str}.")

        # Creativity level
        creativity = preferences.get("creativityLevel", "medium")
        if creativity == "low":
            modifications.append("Focus on factual, conservative responses with minimal speculation.")
        elif creativity == "high":
            modifications.append("Feel free to explore creative approaches and innovative ideas.")
        # medium is default

        # Formality level
        formality = preferences.get("formalityLevel", "medium")
        if formality == "low":
            modifications.append("Use informal language and relax formality constraints appropriately.")
        elif formality == "high":
            modifications.append("Maintain formal, professional language throughout interactions.")
        # medium is default

        # Learning style
        learning_style = preferences.get("learningStyle", "reading")
        if learning_style == "visual":
            modifications.append("When explaining concepts, prefer visual descriptions and spatial reasoning.")
        elif learning_style == "auditory":
            modifications.append("Structure explanations for auditory learning, with clear verbal patterns.")
        elif learning_style == "kinesthetic":
            modifications.append("Include practical, hands-on examples and applications.")
        # reading is default

        # Explanation depth
        explanation_depth = preferences.get("explanationDepth", "medium")
        if explanation_depth == "low":
            modifications.append("Provide high-level explanations unless deeper detail is requested.")
        elif explanation_depth == "high":
            modifications.append("Offer deep, thorough explanations with foundational context.")
        # medium is default

        return " ".join(modifications)

    async def is_personalization_enabled(self, user_id: str, db: AsyncSession) -> bool:
        """
        Check if personalization is enabled for a user.

        Args:
            user_id: The user's ID
            db: Database session

        Returns:
            True if personalization is enabled
        """
        prefs = await self.get_personalization_preferences(user_id, db)
        return prefs.get("personalizationEnabled", True)

    # === LEARNING CAPABILITIES ===

    async def record_interaction_feedback(
        self, user_id: str, interaction_data: Dict[str, Any], db: AsyncSession
    ) -> bool:
        """
        Record feedback from a user interaction to improve personalization.

        Args:
            user_id: The user's ID
            interaction_data: Data about the interaction (rating, topic, etc.)
            db: Database session

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract feedback data
            rating = interaction_data.get("rating", 0)  # 1-5 scale
            topic = interaction_data.get("topic", "")
            agent_used = interaction_data.get("agent", "")
            feedback_text = interaction_data.get("feedback", "")

            # Only process if we have meaningful feedback
            if rating == 0 and not feedback_text:
                return False

            # Get current preferences
            current_prefs = await self.get_personalization_preferences(user_id, db)

            # Learn from the interaction
            updated_prefs = await self._learn_from_interaction(
                current_prefs, interaction_data
            )

            # Apply the learned preferences if they differ significantly
            if self._prefs_have_changed_significantly(current_prefs, updated_prefs):
                await self.update_personalization_preferences(
                    user_id, updated_prefs, db
                )
                logger.info(f"Applied learned personalization updates for user {user_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error recording interaction feedback for user {user_id}: {e}")
            return False

    async def _learn_from_interaction(
        self, current_prefs: Dict[str, Any], interaction_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Learn from an interaction and adjust preferences accordingly.
        Uses a simple reinforcement learning approach.

        Args:
            current_prefs: Current user preferences
            interaction_data: Data about the interaction

        Returns:
            Updated preferences based on learning
        """
        # Start with current preferences
        updated_prefs = current_prefs.copy()

        # Extract feedback signal
        rating = interaction_data.get("rating", 3)  # Default to neutral (3/5)
        feedback_text = interaction_data.get("feedback", "").lower()

        # Convert rating to a feedback signal (-1 to 1 scale)
        # 1-2 = negative (-1 to -0.5), 3 = neutral (0), 4-5 = positive (0.5 to 1)
        if rating <= 2:
            feedback_signal = -1.0 + (rating - 1) * 0.5  # -1.0 to -0.5
        elif rating >= 4:
            feedback_signal = (rating - 3) * 0.5  # 0.5 to 1.0
        else:
            feedback_signal = 0.0  # Neutral

        # Also consider explicit feedback text for sentiment
        if feedback_text:
            # Simple sentiment analysis (could be enhanced with NLP)
            positive_words = ["good", "great", "excellent", "helpful", "accurate", "useful"]
            negative_words = ["bad", "wrong", "unhelpful", "inaccurate", "confusing"]

            pos_count = sum(1 for word in positive_words if word in feedback_text)
            neg_count = sum(1 for word in negative_words if word in feedback_text)

            if pos_count > neg_count:
                feedback_signal = max(feedback_signal, 0.5)
            elif neg_count > pos_count:
                feedback_signal = min(feedback_signal, -0.5)

        # Learning rate (how much to adjust preferences based on feedback)
        learning_rate = 0.1

        # Adjust preferences based on feedback signal and interaction context
        topic = interaction_data.get("topic", "").lower()
        agent_used = interaction_data.get("agent", "")

        # If feedback is positive, reinforce current preferences for this context
        if feedback_signal > 0:
            # Slightly increase confidence in current preferences
            # In a more sophisticated system, we might adjust specific parameters
            pass  # For now, we keep current preferences as they worked well

        # If feedback is negative, adjust preferences away from what didn't work
        elif feedback_signal < 0:
            # Adjust based on what we know about the interaction
            if topic:
                # If user didn't like a topic, might want less emphasis on it
                preferred_topics = updated_prefs.get("preferredTopics", [])
                if topic not in preferred_topics and feedback_signal < -0.5:
                    # Only add to avoided topics if strongly negative
                    pass  # Could implement avoided topics list

            if agent_used:
                # If user didn't like a particular agent, might adjust related preferences
                # For example, if they didn't like the technical agent, reduce technical depth
                if agent_used in ["exploit", "recon", "malware"] and feedback_signal < -0.5:
                    # User might prefer less technical depth for offensive security topics
                    current_depth = updated_prefs.get("technicalDepth", "medium")
                    depth_levels = ["low", "medium", "high"]
                    try:
                        current_index = depth_levels.index(current_depth)
                        if current_index > 0:  # Not already at minimum
                            updated_prefs["technicalDepth"] = depth_levels[current_index - 1]
                    except ValueError:
                        pass  # Keep current if not found

        # Ensure we don't violate safety constraints
        if "safetySensitivity" in updated_prefs:
            safety_levels = {"low": 0, "medium": 1, "high": 2}
            current_level = safety_levels.get(
                updated_prefs["safetySensitivity"], 1
            )
            min_level = safety_levels["medium"]
            if current_level < min_level:
                updated_prefs["safetySensitivity"] = "medium"

        return updated_prefs

    def _prefs_have_changed_significantly(
        self, prefs1: Dict[str, Any], prefs2: Dict[str, Any], threshold: float = 0.3
    ) -> bool:
        """
        Check if preferences have changed enough to warrant an update.

        Args:
            prefs1: First set of preferences
            prefs2: Second set of preferences
            threshold: Minimum change ratio to consider significant

        Returns:
            True if preferences have changed significantly
        """
        # For simplicity, we'll consider it significant if any categorical preference changed
        # or if any numeric preference changed by more than threshold

        # Compare key preference categories
        key_prefs = [
            "communicationStyle", "responseLength", "detailLevel",
            "technicalDepth", "learningStyle", "explanationDepth",
            "creativityLevel", "formalityLevel", "safetySensitivity"
        ]

        for key in key_prefs:
            val1 = prefs1.get(key)
            val2 = prefs2.get(key)
            if val1 != val2:
                return True

        # Check expertise areas and preferred topics (as sets)
        exp1 = set(prefs1.get("expertiseAreas", []))
        exp2 = set(prefs2.get("expertiseAreas", []))
        if exp1 != exp2:
            return True

        top1 = set(prefs1.get("preferredTopics", []))
        top2 = set(prefs2.get("preferredTopics", []))
        if top1 != top2:
            return True

        return False


# Module-level singleton
personalization_service = PersonalizationService()