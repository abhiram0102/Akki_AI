---
name: Ollama + RAG integration
description: Multi-provider AI setup and ChromaDB replacement with PostgreSQL vector search
---

## Rule
- AI provider is controlled by AI_PROVIDER env var: "auto" (default), "ollama", "gemini"
- Ollama is checked at startup via checkOllamaAvailability(); result cached in _available flag
- ChromaDB is completely removed; RAG uses chunks.embedding (real[]) + JS cosine similarity

## How agent model routing works
Each agentRole maps to a different Ollama model:
- "chat"    → OLLAMA_CHAT_MODEL    (default: llama3.2)
- "code"    → OLLAMA_CODE_MODEL    (default: codellama)
- "redteam" → OLLAMA_REDTEAM_MODEL (default: mistral)
- "embed"   (for RAG embeddings)  → OLLAMA_EMBED_MODEL (default: nomic-embed-text)

Pass `agentRole` in ChatCompletionOptions to route to the right model.

## Vector store approach
- No ChromaDB, no pgvector extension needed
- Embeddings stored in chunks.embedding (real[] — already in schema)
- At query time: fetch all chunks with non-null embeddings from DB, rank by cosine similarity in JS
- getAllChunksWithEmbeddings() method added to IStorage + DatabaseStorage

**Why:** ChromaDB requires a separate running process (connection refused on Replit). PostgreSQL is already available; cosine similarity in JS is fast for ≤50k chunks and requires zero new infrastructure.

## Key files
- server/services/ollama.ts — Ollama HTTP client
- server/services/ai.ts — multi-provider dispatcher (Ollama | Gemini)
- server/services/rag.ts — ChromaDB-free RAG
- server/storage.ts — getAllChunksWithEmbeddings() added

## Env vars required for Ollama
- OLLAMA_URL=http://<your-machine>:11434
- AI_PROVIDER=ollama (or "auto")
- OLLAMA_CHAT_MODEL, OLLAMA_CODE_MODEL, OLLAMA_REDTEAM_MODEL, OLLAMA_EMBED_MODEL
