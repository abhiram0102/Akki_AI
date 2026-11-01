"""
Langfuse tracing wrapper with zero-overhead no-op mode.

Ported from server/services/langfuse.ts (130 lines).
When ``LANGFUSE_PUBLIC_KEY`` **and** ``LANGFUSE_SECRET_KEY`` are present
in the environment, traces are forwarded to Langfuse.  Otherwise every
method returns lightweight no-op stubs so the rest of the pipeline can
call tracing helpers without guards or conditionals.

Never crashes the pipeline — every public method is wrapped in a
silent try/except.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger("akki.langfuse")


# =====================================================================
# Abstract interfaces
# =====================================================================


@runtime_checkable
class SpanHandle(Protocol):
    """Minimal interface for a tracing span."""

    def end(self, output: Any = None) -> None:
        """Mark the span as finished, optionally attaching *output*."""
        ...


@runtime_checkable
class TraceHandle(Protocol):
    """Minimal interface for a top-level trace."""

    id: str

    def span(self, name: str, input: Any = None) -> SpanHandle:
        """Create a child span inside this trace."""
        ...

    def end(self, output: Any = None) -> None:
        """Mark the trace as finished, optionally attaching *output*."""
        ...


# =====================================================================
# No-op implementations (zero overhead when Langfuse is disabled)
# =====================================================================


class NoopSpan:
    """A span that does absolutely nothing."""

    def end(self, output: Any = None) -> None:  # noqa: D401
        pass

    def __repr__(self) -> str:
        return "NoopSpan()"


class NoopTrace:
    """A trace that does absolutely nothing."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.id: str = trace_id or uuid.uuid4().hex

    def span(self, name: str, input: Any = None) -> NoopSpan:
        return NoopSpan()

    def end(self, output: Any = None) -> None:
        pass

    def __repr__(self) -> str:
        return f"NoopTrace(id={self.id!r})"


# =====================================================================
# Real Langfuse wrappers (only used when the SDK is available + keyed)
# =====================================================================


class _LangfuseSpan:
    """Thin wrapper around a real ``langfuse`` span object."""

    def __init__(self, raw_span: Any) -> None:
        self._raw = raw_span

    def end(self, output: Any = None) -> None:
        try:
            if output is not None:
                self._raw.end(output=output)
            else:
                self._raw.end()
        except Exception as exc:
            logger.debug("[Langfuse] span.end() failed: %s", exc)


class _LangfuseTrace:
    """Thin wrapper around a real ``langfuse`` trace object."""

    def __init__(self, raw_trace: Any) -> None:
        self._raw = raw_trace
        self.id: str = getattr(raw_trace, "id", uuid.uuid4().hex)

    def span(self, name: str, input: Any = None) -> _LangfuseSpan | NoopSpan:
        try:
            kwargs: dict[str, Any] = {"name": name}
            if input is not None:
                kwargs["input"] = input
            raw_span = self._raw.span(**kwargs)
            return _LangfuseSpan(raw_span)
        except Exception as exc:
            logger.debug("[Langfuse] trace.span() failed: %s", exc)
            return NoopSpan()

    def end(self, output: Any = None) -> None:
        try:
            if output is not None:
                self._raw.update(output=output)
            # Langfuse traces don't have an explicit end(); update suffices.
        except Exception as exc:
            logger.debug("[Langfuse] trace.end() failed: %s", exc)


# =====================================================================
# Main tracer class
# =====================================================================


class CRAGTracer:
    """Langfuse tracing façade.

    * When both ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY``
      environment variables are set **and** the ``langfuse`` package is
      importable, real traces are created.
    * Otherwise every call is a silent no-op — zero overhead, zero risk.

    Usage::

        from backend.services.langfuse_service import tracer

        trace = tracer.start_trace("my-pipeline", input={"query": q})
        span  = trace.span("retrieval", input=q)
        # … do work …
        span.end(output=docs)
        trace.end(output=answer)
        await tracer.flush()
    """

    def __init__(self) -> None:
        self._enabled: bool = False
        self._lf: Any = None
        self._initialized: bool = False

    def _ensure_init(self) -> None:
        """Lazy-initialize the Langfuse client on first use."""
        if self._initialized:
            return
        self._initialized = True

        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

        if not public_key or not secret_key:
            logger.info(
                "[Langfuse] LANGFUSE_PUBLIC_KEY not set — "
                "tracing disabled (no-op mode)"
            )
            return

        try:
            from langfuse import Langfuse  # type: ignore[import-untyped]

            host = os.environ.get("LANGFUSE_HOST", None)
            init_kwargs: dict[str, Any] = {
                "public_key": public_key,
                "secret_key": secret_key,
            }
            if host:
                init_kwargs["host"] = host

            self._lf = Langfuse(**init_kwargs)
            self._enabled = True
            logger.info("[Langfuse] Tracing enabled")

        except ImportError:
            logger.warning(
                "[Langfuse] 'langfuse' package not installed — "
                "tracing disabled (no-op mode)"
            )
        except Exception as exc:
            logger.warning(
                "[Langfuse] Initialization failed — %s: %s  "
                "(tracing disabled)",
                type(exc).__name__,
                exc,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Whether real Langfuse tracing is active."""
        self._ensure_init()
        return self._enabled

    @property
    def is_enabled(self) -> bool:
        """Alias kept for parity with the TypeScript export."""
        self._ensure_init()
        return self._enabled

    def start_trace(
        self,
        name: str,
        *,
        input: Any = None,
    ) -> _LangfuseTrace | NoopTrace:
        """Begin a new top-level trace.

        Args:
            name: Human-readable name for the trace
                  (e.g. ``"crag-pipeline"``).
            input: Optional input payload to attach.

        Returns:
            A :class:`TraceHandle` — either a real Langfuse trace or a
            no-op stub.
        """
        self._ensure_init()
        if not self._enabled or self._lf is None:
            return NoopTrace(uuid.uuid4().hex)

        try:
            kwargs: dict[str, Any] = {"name": name}
            if input is not None:
                kwargs["input"] = input
            raw_trace = self._lf.trace(**kwargs)
            return _LangfuseTrace(raw_trace)
        except Exception as exc:
            logger.debug("[Langfuse] start_trace() failed: %s", exc)
            return NoopTrace(uuid.uuid4().hex)

    async def flush(self) -> None:
        """Flush any buffered traces to the Langfuse backend.

        Safe to call even when tracing is disabled — returns immediately.
        Runs the blocking ``self._lf.flush()`` in a thread-pool executor
        so it never blocks the event loop.
        """
        self._ensure_init()
        if not self._enabled or self._lf is None:
            return

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._lf.flush)
        except Exception as exc:
            # Swallow silently — tracing must never break the pipeline.
            logger.debug("[Langfuse] flush() failed: %s", exc)

    # Alias for TS parity (``flushAsync``).
    flush_async = flush


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
tracer = CRAGTracer()
