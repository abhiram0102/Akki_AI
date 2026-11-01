import React, { useEffect, useRef, useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "wouter";
import { api } from "@/lib/api";

// ── Domain types ──────────────────────────────────────────────────────────────
interface SearchSession {
  id: string;
  title: string | null;
}

interface SearchMessage {
  id: string;
  sessionId: string;
  content: string | null;
}

interface SearchResult {
  sessions: SearchSession[];
  messages: SearchMessage[];
}


// ── Module-level shared state ────────────────────────────────────────────────
type Listener = (open: boolean) => void;
const listeners = new Set<Listener>();
let _isOpen = false;

function setOpen(next: boolean) {
  _isOpen = next;
  listeners.forEach((fn) => fn(next));
}

export function useGlobalSearch() {
  const [isOpen, setIsOpen] = useState(_isOpen);

  useEffect(() => {
    listeners.add(setIsOpen);
    return () => { listeners.delete(setIsOpen); };
  }, []);

  const open = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);

  return { isOpen, open, close };
}

// ── Highlight matched term ───────────────────────────────────────────────────
function Highlight({ text, query }: { text: string; query: string }) {
  if (!query || query.length < 2) return <>{text}</>;
  const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  const parts = text.split(regex);
  return (
    <>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark
            key={i}
            style={{
              background: "rgba(0,216,255,0.25)",
              color: "inherit",
              padding: 0,
            }}
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────
export function GlobalSearch() {
  const { isOpen, close } = useGlobalSearch();
  const [query, setQuery] = useState("");
  const [, navigate] = useLocation();
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset query when closed
  useEffect(() => {
    if (!isOpen) setQuery("");
  }, [isOpen]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [isOpen]);

  // Escape to close
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, close]);

  const { data, isFetching } = useQuery<SearchResult>({
    queryKey: ["/api/protected/search", query],
    queryFn: () =>
      api.get(`/api/protected/search?q=${encodeURIComponent(query)}`) as Promise<SearchResult>,
    enabled: query.trim().length >= 2,
    staleTime: 10_000,
  });

  const sessions: SearchSession[] = data?.sessions ?? [];
  const messages: SearchMessage[] = data?.messages ?? [];
  const hasResults = sessions.length > 0 || messages.length > 0;
  const noResults = query.trim().length >= 2 && !isFetching && !hasResults;

  function handleSessionClick(id: string) {
    navigate(`/?session=${id}`);
    close();
  }

  function handleMessageClick(sessionId: string) {
    navigate(`/?session=${sessionId}`);
    close();
  }

  if (!isOpen) return null;

  return (
    <div
      onClick={close}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(4,8,15,0.92)",
        zIndex: 9999,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: 80,
      }}
    >
      {/* Search box — stop propagation so clicks inside don't close */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 600,
          background: "rgba(8,13,26,0.98)",
          border: "1px solid rgba(0,216,255,0.3)",
          borderRadius: 16,
          padding: 20,
          boxSizing: "border-box",
        }}
      >
        {/* Input */}
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search sessions, messages…"
          style={{
            width: "100%",
            background: "transparent",
            border: "none",
            outline: "none",
            color: "#fff",
            fontFamily: "monospace",
            fontSize: 15,
            paddingBottom: 12,
            borderBottom:
              query.trim().length >= 2
                ? "1px solid rgba(0,216,255,0.2)"
                : "1px solid rgba(255,255,255,0.06)",
            marginBottom: 8,
            boxSizing: "border-box",
          }}
        />

        {/* Spinner */}
        {isFetching && (
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 11,
              color: "rgba(0,216,255,0.6)",
              paddingTop: 8,
            }}
          >
            Searching…
          </div>
        )}

        {/* No results */}
        {noResults && (
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 12,
              color: "rgba(255,255,255,0.35)",
              paddingTop: 12,
            }}
          >
            No results
          </div>
        )}

        {/* Sessions group */}
        {sessions.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 10,
                color: "rgba(0,216,255,0.55)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              Sessions
            </div>
            {sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => handleSessionClick(s.id)}
                style={{
                  padding: "8px 10px",
                  borderRadius: 8,
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontSize: 13,
                  color: "#e0e8ff",
                  marginBottom: 2,
                  background: "rgba(0,216,255,0.04)",
                  border: "1px solid transparent",
                  transition: "background 0.15s, border-color 0.15s",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background =
                    "rgba(0,216,255,0.1)";
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "rgba(0,216,255,0.18)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background =
                    "rgba(0,216,255,0.04)";
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "transparent";
                }}
              >
                <Highlight text={s.title ?? "Untitled"} query={query.trim()} />
              </div>
            ))}
          </div>
        )}

        {/* Messages group */}
        {messages.length > 0 && (
          <div style={{ marginTop: sessions.length > 0 ? 14 : 8 }}>
            <div
              style={{
                fontFamily: "monospace",
                fontSize: 10,
                color: "rgba(0,255,136,0.55)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              Messages
            </div>
            {messages.map((m) => (
              <div
                key={m.id}
                onClick={() => handleMessageClick(m.sessionId)}
                style={{
                  padding: "8px 10px",
                  borderRadius: 8,
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontSize: 12,
                  color: "rgba(255,255,255,0.75)",
                  marginBottom: 2,
                  background: "rgba(0,255,136,0.03)",
                  border: "1px solid transparent",
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                  transition: "background 0.15s, border-color 0.15s",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background =
                    "rgba(0,255,136,0.08)";
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "rgba(0,255,136,0.15)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background =
                    "rgba(0,255,136,0.03)";
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "transparent";
                }}
              >
                <Highlight
                  text={m.content ?? ""}
                  query={query.trim()}
                />
              </div>
            ))}
          </div>
        )}

        {/* Hint when idle */}
        {query.trim().length < 2 && !isFetching && (
          <div
            style={{
              fontFamily: "monospace",
              fontSize: 11,
              color: "rgba(255,255,255,0.2)",
              paddingTop: 8,
            }}
          >
            Type at least 2 characters to search
          </div>
        )}
      </div>
    </div>
  );
}
