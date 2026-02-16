"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import Markdown from "react-markdown";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const SUGGESTIONS = [
  "Recommend a warm beach destination for a week in March",
  "What should I pack for a trip to Tokyo in spring?",
  "What are the must-see attractions in Barcelona?",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function generateId(): string {
  return Math.random().toString(36).substring(2, 12);
}


// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [threadId, setThreadId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Generate thread ID on mount
  useEffect(() => {
    setThreadId(generateId());
  }, []);

  // Scroll: when loading starts, scroll to typing indicator at bottom.
  // When a new message arrives, scroll to the START of that message.
  useEffect(() => {
    if (isLoading) {
      // User just sent a message — scroll to bottom to show typing indicator
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [isLoading]);

  useEffect(() => {
    if (messages.length > 0) {
      // Scroll to the top of the latest message so user reads from the beginning
      lastMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height =
        Math.min(inputRef.current.scrollHeight, 120) + "px";
    }
  }, [input]);

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: text.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setError(null);
    setIsLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMessage.content,
          thread_id: threadId,
        }),
      });

      if (!res.ok) {
        throw new Error(`Server error (${res.status})`);
      }

      const data = await res.json();

      // Update thread_id if server assigned one
      if (data.thread_id) {
        setThreadId(data.thread_id);
      }

      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: data.response,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorMsg =
        err instanceof Error ? err.message : "Failed to send message";
      setError(errorMsg);
    } finally {
      setIsLoading(false);
      // Re-focus input
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  function handleNewChat() {
    setMessages([]);
    setThreadId(generateId());
    setError(null);
    inputRef.current?.focus();
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="border-b border-border bg-surface/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="flex items-center justify-between px-4 md:px-8 py-3 max-w-5xl mx-auto w-full">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-white font-bold text-sm">
              TA
            </div>
            <div>
              <h1 className="text-base font-semibold leading-tight">
                Travel Assistant
              </h1>
              <p className="text-xs text-muted">
                AI-powered trip planning
              </p>
            </div>
          </div>
          {!isEmpty && (
            <button
              onClick={handleNewChat}
              className="text-xs text-muted hover:text-foreground transition-colors px-3 py-1.5 rounded-md hover:bg-primary-light"
            >
              New chat
            </button>
          )}
        </div>
      </header>

      {/* Messages area */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 md:px-8 py-6">
          {isEmpty ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center min-h-[calc(100vh-10rem)] text-center">
              <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center mb-6">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-10 h-10 text-primary"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5a17.92 17.92 0 01-8.716-2.247m0 0A8.966 8.966 0 013 12c0-1.04.177-2.04.502-2.971"
                  />
                </svg>
              </div>
              <h2 className="text-2xl md:text-3xl font-semibold mb-3">
                Where would you like to go?
              </h2>
              <p className="text-muted text-sm md:text-base mb-8 max-w-lg">
                I can help with destination recommendations, packing lists,
                local attractions, and more.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 w-full max-w-3xl">
                {SUGGESTIONS.map((suggestion, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(suggestion)}
                    className="text-left text-sm px-5 py-4 rounded-xl border border-border hover:border-primary/40 hover:bg-primary-light/50 transition-all"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* Message list */
            <div className="flex flex-col gap-5">
              {messages.map((msg, idx) => (
                <div
                  key={msg.id}
                  ref={idx === messages.length - 1 ? lastMessageRef : undefined}
                  className={`flex ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  <div
                    className={`rounded-2xl px-5 py-3 text-sm md:text-base leading-relaxed ${
                      msg.role === "user"
                        ? "bg-primary text-white rounded-br-md max-w-[75%] lg:max-w-[60%]"
                        : "bg-surface border border-border rounded-bl-md assistant-message max-w-[90%] lg:max-w-[75%]"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <Markdown>{msg.content}</Markdown>
                    ) : (
                      msg.content
                    )}
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-surface border border-border rounded-2xl rounded-bl-md px-5 py-3 flex gap-1.5 items-center">
                    <span className="typing-dot w-2 h-2 bg-muted rounded-full" />
                    <span className="typing-dot w-2 h-2 bg-muted rounded-full" />
                    <span className="typing-dot w-2 h-2 bg-muted rounded-full" />
                  </div>
                </div>
              )}

              {/* Error message */}
              {error && (
                <div className="flex justify-center">
                  <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-xs px-4 py-2 rounded-lg">
                    {error} &mdash;{" "}
                    <button
                      onClick={() => setError(null)}
                      className="underline hover:no-underline"
                    >
                      dismiss
                    </button>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </main>

      {/* Input bar */}
      <footer className="border-t border-border bg-surface/80 backdrop-blur-sm sticky bottom-0">
        <div className="max-w-5xl mx-auto px-4 md:px-8 py-3">
          <form
            onSubmit={handleSubmit}
            className="flex items-end gap-3"
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about destinations, packing, attractions..."
              rows={1}
              disabled={isLoading}
              className="flex-1 resize-none rounded-xl border border-border bg-background px-4 py-2.5 text-sm md:text-base placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary disabled:opacity-50 transition-all"
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="shrink-0 w-10 h-10 md:w-11 md:h-11 rounded-xl bg-primary text-white flex items-center justify-center hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-4 h-4 md:w-5 md:h-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
                />
              </svg>
            </button>
          </form>
          <p className="text-center text-[10px] text-muted mt-2">
            Travel Assistant may make mistakes. Verify important details independently.
          </p>
        </div>
      </footer>
    </div>
  );
}
