"""
Ollama integration for local LLM inference and embeddings.

Ported from server/services/ollama.ts (136 lines).
Connects to Ollama at OLLAMA_HOST (default http://localhost:11434).
Provides chat completion, embedding generation, model listing,
and role-based model selection (chat, code, redteam, embed).
"""

import os
import logging
import asyncio
from typing import Any, Optional, AsyncGenerator

import httpx

logger = logging.getLogger("akki.ollama")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", os.environ.get("OLLAMA_URL", "http://localhost:11434"))


class OllamaService:
    """Async wrapper around the Ollama REST API.

    Provides chat completion, text embedding, model enumeration,
    and role-based model mapping.  Designed to fail gracefully —
    callers should check ``available`` or catch ``RuntimeError``
    before making inference calls.
    """

    def __init__(self) -> None:
        self.host: str = OLLAMA_HOST.rstrip("/")
        self.available: bool = False
        self.models: list[str] = []
        self.model_map: dict[str, str] = {
            "chat": os.environ.get("OLLAMA_CHAT_MODEL", "llama3.2:latest"),
            "code": os.environ.get("OLLAMA_CODE_MODEL", os.environ.get("OLLAMA_CHAT_MODEL", "codellama:latest")),
            "redteam": os.environ.get("OLLAMA_REDTEAM_MODEL", os.environ.get("OLLAMA_CHAT_MODEL", "mistral:latest")),
            "embed": os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest"),
        }
        self.client: Optional[httpx.AsyncClient] = None
        self.last_checked: float = 0.0

    def _get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            # 8s total: enough for short completions, fails fast for slow models
            self.client = httpx.AsyncClient(timeout=60.0)
        return self.client

    def _resolve_model_fallback(self, model: str) -> str:
        if not self.models:
            return model
        
        # If the exact model name is in self.models, use it.
        if model in self.models:
            return model
            
        # Try appending ':latest' if not present
        if ":" not in model and f"{model}:latest" in self.models:
            return f"{model}:latest"
            
        # Try stripping ':latest' if present
        if model.endswith(":latest") and model[:-7] in self.models:
            return model[:-7]
            
        # If model is not found, try to find a reasonable fallback in self.models
        # Preferred order of fallback models: llama3.2, qwen, mistral, codellama, any model
        for candidate in ["llama3.2", "qwen", "mistral", "codellama"]:
            for m in self.models:
                if candidate in m.lower():
                    return m
                    
        # Just return the first available model that is not an embedding model
        for m in self.models:
            if "embed" not in m.lower():
                return m
                
        return model

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    async def check_availability(self, force: bool = False) -> bool:
        """Probe the ``/api/tags`` endpoint to verify Ollama is reachable.

        On success, populates ``self.models`` with the names of all
        locally-pulled models and sets ``self.available = True``.

        Returns:
            ``True`` if the Ollama server responded, ``False`` otherwise.
        """
        import time
        now = time.time()
        # Cooldown check: if not forced and checked within the last 15 seconds, return current status
        if not force and (now - self.last_checked < 15.0):
            return self.available

        self.last_checked = now
        try:
            client = self._get_client()
            resp = await client.get(f"{self.host}/api/tags", timeout=1.0)
            resp.raise_for_status()
            data = resp.json()

            models: list[str] = [
                m["name"] for m in data.get("models", [])
            ]
            self.models = models
            self.available = True
            logger.info(
                "[Ollama] Connected ✓  models: %s",
                ", ".join(models) if models else "(none)",
            )
        except Exception as exc:
            self.available = False
            self.models = []
            logger.warning(
                "[Ollama] Unavailable — %s: %s",
                type(exc).__name__,
                exc,
            )

        return self.available

    # ------------------------------------------------------------------
    # Chat completion
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
        num_predict: int | None = None,
    ) -> str:
        """Send a chat-completion request to Ollama.

        Args:
            messages: Conversation history as a list of
                ``{"role": ..., "content": ...}`` dicts.
            model: Ollama model tag.  Defaults to the ``chat`` role model.
            temperature: Sampling temperature (0.0 – 2.0).
            stream: Reserved for future streaming support.  Currently
                forced to ``False``.

        Returns:
            The assistant's response text.

        Raises:
            RuntimeError: If Ollama is not available.
            httpx.HTTPStatusError: On non-2xx responses.
        """
        if not self.available:
            await self.check_availability()
            if not self.available:
                raise RuntimeError(
                    "Ollama is not available. Call check_availability() first."
                )

        resolved_model = model or self.model_map["chat"]
        resolved_model = self._resolve_model_fallback(resolved_model)

        options: dict[str, Any] = {"temperature": temperature, "num_ctx": 2048}
        if num_predict is not None:
            options["num_predict"] = num_predict
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
            "options": options,
        }

        client = self._get_client()
        resp = await client.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        body = resp.json()

        content: str = body.get("message", {}).get("content", "")
        return content

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        num_predict: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Send a streaming chat-completion request to Ollama."""
        if not self.available:
            await self.check_availability()
            if not self.available:
                raise RuntimeError(
                    "Ollama is not available. Call check_availability() first."
                )

        resolved_model = model or self.model_map["chat"]
        resolved_model = self._resolve_model_fallback(resolved_model)

        options: dict[str, Any] = {"temperature": temperature, "num_ctx": 2048}
        if num_predict is not None:
            options["num_predict"] = num_predict
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            "options": options,
        }

        logger.debug("[Ollama] Streaming request to /api/chat payload: %s", payload)

        client = self._get_client()
        async with client.stream(
            "POST",
            f"{self.host}/api/chat",
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                err_body = await resp.aread()
                logger.error("[Ollama] /api/chat stream error status: %d, body: %s, payload: %s", resp.status_code, err_body.decode(errors='ignore'), payload)
                resp.raise_for_status()

            import json
            async for line in resp.aiter_lines():
                if line:
                    body = json.loads(line)
                    chunk = body.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def embed(
        self,
        text: str | list[str],
        *,
        model: str | None = None,
    ) -> list[float] | list[list[float]] | None:
        """Generate an embedding vector for *text* (or a list of vectors for a list of strings).

        Uses ``nomic-embed-text`` (768-dimensional) by default.

        Args:
            text: The input string or list of strings to embed.
            model: Override the embedding model tag.

        Returns:
            A list of 768 floats (or a list of lists of floats), or ``None`` if Ollama is unavailable
            or an error occurs.
        """
        if not self.available:
            await self.check_availability()
            if not self.available:
                return None

        resolved_model = model or self.model_map["embed"]

        if self.models and resolved_model not in self.models:
            if ":" not in resolved_model and f"{resolved_model}:latest" in self.models:
                resolved_model = f"{resolved_model}:latest"
            elif resolved_model.endswith(":latest") and resolved_model[:-7] in self.models:
                resolved_model = resolved_model[:-7]
            else:
                for m in self.models:
                    if "embed" in m.lower():
                        resolved_model = m
                        break

        try:
            client = self._get_client()
            resp = await client.post(
                f"{self.host}/api/embed",
                json={
                    "model": resolved_model,
                    "input": text,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            body = resp.json()

            embeddings = body.get("embeddings", [])
            if embeddings:
                if isinstance(text, list):
                    return embeddings
                return embeddings[0]

            logger.warning("[Ollama] Embed response contained no vectors")
            return None

        except Exception as exc:
            logger.warning(
                "[Ollama] Embedding failed — %s: %s",
                type(exc).__name__,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    async def list_models(self) -> list[dict[str, Any]]:
        """Return detailed info for every locally-pulled model.

        Returns:
            A list of model-info dicts as returned by Ollama's
            ``/api/tags`` endpoint (keys typically include ``name``,
            ``modified_at``, ``size``, ``digest``, ``details``).
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.host}/api/tags")
                resp.raise_for_status()
                data = resp.json()

            return data.get("models", [])

        except Exception as exc:
            logger.warning(
                "[Ollama] list_models failed — %s: %s",
                type(exc).__name__,
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Role → model resolution
    # ------------------------------------------------------------------

    def get_model(self, role: str) -> str:
        """Resolve a logical *role* to a concrete Ollama model tag.

        Known roles: ``chat``, ``code``, ``redteam``, ``embed``.
        Unknown roles fall back to the ``chat`` model.

        Args:
            role: Logical role name.

        Returns:
            The Ollama model tag string.
        """
        return self.model_map.get(role, self.model_map["chat"])


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
ollama_service = OllamaService()
