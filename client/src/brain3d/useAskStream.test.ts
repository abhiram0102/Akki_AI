import { describe, expect, it } from "vitest";
import { parseSSEChunks } from "./useAskStream";

// ── parseSSEChunks ───────────────────────────────────────────────────────────
// The backend's `sse_starlette.EventSourceResponse` writes `data: <json>\n\n`
// blocks. A network chunk boundary can land anywhere — including mid-JSON —
// so the parser must buffer partial input across calls and only emit once a
// full `data: ...\n\n` block has been seen.

describe("parseSSEChunks", () => {
  it("buffers a data block split across chunk boundaries and emits once complete", () => {
    const parser = parseSSEChunks();

    // First chunk: one complete event ("grew") plus the start of a second
    // event's JSON, cut off mid-string (no closing `\n\n` yet).
    const first = parser.push('data: {"stage":"grew"}\n\ndata: {"sta');
    expect(first).toEqual([{ stage: "grew" }]);

    // Second chunk completes the buffered partial event.
    const second = parser.push('ge":"done"}\n\n');
    expect(second).toEqual([{ stage: "done" }]);
  });

  it("emits multiple complete events found in a single chunk", () => {
    const parser = parseSSEChunks();
    const events = parser.push(
      'data: {"stage":"thinking","concept":"fire"}\n\ndata: {"stage":"done"}\n\n'
    );
    expect(events).toEqual([
      { stage: "thinking", concept: "fire" },
      { stage: "done" },
    ]);
  });

  it("emits nothing when a chunk contains no complete event yet", () => {
    const parser = parseSSEChunks();
    const events = parser.push('data: {"stage":"thin');
    expect(events).toEqual([]);
  });

  it("ignores blank keep-alive lines between events", () => {
    const parser = parseSSEChunks();
    const events = parser.push('\n\ndata: {"stage":"done"}\n\n');
    expect(events).toEqual([{ stage: "done" }]);
  });
});
