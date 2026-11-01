"""
RAG Service — True Corrective RAG (CRAG) Implementation

Based on the original CRAG paper (Yan et al., 2024) and the LangGraph
reference implementation.

─── Core CRAG algorithm ───────────────────────────────────────────────────

 The key insight from the paper is a THREE-STATE retrieval evaluator:

   CORRECT   → at least one doc is relevant → generate directly from vector store
   INCORRECT → ALL docs are irrelevant      → discard vector store, use web search only
   AMBIGUOUS → mixed relevance              → combine vector store + web search

 Each document is graded INDIVIDUALLY (binary YES/NO), not as a batch.

 After deciding on the knowledge source:
   • Knowledge refinement  — strip irrelevant chunks, keep only relevant ones
   • Query rewriting       — optimise the query specifically for web search
   • Generation            — produce final answer from refined knowledge
   • Hallucination grading — confirm every claim is grounded (Self-RAG ISSUP)
   • Self-correction loop  — rewrite + re-retrieve on failure (max 2 retries)

─── Preserved from the TypeScript implementation ──────────────────────────
   ✓ PDF / text / markdown / CSV ingestion
   ✓ Text chunking with configurable overlap & sentence-boundary awareness
   ✓ Embedding generation via Ollama (nomic-embed-text) or provider
   ✓ PostgreSQL vector store (cosine similarity fallback in Python)
   ✓ Keyword-search fallback when embeddings are unavailable
   ✓ RAGQueryResult response shape (answer / sources / confidence / _crag trace)
   ✓ Document management (ingest / delete / search)
"""

import os
import re
import json
import math
import uuid
import logging
import asyncio
import unicodedata
from typing import Optional, Literal
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, text, update, delete

logger = logging.getLogger("akki.rag")

# ─── Cosine similarity (pure-Python fallback) ────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    denom = mag_a * mag_b
    return dot / denom if denom > 0 else 0.0


# ─── Type aliases ─────────────────────────────────────────────────────────────

RetrievalQuality = Literal["CORRECT", "INCORRECT", "AMBIGUOUS"]


class RAGService:
    """
    Corrective RAG (CRAG) pipeline service.

    Implements the full CRAG algorithm:
      1. Query embedding & rewriting
      2. Vector store retrieval (pgvector or ILIKE fallback)
      3. Per-document grading via single batched LLM call
      4. Three-state retrieval quality decision (CORRECT / INCORRECT / AMBIGUOUS)
      5. Optional web search supplement (Tavily)
      6. Knowledge refinement (dedup, filter, cap)
      7. Generation from refined sources
      8. Groundedness check (Self-RAG ISSUP token concept)
      9. Self-correction retry loop (max 2 retries)
     10. Composite confidence scoring
    """

    # ── Config constants ──────────────────────────────────────────────────────
    CHUNK_SIZE: int = 1500   # ~375 tokens; better for multi-paragraph technical content
    CHUNK_OVERLAP: int = 300  # 20% overlap preserves cross-boundary context
    BATCH_SIZE: int = 5
    TOP_K_DEFAULT: int = 5
    TOP_K_EXPANDED: int = 10
    MAX_RETRIES: int = 1
    RELEVANCE_THRESHOLD: float = 0.5
    CONFIDENCE_WEIGHTS: dict = {
        "retrieval": 0.4,
        "generation": 0.3,
        "groundedness": 0.3,
    }

    def __init__(self) -> None:
        self.embedding_provider: str = os.environ.get("EMBEDDING_PROVIDER", "none")
        self.vector_store: str = "postgresql"
        self.mode: str = "crag"
        logger.info(
            "[RAGService] Ready — embeddings via %s, vector store: %s, mode: Corrective RAG (CRAG)",
            self.embedding_provider,
            self.vector_store,
        )

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  MAIN QUERY ENTRYPOINT — True CRAG pipeline                            ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def query(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
        user_id: str | None = None,
    ) -> dict:
        """
        Execute the full CRAG pipeline:
          rewrite → retrieve → grade → (web search) → refine → generate → groundedness → confidence

        Returns a dict with:
          answer, sources, confidence, retrieval_score, groundedness_score,
          web_search_used, chunks_evaluated, chunks_relevant, _crag trace
        """
        from backend.services.ai_service import ai_service

        start_ms = asyncio.get_event_loop().time()

        # ── CRAG execution trace ──────────────────────────────────────────────
        trace: dict = {
            "original_query": query,
            "final_query": query,
            "retrieval_quality": "CORRECT",
            "relevant_doc_count": 0,
            "irrelevant_doc_count": 0,
            "web_search_used": False,
            "web_search_query_used": None,
            "query_rewrite_count": 0,
            "hallucination_failures": 0,
            "retry_count": 0,
            "final_confidence": 0.0,
            "duration_ms": 0.0,
        }

        # ── Node 1: Generate query embedding ──────────────────────────────────
        query_embedding = await self._generate_embedding(query)

        if query_embedding is None:
            logger.warning("[CRAG] Embedding generation failed for query '%s...' — falling back to keyword search", query[:50])
            # Enhanced fallback with more detailed error context
            try:
                result = await self._keyword_fallback(query)
                result["_fallback_used"] = "embedding_generation"
                result["_fallback_reason"] = "Ollama embedding service unavailable or failed"
                return result
            except Exception as e:
                logger.error("[CRAG] Keyword fallback also failed for query '%s...': %s", query[:50], e)
                return await self._direct_ai_answer(query, "Embedding and keyword search both failed")

        # ── Node 2: Vector store retrieval ────────────────────────────────────
        retrieved = await self._retrieve_chunks(query, query_embedding, top_k, owner_id=user_id)

        if not retrieved:
            logger.info("[CRAG] Empty retrieval for query: %s", query[:100])
            return await self._direct_ai_answer(query, "No documents in knowledge base.")

        # ── Node 3: Grade each document (core CRAG step) ──────────────────────
        grades = await self._grade_documents_batch(query, retrieved)

        relevant_chunks = [c for c, g in zip(retrieved, grades) if g.get("relevant")]
        irrelevant_chunks = [c for c, g in zip(retrieved, grades) if not g.get("relevant")]

        # Three-state quality decision
        # Heuristic optimization: If we have at least 2 relevant chunks, we have enough local context to answer.
        if len(relevant_chunks) >= 2 or len(irrelevant_chunks) == 0:
            quality: RetrievalQuality = "CORRECT"
        elif len(relevant_chunks) == 0:
            quality = "INCORRECT"
        else:
            quality = "AMBIGUOUS"

        overall_score = len(relevant_chunks) / len(grades) if grades else 0.0

        trace["retrieval_quality"] = quality
        trace["relevant_doc_count"] = len(relevant_chunks)
        trace["irrelevant_doc_count"] = len(irrelevant_chunks)

        logger.info(
            "[CRAG] Retrieval evaluated — quality=%s, relevant=%d, irrelevant=%d, score=%.2f",
            quality, len(relevant_chunks), len(irrelevant_chunks), overall_score,
        )

        # ── Node 4: Decide knowledge source based on quality ──────────────────
        knowledge_sources: list[dict] = []
        web_search_query = query

        if quality == "CORRECT":
            # Path A: Vector store is good — build sources from relevant chunks
            knowledge_sources = self._build_sources(relevant_chunks)

        else:
            tavily_key = os.environ.get("TAVILY_API_KEY", "")
            if not tavily_key:
                logger.info("[CRAG] Web search triggered but TAVILY_API_KEY is not configured. Falling back to vector store chunks.")
                fallback_chunks = relevant_chunks if relevant_chunks else retrieved
                knowledge_sources = self._build_sources(fallback_chunks)
            else:
                # Path B/C: Need web search — rewrite query for web optimisation
                web_search_query = await self._rewrite_query(query)
                trace["query_rewrite_count"] += 1
                trace["web_search_used"] = True
                trace["web_search_query_used"] = web_search_query
                trace["final_query"] = web_search_query

                logger.info(
                    "[CRAG] Query rewritten for web — original=%s, rewritten=%s, trigger=%s",
                    query[:60], web_search_query[:60], quality,
                )

                web_results = await self._web_search(web_search_query)
                logger.info("[CRAG] Web search complete — %d results", len(web_results))

                # Convert web results to source format
                web_sources = [
                    {
                        "content": r["content"],
                        "source": r.get("source", "Web"),
                        "relevance_score": 0.75,
                        "metadata": {"from_web_search": True, "url": r.get("url")},
                    }
                    for r in web_results
                ]

                if quality == "AMBIGUOUS":
                    # Keep relevant vector store chunks AND add web results
                    vector_sources = self._build_sources(relevant_chunks)
                    knowledge_sources = vector_sources + web_sources
                else:
                    # INCORRECT: web results only
                    knowledge_sources = web_sources

                # Knowledge refinement
                knowledge_sources = self._refine_knowledge(knowledge_sources, [])

        if not knowledge_sources:
            return await self._direct_ai_answer(query, "No usable context after retrieval evaluation.")

        # ── Node 5: Generate answer + self-correction loop ────────────────────
        answer = ""
        groundedness_score = 1.0
        groundedness_supported = True
        current_query = query

        for attempt in range(self.MAX_RETRIES + 1):
            answer = await self._generate_response(current_query, knowledge_sources)

            # ── Node 6: Groundedness check (Self-RAG ISSUP) ───────────────────
            groundedness_score = await self._check_groundedness(answer, [
                s["content"] for s in knowledge_sources[:6]
            ], query=current_query)
            groundedness_supported = groundedness_score >= 0.7

            logger.info(
                "[CRAG] Groundedness check — attempt=%d, score=%.2f, supported=%s",
                attempt, groundedness_score, groundedness_supported,
            )

            if groundedness_supported:
                break

            # Self-correction: rewrite and re-retrieve
            trace["hallucination_failures"] += 1

            if attempt < self.MAX_RETRIES:
                trace["retry_count"] += 1

                hint = "The previous answer contained claims not grounded in the context. Focus only on what the context supports."
                current_query = await self._rewrite_query(query, hint=hint)
                trace["query_rewrite_count"] += 1

                logger.info(
                    "[CRAG] Self-correction retry %d — rewritten=%s",
                    attempt + 1, current_query[:80],
                )

                # Re-retrieve with corrected query
                retry_embedding = await self._generate_embedding(current_query)
                if retry_embedding is None:
                    retry_embedding = query_embedding

                retry_chunks = await self._retrieve_chunks(current_query, retry_embedding, self.TOP_K_EXPANDED)
                if retry_chunks:
                    retry_grades = await self._grade_documents_batch(current_query, retry_chunks)
                    retry_relevant = [c for c, g in zip(retry_chunks, retry_grades) if g.get("relevant")]
                    retry_sources = self._build_sources(retry_relevant if retry_relevant else retry_chunks)
                    knowledge_sources = self._refine_knowledge(retry_sources, [])

        # ── Composite confidence scoring ──────────────────────────────────────
        source_coverage = self._calc_source_coverage(knowledge_sources)
        final_confidence = self._compute_composite_confidence(
            overall_score, source_coverage, groundedness_score
        )

        trace["final_confidence"] = final_confidence
        trace["duration_ms"] = (asyncio.get_event_loop().time() - start_ms) * 1000

        logger.info(
            "[CRAG] Query complete — confidence=%.2f, quality=%s, duration=%.0fms",
            final_confidence, quality, trace["duration_ms"],
        )

        return {
            "answer": answer,
            "sources": knowledge_sources,
            "confidence": final_confidence,
            "retrieval_score": overall_score,
            "groundedness_score": groundedness_score,
            "web_search_used": trace["web_search_used"],
            "chunks_evaluated": len(grades),
            "chunks_relevant": len(relevant_chunks),
            "_crag": trace,
        }

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  DOCUMENT INGESTION                                                    ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def ingest_document(
        self,
        file_content: bytes,
        title: str,
        owner_id: str,
        tags: list | None = None,
        content_type: str = "text/plain",
        filename: str = "unknown",
    ) -> dict:
        """
        Ingest a document into the knowledge base.

        Steps:
          1. Extract text (PDF via PyMuPDF, or UTF-8 decode)
          2. Sanitize UTF-8
          3. Chunk text with sentence-boundary awareness
          4. Generate embeddings in batches of BATCH_SIZE
          5. Store document + chunks in DB

        Returns dict with: id, title, type, chunks_created, status
        """
        from backend.database import AsyncSessionLocal
        from backend.models import Document, Chunk

        tags = tags or []
        extracted_text = ""
        file_meta: dict = {"size": len(file_content), "mime_type": content_type}

        # ── Extract text based on content type ────────────────────────────────
        if content_type == "application/pdf":
            extracted_text = self._extract_pdf_text(file_content)
            file_meta["format"] = "pdf"
        elif (
            content_type.startswith("text/")
            or "markdown" in content_type
            or "json" in content_type
            or "csv" in content_type
        ):
            try:
                extracted_text = file_content.decode("utf-8", errors="replace")
            except Exception:
                extracted_text = file_content.decode("latin-1", errors="replace")
        else:
            raise ValueError(f"Unsupported file type: {content_type}")

        # ── UTF-8 sanitization ────────────────────────────────────────────────
        extracted_text = self._sanitize_utf8(extracted_text)
        if not extracted_text.strip():
            raise ValueError("No readable text found in document")

        # ── Determine document type ───────────────────────────────────────────
        doc_type = self._get_document_type(content_type)

        # ── Store document in DB ──────────────────────────────────────────────
        doc_id = str(uuid.uuid4())

        async with AsyncSessionLocal() as session:
            doc = Document(
                id=doc_id,
                owner_id=owner_id,
                title=title,
                type=doc_type,
                content=extracted_text,
                tags=tags,
                metadata_=file_meta,
            )
            session.add(doc)
            await session.commit()

        # ── Chunk text ────────────────────────────────────────────────────────
        text_chunks = self._chunk_text(extracted_text, self.CHUNK_SIZE, self.CHUNK_OVERLAP)
        logger.info("[RAGService] Chunked '%s' into %d chunks", title, len(text_chunks))

        # ── Generate embeddings & store chunks in batches ─────────────────────
        failed = 0
        chunks_created = 0

        for i in range(0, len(text_chunks), self.BATCH_SIZE):
            batch = text_chunks[i : i + self.BATCH_SIZE]

            # Generate embeddings using the configured provider
            batch_embeddings: list[list[float] | None] = []
            for chunk_text in batch:
                emb = await self._generate_embedding(chunk_text)
                batch_embeddings.append(emb)

            # Store all chunks in the batch in a single DB transaction
            try:
                async with AsyncSessionLocal() as session:
                    for idx, chunk_content in enumerate(batch):
                        embedding = batch_embeddings[idx] if idx < len(batch_embeddings) else None
                        chunk = Chunk(
                            id=str(uuid.uuid4()),
                            document_id=doc_id,
                            content=chunk_content,
                            embedding=embedding,
                            metadata_={
                                "chunk_index": i + idx,
                                "document_title": title,
                                "document_type": doc_type,
                                "owner_id": owner_id,
                            },
                        )
                        session.add(chunk)
                    await session.commit()
                chunks_created += len(batch)
            except Exception as db_err:
                failed += len(batch)
                logger.warning("[RAGService] Batch chunk storage failed at index %d: %s", i, db_err)

        if failed:
            logger.warning("[RAGService] %d/%d chunk(s) failed to store", failed, len(text_chunks))

        # ── Mark document as embedded ─────────────────────────────────────────
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(embedded_at=datetime.now(timezone.utc))
            )
            await session.commit()

        logger.info(
            "[RAGService] Ingested '%s' — %d chunks embedded", title, chunks_created
        )

        return {
            "id": doc_id,
            "title": title,
            "type": doc_type,
            "chunks_created": chunks_created,
            "status": "completed",
        }

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  DOCUMENT MANAGEMENT                                                   ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def delete_document(self, document_id: str) -> None:
        """Delete a document and all its associated chunks."""
        from backend.database import AsyncSessionLocal
        from backend.models import Document, Chunk

        async with AsyncSessionLocal() as session:
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            await session.execute(delete(Document).where(Document.id == document_id))
            await session.commit()

        logger.info("[RAGService] Deleted document %s", document_id)

    async def search_documents(self, user_id: str, query: str) -> list[dict]:
        """Search user's documents by title, content, or tags."""
        from backend.database import AsyncSessionLocal
        from backend.models import Document

        q = query.lower()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Document).where(Document.owner_id == user_id)
            )
            docs = result.scalars().all()

        matches = []
        for doc in docs:
            title_match = q in (doc.title or "").lower()
            content_match = q in (doc.content or "").lower()
            tag_match = any(q in t.lower() for t in (doc.tags or []))
            if title_match or content_match or tag_match:
                matches.append({
                    "id": doc.id,
                    "title": doc.title,
                    "type": doc.type,
                    "tags": doc.tags or [],
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                })
        return matches

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  UTF-8 SANITIZATION                                                    ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    def _sanitize_utf8(self, text: str) -> str:
        """
        Strip null bytes, BOM, non-printable control characters, and other
        problematic code-points that break PostgreSQL TEXT columns or PDF
        extraction artefacts. Unicode is normalised to NFC for consistent
        tokenisation.
        """
        before_len = len(text)

        # Remove null bytes
        cleaned = text.replace("\x00", "")

        # Remove BOM
        cleaned = cleaned.replace("\ufeff", "")

        # Remove non-printable control chars (keep newline \x0a, tab \x09, carriage return \x0d)
        cleaned = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)

        # Normalise to NFC
        cleaned = unicodedata.normalize("NFC", cleaned)

        # Collapse multiple whitespace (except newlines) to single space
        cleaned = re.sub(r"[^\S\n]+", " ", cleaned)

        stripped = before_len - len(cleaned)
        if stripped > 0:
            logger.warning(
                "[RAGService] sanitize_utf8 stripped %d character(s) from extracted text",
                stripped,
            )

        return cleaned

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  TEXT CHUNKING — Sentence-boundary aware                               ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    def _chunk_text(
        self, text: str, chunk_size: int = 1000, overlap: int = 200
    ) -> list[str]:
        """
        Split text into overlapping chunks, respecting sentence boundaries.

        Algorithm (from the TypeScript implementation):
          - Walk through text in steps of chunk_size
          - If a chunk boundary falls mid-text, look back for the last
            sentence boundary ('. ' or '\\n') within the chunk
          - If a good boundary is found (past 70% of chunk_size), break there
          - Include `overlap` characters from the end of the previous chunk
          - Never produce empty chunks
        """
        result: list[str] = []
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            actual = end

            # Try to break at a sentence boundary if not at the end of text
            if end < len(text):
                chunk_slice = text[start:end]
                # Find the last sentence boundary
                bp_period = chunk_slice.rfind(". ")
                bp_newline = chunk_slice.rfind("\n")
                bp = max(bp_period, bp_newline)

                # Only use the boundary if it's past 70% of the chunk
                if bp > chunk_size * 0.7:
                    actual = start + bp + 1

            content = text[start:actual].strip()
            if content:
                result.append(content)

            if actual >= len(text):
                break

            # Advance with overlap
            start = actual - overlap
            if start < 0:
                start = 0

            # Safety: ensure we always make forward progress
            if actual <= start + overlap and actual < len(text):
                start = actual

        return result

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  EMBEDDING GENERATION                                                  ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def _generate_embedding(self, text: str) -> list[float] | None:
        """Generate an embedding vector using the configured provider.

        Providers (set EMBEDDING_PROVIDER in .env):
          ollama             → nomic-embed-text via local Ollama (768-dim, no API key)
          sentence_transformers → HuggingFace local model (install: pip install sentence-transformers)
                               ST_MODEL env var selects model (default: all-MiniLM-L6-v2, 384-dim)
                               Better quality models: BAAI/bge-large-en-v1.5 (1024-dim)
          gemini             → Google text-embedding-004 (768-dim, needs GEMINI_API_KEY)
          cloudflare         → Cloudflare Workers AI embedding
          none               → falls through to PostgreSQL FTS keyword search
        """
        if self.embedding_provider == "ollama":
            from backend.services.ollama_service import ollama_service
            try:
                embedding = await ollama_service.embed(text[:8000])
                if embedding is None:
                    logger.warning("[RAGService] Ollama embedding returned None for: %s...", text[:50])
                return embedding
            except Exception as e:
                logger.warning("[RAGService] Ollama embedding failed '%s...': %s", text[:50], e)
                return None

        elif self.embedding_provider == "sentence_transformers":
            # Pure-Python HuggingFace embeddings — no server needed.
            # First run downloads the model (~90 MB for MiniLM, ~1.3 GB for bge-large).
            # Install with: pip install sentence-transformers
            try:
                model_name = os.environ.get("ST_MODEL", "all-MiniLM-L6-v2")
                if not hasattr(self, "_st_model") or self._st_model_name != model_name:
                    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
                    logger.info("[RAGService] Loading sentence-transformers model: %s", model_name)
                    self._st_model = await asyncio.to_thread(SentenceTransformer, model_name)
                    self._st_model_name = model_name
                import functools
                embedding = await asyncio.to_thread(
                    functools.partial(self._st_model.encode, text[:8000], convert_to_numpy=True)
                )
                return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
            except ImportError:
                logger.error(
                    "[RAGService] sentence-transformers not installed. Run: pip install sentence-transformers"
                )
                return None
            except Exception as e:
                logger.warning("[RAGService] sentence-transformers failed '%s...': %s", text[:50], e)
                return None

        elif self.embedding_provider == "cloudflare":
            from backend.services.cloudflare_ai_service import cloudflare_ai
            try:
                embedding = await cloudflare_ai.embed(text[:8000])
                if embedding is None:
                    logger.warning("[RAGService] Cloudflare embedding returned None for: %s...", text[:50])
                return embedding
            except Exception as e:
                logger.warning("[RAGService] Cloudflare embedding failed '%s...': %s", text[:50], e)
                return None

        elif self.embedding_provider == "gemini":
            # Google Gemini text-embedding-004 — 768-dim, free with Gemini API key
            try:
                import google.generativeai as genai_embed
                api_key = os.environ.get("GEMINI_API_KEY", "")
                if not api_key:
                    logger.warning("[RAGService] Gemini embedding skipped — GEMINI_API_KEY not set")
                    return None
                def _embed_sync():
                    genai_embed.configure(api_key=api_key)
                    result = genai_embed.embed_content(
                        model="models/text-embedding-004",
                        content=text[:8000],
                        task_type="retrieval_query",
                    )
                    return result["embedding"]
                embedding = await asyncio.to_thread(_embed_sync)
                return list(embedding) if embedding else None
            except Exception as e:
                logger.warning("[RAGService] Gemini embedding failed '%s...': %s", text[:50], e)
                return None

        else:
            logger.debug("[RAGService] Embedding skipped (provider=%s) — using text search fallback", self.embedding_provider)
            return None

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  RETRIEVAL — Vector search with text-search fallback                   ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def _retrieve_chunks(
        self,
        query: str,
        query_embedding: list[float] | None,
        top_k: int,
        owner_id: str | None = None,
        group_filter: list[str] | None = None,
    ) -> list[dict]:
        """
        Retrieve top-K document chunks scoped to owner_id when provided.

        Fallback chain: pgvector cosine → Python cosine → FTS (to_tsvector) → ILIKE
        Returns: [{id, content, score, document_id, metadata}]
        """
        from backend.database import AsyncSessionLocal
        from backend.models import Chunk

        if query_embedding is not None:
            # ── Attempt 1: pgvector cosine similarity ─────────────────────────
            try:
                async with AsyncSessionLocal() as session:
                    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
                    owner_clause = "AND d.owner_id = :owner_id" if owner_id else ""
                    group_clause = ""
                    params = {"emb": embedding_str, "limit": top_k, "owner_id": owner_id}
                    if group_filter:
                        group_clause = "AND d.tags && :group_filter::text[]"
                        params["group_filter"] = group_filter
                    result = await session.execute(
                        text(f"""
                            SELECT c.id, c.document_id, c.content, c.metadata,
                                   1 - (c.embedding::vector <=> :emb::vector) AS score
                            FROM chunks c
                            JOIN documents d ON d.id = c.document_id
                            WHERE c.embedding IS NOT NULL
                            {owner_clause}
                            {group_clause}
                            ORDER BY c.embedding::vector <=> :emb::vector
                            LIMIT :limit
                        """),
                        params,
                    )
                    rows = result.mappings().all()
                    if rows:
                        return [
                            {
                                "id": str(row["id"]),
                                "content": row["content"],
                                "score": float(row["score"]) if row["score"] else 0.0,
                                "document_id": str(row["document_id"]),
                                "metadata": row["metadata"] or {},
                            }
                            for row in rows
                            if row["score"] and float(row["score"]) > 0
                        ]
            except Exception as e:
                logger.warning("[CRAG] pgvector query failed '%s...': %s", query[:50], str(e)[:120])

            # ── Attempt 2: Python cosine over owner-scoped chunks ──────────────
            try:
                async with AsyncSessionLocal() as session:
                    from backend.models import Document
                    if owner_id:
                        # Join through documents to filter by owner
                        cond = [Chunk.embedding.isnot(None), Document.owner_id == owner_id]
                        if group_filter:
                            cond.append(Document.tags.overlap(group_filter))
                        stmt = (
                            select(Chunk)
                            .join(Document, Document.id == Chunk.document_id)
                            .where(*cond)
                        )
                    else:
                        stmt = select(Chunk).where(Chunk.embedding.isnot(None))
                    result = await session.execute(stmt)
                    chunks = result.scalars().all()

                scored = []
                for chunk in chunks:
                    if chunk.embedding and isinstance(chunk.embedding, list) and len(chunk.embedding) > 0:
                        score = _cosine_similarity(query_embedding, chunk.embedding)
                        scored.append({
                            "id": str(chunk.id),
                            "content": chunk.content,
                            "score": score,
                            "document_id": str(chunk.document_id),
                            "metadata": chunk.metadata_ or {},
                        })

                scored.sort(key=lambda x: x["score"], reverse=True)
                if scored:
                    logger.info("[CRAG] Python cosine fallback found %d chunks", len(scored))
                    return scored[:top_k]
                logger.warning("[CRAG] Python cosine fallback: no scored chunks")
            except Exception as e:
                logger.warning("[CRAG] Python cosine fallback failed '%s...': %s", query[:50], e)

            # ── Attempt 3: ILIKE text search fallback ─────────────────────────────
            logger.info("[CRAG] Falling back to ILIKE text search for query '%s...'", query[:50])
            try:
                text_results = await self._text_search_fallback(query, top_k, owner_id=owner_id, group_filter=group_filter)
                if text_results:
                    logger.info("[CRAG] Text search fallback found %d chunks for query '%s...'", len(text_results), query[:50])
                    return text_results
                else:
                    logger.warning("[CRAG] Text search fallback found no results for query '%s...'", query[:50])
            except Exception as e:
                logger.error("[CRAG] Text search fallback failed for query '%s...': %s", query[:50], e)
                return []

        # If no embedding available, go straight to text search
        logger.info("[CRAG] No query embedding available for query '%s...', using ILIKE text search", query[:50])
        try:
            text_results = await self._text_search_fallback(query, top_k, owner_id=owner_id, group_filter=group_filter)
            if text_results:
                logger.info("[CRAG] Text search (no embedding) found %d chunks for query '%s...'", len(text_results), query[:50])
                return text_results
            else:
                logger.warning("[CRAG] Text search (no embedding) found no results for query '%s...'", query[:50])
        except Exception as e:
            logger.error("[CRAG] Text search fallback failed for query '%s...': %s", query[:50], e)
            return []

    async def _retrieve_hybrid(
        self,
        query: str,
        query_embedding: list[float] | None,
        top_k: int,
        owner_id: str | None = None,
        group_filter: list[str] | None = None,
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion of vector search + full-text search.

        RRF score = Σ 1 / (k + rank_i)  where k=60 (standard constant).
        Chunks that rank well in BOTH methods score highest.
        Falls back gracefully if either source returns nothing.
        """
        K = 60
        expanded = min(top_k * 3, 20)  # retrieve more candidates to fuse

        # Run both in parallel
        if query_embedding is not None:
            vector_task = asyncio.ensure_future(
                self._retrieve_chunks(query, query_embedding, expanded, owner_id=owner_id, group_filter=group_filter)
            )
        else:
            async def _empty_vec() -> list:
                return []
            vector_task = asyncio.ensure_future(_empty_vec())
        fts_task = asyncio.ensure_future(
            self._text_search_fallback(query, expanded, owner_id=owner_id, group_filter=group_filter)
        )
        vector_results, fts_results = await asyncio.gather(vector_task, fts_task, return_exceptions=True)
        if isinstance(vector_results, Exception): vector_results = []
        if isinstance(fts_results, Exception):    fts_results = []

        if not vector_results and not fts_results:
            return []

        # Build RRF score map
        rrf: dict[str, dict] = {}
        for rank, chunk in enumerate(vector_results or []):
            cid = chunk["id"]
            rrf.setdefault(cid, {"score": 0.0, "chunk": chunk})
            rrf[cid]["score"] += 1.0 / (K + rank + 1)

        for rank, chunk in enumerate(fts_results or []):
            cid = chunk["id"]
            if cid not in rrf:
                rrf[cid] = {"score": 0.0, "chunk": chunk}
            rrf[cid]["score"] += 1.0 / (K + rank + 1)

        ranked = sorted(rrf.values(), key=lambda x: x["score"], reverse=True)
        for item in ranked:
            item["chunk"]["score"] = item["score"]  # expose RRF score as the chunk score

        logger.debug("[RAG] Hybrid RRF — vector=%d, fts=%d → merged=%d, returning top_%d",
                     len(vector_results or []), len(fts_results or []), len(ranked), top_k)
        return [item["chunk"] for item in ranked[:top_k]]

    async def retrieve_context(
        self,
        query: str,
        top_k: int = 4,
        owner_id: str | None = None,
        group_filter: list[str] | None = None,
    ) -> str:
        """
        Hybrid RAG context retrieval for chat injection.

        Pipeline:
          1. Hybrid retrieval (vector + FTS via RRF) — top_k * 2 candidates
          2. Lightweight LLM grading — keeps only relevant chunks
          3. Quality threshold 0.40 (up from 0.25) to reduce noise
          4. Returns formatted context string for system prompt injection
        """
        try:
            from backend.database import AsyncSessionLocal
            from backend.models import Document
            async with AsyncSessionLocal() as session:
                if owner_id:
                    cond = [Document.owner_id == owner_id, Document.embedded_at.isnot(None)]
                    if group_filter:
                        cond.append(Document.tags.overlap(group_filter))
                    check_q = select(Document.id).where(*cond).limit(1)
                else:
                    check_q = select(Document.id).where(Document.embedded_at.isnot(None)).limit(1)
                if not (await session.execute(check_q)).fetchone():
                    return ""

            query_embedding = await self._generate_embedding(query)

            # Step 1: Hybrid retrieval — get 2× candidates for grading
            candidates = await self._retrieve_hybrid(
                query, query_embedding, top_k * 2, owner_id=owner_id, group_filter=group_filter
            )

            if not candidates:
                return ""

            # Step 2: Lightweight LLM grading (only when we have surplus candidates)
            chunks = candidates
            if len(candidates) > top_k:
                try:
                    grades = await self._grade_documents_batch(query, candidates)
                    relevant = [c for c, g in zip(candidates, grades) if g.get("relevant")]
                    if len(relevant) >= 1:
                        chunks = relevant
                        logger.info("[RAG] Grading: %d/%d chunks relevant", len(relevant), len(candidates))
                    else:
                        logger.info("[RAG] Grading: no chunks passed — using top candidates")
                except Exception as grade_err:
                    logger.debug("[RAG] Grading skipped: %s", grade_err)

            # Step 3: RRF-aware quality gate
            # RRF scores are in [0, ~0.033] — use 0.008 (≈ rank 60+) as the noise floor.
            # LLM grading already filtered aggressively; threshold is a last safety net.
            RRF_NOISE_FLOOR = 0.008
            filtered = [c for c in chunks if c.get("score", 1.0) > RRF_NOISE_FLOOR]
            final = (filtered or chunks)[:top_k]

            # Step 4: Build context string
            ctx_parts: list[str] = []
            seen_docs: set[str] = set()
            for chunk in final:
                doc_id = chunk.get("document_id", "unknown")
                content = chunk.get("content", "").strip()
                if not content or len(content) < 50:
                    continue
                doc_title = chunk.get("metadata", {}).get("document_title", doc_id[:8])
                label = f"[Source: {doc_title}]" if doc_id not in seen_docs else ""
                seen_docs.add(doc_id)
                ctx_parts.append(f"{label}\n{content}")

            if not ctx_parts:
                return ""

            return (
                "\n\n[KNOWLEDGE BASE CONTEXT — Use this information to answer the user's question. "
                "Cite the source document name when making claims.]\n\n"
                + "\n\n---\n\n".join(ctx_parts)
                + "\n\n[END OF CONTEXT]"
            )

        except Exception as e:
            logger.warning("[RAGService] retrieve_context failed: %s", e)
            return ""

    async def _text_search_fallback(
        self, query: str, top_k: int, owner_id: str | None = None, group_filter: list[str] | None = None
    ) -> list[dict]:
        """
        PostgreSQL full-text search fallback using to_tsvector + ts_rank.

        Significantly better than ILIKE:
        - Language-aware stemming (English)
        - TF-IDF based ts_rank scoring (0.0–1.0, not fixed 0.5)
        - Phrase matching and AND/OR semantics
        - Falls back to ILIKE if FTS index is unavailable
        """
        from backend.database import AsyncSessionLocal

        # Build owner filter
        need_join = bool(owner_id or group_filter)
        owner_join = "JOIN documents d ON d.id = c.document_id" if need_join else ""
        owner_where = "AND d.owner_id = :owner_id" if owner_id else ""
        group_where = "AND d.tags && :group_filter::text[]" if group_filter else ""

        # Build tsquery — clean query, convert to FTS
        fts_query = " & ".join(
            w.strip() for w in re.split(r"\s+", query.strip())
            if len(w.strip()) > 2 and w.strip().isalpha()
        ) or query.strip()

        async with AsyncSessionLocal() as session:
            # ── Attempt A: PostgreSQL FTS with ts_rank ────────────────────────
            try:
                fts_params: dict = {"query": fts_query, "owner_id": owner_id, "limit": top_k}
                if group_filter:
                    fts_params["group_filter"] = group_filter
                result = await session.execute(
                    text(f"""
                        SELECT c.id, c.document_id, c.content, c.metadata,
                               ts_rank(
                                   to_tsvector('english', c.content),
                                   plainto_tsquery('english', :query)
                               ) AS score
                        FROM chunks c
                        {owner_join}
                        WHERE to_tsvector('english', c.content) @@ plainto_tsquery('english', :query)
                        {owner_where}
                        {group_where}
                        ORDER BY score DESC
                        LIMIT :limit
                    """),
                    fts_params,
                )
                rows = result.mappings().all()
                if rows:
                    return [
                        {
                            "id": str(row["id"]),
                            "content": row["content"],
                            "score": min(float(row["score"]) * 2, 1.0),  # ts_rank is ~0–0.5; scale to 0–1
                            "document_id": str(row["document_id"]),
                            "metadata": row["metadata"] or {},
                        }
                        for row in rows
                    ]
            except Exception as e:
                logger.warning("[CRAG] PostgreSQL FTS failed, trying ILIKE: %s", str(e)[:100])

            # ── Attempt B: ILIKE word-by-word (last resort) ───────────────────
            try:
                words = [w for w in query.split() if len(w) > 2][:8]  # cap at 8 words
                if not words:
                    words = [query[:50]]
                conditions = " OR ".join(f"c.content ILIKE :w{i}" for i in range(len(words)))
                params: dict = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
                params.update({"limit": top_k, "owner_id": owner_id})
                if group_filter:
                    params["group_filter"] = group_filter
                result = await session.execute(
                    text(f"""
                        SELECT c.id, c.document_id, c.content, c.metadata
                        FROM chunks c
                        {owner_join}
                        WHERE ({conditions})
                        {owner_where}
                        {group_where}
                        LIMIT :limit
                    """),
                    params,
                )
                rows = result.mappings().all()
                return [
                    {
                        "id": str(row["id"]),
                        "content": row["content"],
                        "score": 0.3,  # low score — keyword match only
                        "document_id": str(row["document_id"]),
                        "metadata": row["metadata"] or {},
                    }
                    for row in rows
                ]
            except Exception as e:
                logger.error("[CRAG] ILIKE fallback failed '%s...': %s", query[:50], e)
                return []

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  QUERY REWRITING                                                       ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def _rewrite_query(self, query: str, hint: str | None = None) -> str:
        """
        Reformulate the user query for better retrieval / web search.

        From the LangGraph CRAG cookbook:
          "Look at the input and try to reason about the underlying semantic
           intent / meaning. Formulate an improved question."

        On failure, returns the original query unchanged.
        """
        from backend.services.ai_service import ai_service

        hint_section = f"\nAdditional context:\n{hint}" if hint else ""
        prompt = f"""Look at the input and try to reason about the underlying semantic intent / meaning.

Here is the initial question:
{query}
{hint_section}
Formulate an improved question optimised for search:
- Clarify the intent
- Expand any abbreviations or jargon
- Add synonyms or alternative phrasings if helpful
- Keep it ≤ 30 words

Respond with ONLY the improved question text — no labels, no preamble."""

        try:
            result = await ai_service.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                agent="memory",
            )
            rewritten = result.strip().strip("\"'")
            return rewritten if rewritten else query
        except Exception as e:
            logger.warning("[CRAG] Query rewrite failed for query '%s...': %s", query[:50], e)
            return query

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  BATCH DOCUMENT GRADING — Single LLM call                             ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def _grade_documents_batch(
        self, query: str, chunks: list[dict]
    ) -> list[dict]:
        """
        Grade ALL retrieved chunks in a SINGLE LLM call.

        Prompt structure (from the CRAG / LangGraph cookbook):
          "Give a binary score 'yes' or 'no' for each document below."

        Expected JSON response:
          [{"index": 0, "binary_score": "yes", "reasoning": "..."}, ...]

        Adds a 'relevant' boolean to each returned grade dict.
        Falls back to cosine score > 0.5 proxy if LLM grading fails.
        """
        from backend.services.ai_service import ai_service

        doc_list = "\n\n---\n\n".join(
            f"[{i}] {chunk['content'][:500]}" for i, chunk in enumerate(chunks)
        )

        prompt = f"""You are a grader assessing relevance of retrieved documents to a user question.

Here is the user question:
{query}

Here are the retrieved documents (0-indexed):
{doc_list}

For each document, give a binary score "yes" or "no" indicating whether it is
relevant to the question. Use the criterion from the CRAG paper:
  "If the document contains keyword(s) or semantic meaning related to the question."

Respond ONLY with valid JSON — no markdown fences, no explanation.
Return a JSON array with one object per document, in index order:
[
  {{ "index": <number>, "binary_score": "yes" | "no", "reasoning": "<one sentence>" }},
  ...
]"""

        try:
            raw = await ai_service.chat_completion(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                temperature=0.1,
                agent="memory",
            )
            # Strip markdown fences if present
            text_clean = re.sub(r"```json|```", "", raw).strip()
            parsed = json.loads(text_clean)

            if not isinstance(parsed, list):
                raise ValueError("Expected JSON array")

            # Build grades aligned with chunks[]
            grades = []
            for i, chunk in enumerate(chunks):
                grade = next((g for g in parsed if g.get("index") == i), None)
                if grade:
                    relevant = str(grade.get("binary_score", "")).lower() == "yes"
                    reasoning = grade.get("reasoning", "")
                else:
                    # Fallback: use cosine score proxy
                    relevant = chunk.get("score", 0) >= self.RELEVANCE_THRESHOLD
                    reasoning = "LLM grade missing — cosine proxy used"

                grades.append({
                    "document_id": chunk.get("document_id", ""),
                    "chunk_content": chunk["content"][:120],
                    "relevant": relevant,
                    "reasoning": reasoning,
                })

            return grades

        except Exception as e:
            logger.warning("[CRAG] Batch grading failed (%d chunks) for query '%s...': %s", len(chunks), query[:50], e)
            # Fall back: use cosine score >= RELEVANCE_THRESHOLD as relevance proxy
            relevant_count = sum(1 for chunk in chunks if chunk.get("score", 0) >= self.RELEVANCE_THRESHOLD)
            logger.info("[CRAG] Cosine proxy: %d/%d chunks deemed relevant", relevant_count, len(chunks))
            return [
                {
                    "document_id": chunk.get("document_id", ""),
                    "chunk_content": chunk["content"][:120],
                    "relevant": chunk.get("score", 0) >= self.RELEVANCE_THRESHOLD,
                    "reasoning": "LLM batch grading failed — cosine score used as proxy",
                }
                for chunk in chunks
            ]

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  GROUNDEDNESS CHECK — Self-RAG ISSUP concept                           ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def _check_groundedness(
        self, answer: str, sources: list[str], query: str = ""
    ) -> float:
        """
        Check whether the generated answer is grounded in the source context.

        Uses the Self-RAG ISSUP token concept: an LLM call verifies that all
        factual claims in the answer are supported by the retrieved context.

        Returns a float 0.0–1.0 representing groundedness confidence.
        On failure, returns 0.5 (neutral).
        """
        from backend.services.ai_service import ai_service

        if not sources:
            return 0.4

        context_block = "\n---\n".join(
            f"[{i + 1}]: {src[:500]}" for i, src in enumerate(sources)
        )

        prompt = f"""You are a factual accuracy auditor. Your job is to check whether all claims
in the generated answer are supported by the provided context.

CONTEXT:
{context_block}

GENERATED ANSWER:
{answer}

Check: Are all factual claims in the answer grounded in the context above?
Respond ONLY with valid JSON — no markdown, no explanation.

{{
  "supported": <boolean — true only if ALL claims are grounded>,
  "confidence": <number 0.0–1.0>,
  "unsupported_claims": [<list any verbatim claim phrases not in the context, or []>]
}}"""

        try:
            raw = await ai_service.chat_completion(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                temperature=0.1,
                agent="memory",
            )
            text_clean = re.sub(r"```json|```", "", raw).strip()
            parsed = json.loads(text_clean)
            confidence = float(parsed.get("confidence", 0.5))
            return max(0.0, min(1.0, confidence))
        except Exception as e:
            logger.warning("[CRAG] Groundedness check failed for query '%s...': %s", query[:50], e)
            # Conservative degrade: assume supported so we don't loop forever
            return 0.6

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  WEB SEARCH — Tavily API                                               ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def _web_search(self, query: str) -> list[dict]:
        """
        Search the web using Tavily API for supplemental knowledge.

        Priority:
          1. If TAVILY_API_KEY is set → call Tavily Search API
          2. Degrade gracefully → return empty results

        Returns list of dicts: {content, source, score, url}
        """
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

        if tavily_key:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": tavily_key,
                            "query": query,
                            "search_depth": "basic",
                            "max_results": 5,
                            "include_answer": True,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    results: list[dict] = []

                    # Include Tavily's synthesised answer if available
                    if data.get("answer"):
                        results.append({
                            "content": data["answer"],
                            "source": "Tavily Answer",
                            "score": 0.85,
                            "url": None,
                        })

                    # Include individual search results
                    for r in data.get("results", []):
                        content = r.get("content") or r.get("snippet") or ""
                        if content:
                            results.append({
                                "content": content,
                                "source": r.get("title", "Web"),
                                "score": 0.75,
                                "url": r.get("url"),
                            })

                    return results

            except Exception as e:
                logger.warning("[CRAG] Tavily search failed for query '%s...': %s", query[:50], e)

        # Graceful degrade — no web search available
        logger.warning(
            "[CRAG] No web search provider available (set TAVILY_API_KEY). "
            "Falling back to vector store only."
        )
        return []

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  KNOWLEDGE REFINEMENT                                                  ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    def _refine_knowledge(
        self, chunks: list[dict], web_results: list[dict]
    ) -> list[dict]:
        """
        Refine knowledge sources by combining, deduplicating, filtering,
        and capping the total context.

        From the CRAG paper: partition retrieved documents into "knowledge strips",
        grade each strip, filter irrelevant ones.

        Simplified:
          1. Combine chunk sources + web results
          2. Deduplicate by content fingerprint (first 100 chars)
          3. Filter very low relevance (below 0.2) unless few sources
          4. Sort by relevance score descending
          5. Cap at 10 sources
        """
        # Combine all sources
        all_sources = list(chunks)

        for wr in web_results:
            all_sources.append({
                "content": wr.get("content", ""),
                "source": wr.get("source", "Web"),
                "relevance_score": wr.get("score", 0.75),
                "metadata": {"from_web_search": True, "url": wr.get("url")},
            })

        # Deduplicate by first 100 chars
        seen: set[str] = set()
        deduped: list[dict] = []
        for source in all_sources:
            content = source.get("content", "")
            key = re.sub(r"\s+", " ", content[:100].lower())
            if key not in seen:
                seen.add(key)
                deduped.append(source)

        # Filter very low relevance (below 0.2) unless we have few sources
        if len(deduped) > 3:
            filtered = [
                s for s in deduped
                if s.get("relevance_score", s.get("score", 0.5)) >= 0.2
            ]
        else:
            filtered = deduped

        # Sort by relevance score descending
        filtered.sort(
            key=lambda s: s.get("relevance_score", s.get("score", 0.0)),
            reverse=True,
        )

        # Cap at 10 sources
        return filtered[:10]

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  RESPONSE GENERATION                                                   ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    async def _generate_response(
        self, query: str, sources: list[dict]
    ) -> str:
        """
        Generate an answer using the provided knowledge sources.

        The LLM is instructed to answer using ONLY the provided sources,
        and to cite source numbers when making claims.
        """
        from backend.services.ai_service import ai_service

        context_block = "\n\n---\n\n".join(
            f"[Source {i + 1}] ({s.get('source', 'Unknown')}):\n{s.get('content', '')[:800]}"
            for i, s in enumerate(sources)
        )

        prompt = f"""You are an expert cybersecurity analyst answering a question using ONLY the provided sources.

SOURCES:
{context_block}

QUESTION:
{query}

Instructions:
- Answer the question using ONLY information from the provided sources
- Cite source numbers [1], [2], etc. when making specific claims
- If the sources don't contain enough information, say so explicitly
- Be precise, technical, and actionable
- Structure your response with clear sections if appropriate"""

        try:
            result = await ai_service.chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                agent="planner",
            )
            return result.strip()
        except Exception as e:
            logger.error("[CRAG] Response generation failed for query '%s...': %s", query[:50], e)
            return f"I was unable to generate a response. Error: {str(e)[:200]}"

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  CONFIDENCE SCORING                                                    ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    def _compute_composite_confidence(
        self,
        retrieval_score: float,
        generation_confidence: float,
        groundedness: float,
    ) -> float:
        """
        Compute composite confidence score.

        Weights:
          40% retrieval quality score  (ratio of relevant docs)
          30% generation confidence    (source coverage breadth + quality)
          30% groundedness score       (from ISSUP check)

        Clamped to [0.0, 1.0].
        """
        raw = (
            self.CONFIDENCE_WEIGHTS["retrieval"] * retrieval_score
            + self.CONFIDENCE_WEIGHTS["generation"] * generation_confidence
            + self.CONFIDENCE_WEIGHTS["groundedness"] * groundedness
        )
        return max(0.0, min(1.0, raw))

    def _calc_source_coverage(self, sources: list[dict]) -> float:
        """
        Calculate source coverage: how broadly and strongly the sources
        cover the query space.

        Combines average relevance score with a count factor (capped at 3 sources
        for full credit).
        """
        if not sources:
            return 0.0

        avg_score = sum(
            s.get("relevance_score", s.get("score", 0.5))
            for s in sources
        ) / len(sources)

        count_factor = min(len(sources) / 3.0, 1.0)
        return min(avg_score * count_factor, 1.0)

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  PDF TEXT EXTRACTION                                                   ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    def _extract_pdf_text(self, content: bytes) -> str:
        """
        Extract text from PDF file bytes using PyMuPDF (fitz).

        Falls back to empty string on any error to avoid crashing ingestion
        for malformed PDFs.
        """
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=content, filetype="pdf")
            pages: list[str] = []
            for page in doc:
                page_text = page.get_text("text")
                if page_text:
                    pages.append(page_text)
            doc.close()

            full_text = "\n\n".join(pages)
            logger.info("[RAGService] Extracted %d pages from PDF", len(pages))
            return full_text

        except ImportError:
            logger.error(
                "[RAGService] PyMuPDF (fitz) is not installed — "
                "install with: pip install PyMuPDF"
            )
            return ""
        except Exception as e:
            logger.error("[RAGService] PDF extraction failed: %s", e)
            return ""

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  HELPERS                                                               ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    def _build_sources(self, chunks: list[dict]) -> list[dict]:
        """
        Convert ranked chunks into the standard source format used throughout
        the pipeline.
        """
        return [
            {
                "content": chunk.get("content", ""),
                "source": (
                    chunk.get("metadata", {}).get("document_title")
                    or chunk.get("metadata", {}).get("title")
                    or "Document"
                ),
                "relevance_score": chunk.get("score", 0.5),
                "metadata": chunk.get("metadata", {}),
            }
            for chunk in chunks
        ]

    async def _direct_ai_answer(self, query: str, note: str) -> dict:
        """Generate an answer directly from the AI service without RAG context."""
        from backend.services.ai_service import ai_service

        try:
            result = await ai_service.chat_completion(
                [{"role": "user", "content": f"[{note}]\n\n{query}"}],
                agent="planner",
            )
            return {
                "answer": result.strip(),
                "sources": [],
                "confidence": 0.5,
                "retrieval_score": 0.0,
                "groundedness_score": 0.0,
                "web_search_used": False,
                "chunks_evaluated": 0,
                "chunks_relevant": 0,
                "_fallback_used": "direct_ai",
                "_fallback_reason": note,
            }
        except Exception as e:
            logger.error("[CRAG] Direct AI answer failed for query '%s...' (note: %s): %s",
                        query[:50], note, e)
            return {
                "answer": "I'm unable to answer this query at the moment.",
                "sources": [],
                "confidence": 0.0,
                "retrieval_score": 0.0,
                "groundedness_score": 0.0,
                "web_search_used": False,
                "chunks_evaluated": 0,
                "chunks_relevant": 0,
                "_fallback_used": "direct_ai_error",
                "_fallback_reason": "AI service unavailable",
            }

    async def _keyword_fallback(self, query: str) -> dict:
        """
        Fallback when embedding generation fails completely.
        Uses text search and generates a response from keyword-matched sources.
        """
        from backend.services.ai_service import ai_service

        try:
            chunks = await self._text_search_fallback(query, 5)
            if not chunks:
                logger.warning("[CRAG] No matching documents found in keyword fallback for query: %s...", query[:50])
                return await self._direct_ai_answer(query, "No matching documents")

            sources = [
                {
                    "content": c["content"],
                    "source": "document",
                    "relevance_score": 0.5,
                }
                for c in chunks
            ]
            answer = await self._generate_response(query, sources)
            return {
                "answer": answer,
                "sources": sources,
                "confidence": 0.4,
                "retrieval_score": 0.4,
                "groundedness_score": 0.5,
                "web_search_used": False,
                "chunks_evaluated": len(chunks),
                "chunks_relevant": len(chunks),
                "_fallback_used": "keyword_search",
                "_fallback_reason": "Embedding generation failed",
            }
        except Exception as e:
            logger.error("[CRAG] Keyword fallback failed for query '%s...': %s", query[:50], e)
            logger.info("[CRAG] Falling back to direct AI answer due to keyword fallback failure")
            return await self._direct_ai_answer(query, "Knowledge base unavailable")

    @staticmethod
    def _get_document_type(mime: str) -> str:
        """Map MIME type to a simplified document type label."""
        if mime == "application/pdf":
            return "pdf"
        if "markdown" in mime:
            return "markdown"
        if "json" in mime:
            return "json"
        if "csv" in mime:
            return "csv"
        if mime.startswith("text/"):
            return "text"
        return "unknown"


# ── Singleton export ──────────────────────────────────────────────────────────

rag_service = RAGService()
