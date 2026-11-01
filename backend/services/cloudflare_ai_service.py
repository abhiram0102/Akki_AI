"""
Cloudflare AI Service — Integration for Cloudflare-hosted LLM models.
Connects to user-provided models via Cloudflare URL for personalization and fine-tuning.
"""
import os
import logging
import asyncio
from typing import Any, Optional, AsyncGenerator, List, Union

import httpx

logger = logging.getLogger("akki.cloudflare")

CLOUDFLARE_AI_URL = os.environ.get("CLOUDFLARE_AI_URL", "")


class CloudflareAIService:
    """Async wrapper around Cloudflare-hosted LLM API.

    Provides chat completion and text embedding for user-hosted models.
    Designed to fail gracefully — callers should check ``available``
    before making inference calls.
    """

    def __init__(self) -> None:
        self.url: str = CLOUDFLARE_AI_URL.rstrip("/") if CLOUDFLARE_AI_URL else ""
        self.available: bool = False
        self.models: list[str] = []
        self.model_map: dict[str, str] = {
            "chat": os.environ.get("CLOUDFLARE_CHAT_MODEL", ""),
            "code": os.environ.get("CLOUDFLARE_CODE_MODEL", ""),
            "redteam": os.environ.get("CLOUDFLARE_REDTEAM_MODEL", ""),
            "embed": os.environ.get("CLOUDFLARE_EMBED_MODEL", ""),
        }
        self.client: Optional[httpx.AsyncClient] = None
        self.last_checked: float = 0.0

    def _get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=120.0)
        return self.client

    async def check_availability(self, force: bool = False) -> bool:
        """Probe the Cloudflare AI endpoint to verify it's reachable.

        On success, populates ``self.models`` with available models and
        sets ``self.available = True``.

        Returns:
            ``True`` if the Cloudflare AI service responded, ``False`` otherwise.
        """
        import time
        now = time.time()
        # Cooldown check: if not forced and checked within the last 30 seconds, return current status
        if not force and (now - self.last_checked < 30.0):
            return self.available

        self.last_checked = now

        if not self.url:
            self.available = False
            self.models = []
            logger.warning("[Cloudflare AI] No URL configured")
            return False

        try:
            client = self._get_client()
            # Try to get models list - adjust endpoint based on your Cloudflare setup
            resp = await client.get(f"{self.url}/v1/models", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()

            # Extract model names - adjust based on your API response format
            models = []
            if "data" in data:
                models = [m["id"] for m in data["data"]]
            elif "models" in data:
                models = data["models"]

            self.models = models
            self.available = True
            logger.info(
                "[Cloudflare AI] Connected ✓  models: %s",
                ", ".join(models) if models else "(none)",
            )
        except Exception as exc:
            self.available = False
            self.models = []
            logger.warning(
                "[Cloudflare AI] Unavailable — %s: %s",
                type(exc).__name__,
                exc,
            )

        return self.available

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send a chat-completion request to Cloudflare AI.

        Args:
            messages: Conversation history as a list of
                ``{"role": ..., "content": ...}`` dicts.
            model: Model identifier.  Defaults to the ``chat`` role model.
            temperature: Sampling temperature (0.0 – 2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            The assistant's response text.

        Raises:
            RuntimeError: If Cloudflare AI is not available.
            httpx.HTTPStatusError: On non-2xx responses.
        """
        if not self.available:
            await self.check_availability()
            if not self.available:
                raise RuntimeError(
                    "Cloudflare AI is not available. Check CLOUDFLARE_AI_URL."
                )

        resolved_model = model or self.model_map["chat"]
        if not resolved_model:
            resolved_model = self.models[0] if self.models else ""

        # Prepare messages in OpenAI format (adjust based on your Cloudflare setup)
        formatted_messages = []
        for m in messages:
            role = m.get("role", "user")
            # Map roles if needed - some APIs use different role names
            if role in ["assistant", "model"]:
                role = "assistant"
            elif role not in ["user", "system"]:
                role = "user"

            formatted_messages.append({
                "role": role,
                "content": m.get("content", "")
            })

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": False,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        client = self._get_client()
        resp = await client.post(
            f"{self.url}/v1/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()

        # Extract response - adjust based on your API response format
        content = ""
        if "choices" in body and len(body["choices"]) > 0:
            choice = body["choices"][0]
            if "message" in choice:
                content = choice["message"].get("content", "")
            elif "text" in choice:
                content = choice["text"]

        return content

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Send a streaming chat-completion request to Cloudflare AI."""
        if not self.available:
            await self.check_availability()
            if not self.available:
                raise RuntimeError(
                    "Cloudflare AI is not available. Check CLOUDFLARE_AI_URL."
                )

        resolved_model = model or self.model_map["chat"]
        if not resolved_model:
            resolved_model = self.models[0] if self.models else ""

        formatted_messages = []
        for m in messages:
            role = m.get("role", "user")
            if role in ["assistant", "model"]:
                role = "assistant"
            elif role not in ["user", "system"]:
                role = "user"

            formatted_messages.append({
                "role": role,
                "content": m.get("content", "")
            })

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }

        client = self._get_client()
        async with client.stream(
            "POST",
            f"{self.url}/v1/chat/completions",
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                err_body = await resp.aread()
                logger.error("[Cloudflare AI] Stream error status: %d, body: %s",
                           resp.status_code, err_body.decode(errors='ignore'))
                resp.raise_for_status()

            async for line in resp.aiter_lines():
                if line:
                    try:
                        # Parse SSE format or JSON lines - adjust based on your API
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            if data.strip() == "[DONE]":
                                break
                        else:
                            data = line

                        body = json.loads(data)
                        # Extract chunk based on your API format
                        chunk = ""
                        if "choices" in body and len(body["choices"]) > 0:
                            delta = body["choices"][0].get("delta", {})
                            chunk = delta.get("content", "")
                            if not chunk:  # Fallback for different format
                                chunk = body["choices"][0].get("text", "")
                        if chunk:
                            yield chunk
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
                    except Exception as e:
                        logger.warning("[Cloudflare AI] Error parsing stream line: %s", e)
                        continue

    async def embed(
        self,
        text: str | list[str],
        *,
        model: str | None = None,
    ) -> list[float] | list[list[float]] | None:
        """Generate an embedding vector for *text* using Cloudflare AI.

        Args:
            text: The input string or list of strings to embed.
            model: Override the embedding model tag.

        Returns:
            A list of floats (or list of lists), or None if unavailable.
        """
        if not self.available:
            await self.check_availability()
            if not self.available:
                return None

        resolved_model = model or self.model_map["embed"]
        if not resolved_model and self.models:
            # Find first non-chat model or use first available
            for m in self.models:
                if "embed" in m.lower() or m not in [self.model_map.get("chat", ""),
                                                   self.model_map.get("code", ""),
                                                   self.model_map.get("redteam", "")]:
                    resolved_model = m
                    break
            if not resolved_model:
                resolved_model = self.models[0]

        # Prepare input for embedding API
        if isinstance(text, str):
            input_text = [text]
        else:
            input_text = text

        payload: dict[str, Any] = {
            "model": resolved_model,
            "input": input_text,
            "encoding_format": "float",
        }

        client = self._get_client()
        try:
            resp = await client.post(
                f"{self.url}/v1/embeddings",
                json=payload,
                timeout=30.0,
            )
            resp.raise_for_status()
            body = resp.json()

            embeddings = []
            if "data" in body:
                # Sort by index to maintain order
                for item in sorted(body["data"], key=lambda x: x.get("index", 0)):
                    embeddings.append(item["embedding"])
            elif "embeddings" in body:
                embeddings = body["embeddings"]

            if embeddings:
                if isinstance(text, str) and len(embeddings) == 1:
                    return embeddings[0]
                return embeddings

            logger.warning("[Cloudflare AI] Embed response contained no vectors")
            return None

        except Exception as exc:
            logger.warning(
                "[Cloudflare AI] Embedding failed — %s: %s",
                type(exc).__name__,
                exc,
            )
            return None

# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
cloudflare_ai = CloudflareAIService()