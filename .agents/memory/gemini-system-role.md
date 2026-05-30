---
name: Gemini API System Role Constraint
description: Gemini chat history only allows user/model roles; system messages must use systemInstruction.
---

**Rule:** Never include a `{ role: "system", ... }` entry in the Gemini `history` array. Pass system prompts via the `systemInstruction` field of `startChat()`.

**Why:** Gemini's SDK throws or silently drops messages with unsupported roles. Only `user` and `model` are valid in history.

**How to apply:** In `server/services/ai.ts`, extract any system messages from the messages array before building history, and pass them as `systemInstruction: { role: "system", parts: [{ text: ... }] }` to `model.startChat()`.
