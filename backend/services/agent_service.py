import json
from backend.services.ai_service import ai_service


class AgentService:
    async def process_message(self, message: str, session_id: str, user_id: str,
                               voice_input: bool = False, context: dict = None) -> dict:
        try:
            response_text = await ai_service.process_cybersecurity_message(message, context)
            return {
                "content": response_text,
                "toolCalls": [],
                "ragUsed": False,
                "sources": [],
                "emotionalTone": "professional",
                "plan": None,
            }
        except Exception as e:
            return {
                "content": f"I encountered an issue processing your request. Please try again.\n\nError details: {str(e)[:200]}",
                "toolCalls": [],
                "ragUsed": False,
                "sources": [],
                "emotionalTone": "neutral",
                "plan": None,
            }


agent_service = AgentService()
