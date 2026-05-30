---
name: ChromaDB v3 Embedding Function
description: chromadb v3 requires an explicit IEmbeddingFunction at collection creation; omitting it or passing null causes a crash.
---

**Rule:** Always pass an `embeddingFunction` implementing `IEmbeddingFunction` (`generate(texts: string[]): Promise<number[][]>`) when calling `chromaClient.getOrCreateCollection()`.

**Why:** chromadb v3 removed the old `embeddingFunction: null` shorthand. Without an EF, it tries to load `@chroma-core/default-embed` (not installed) and throws at startup.

**How to apply:** In `server/services/rag.ts`, define a `geminiEmbeddingFunction` wrapping `aiService.generateEmbedding()` and pass it to every `getOrCreateCollection` call. The function is only used as fallback; manual embeddings passed in `add()`/`query()` calls take precedence.
