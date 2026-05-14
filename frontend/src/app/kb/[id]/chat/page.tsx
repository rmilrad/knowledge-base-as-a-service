"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { isLoggedIn, getToken } from "@/lib/auth";

interface KnowledgeBase {
  id: string;
  name: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const MODELS = [
  { id: "claude-haiku-4-5", label: "Haiku 4.5", desc: "Fast" },
  { id: "claude-sonnet-4-5", label: "Sonnet 4.5", desc: "Balanced" },
  { id: "claude-opus-4-7", label: "Opus 4.7", desc: "Powerful" },
];

const STYLES = [
  { id: "concise", label: "Concise" },
  { id: "balanced", label: "Balanced" },
  { id: "comprehensive", label: "Comprehensive" },
];

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderMarkdown(text: string): string {
  let html = escapeHtml(text);
  // links
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  // bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // headers
  html = html.replace(
    /## ([^\n]+)/g,
    '<strong style="font-size:1.05em;display:block;margin:0.75em 0 0.25em">$1</strong>'
  );
  // bullet lists
  html = html.replace(/^- (.+)$/gm, '<span style="display:block;padding-left:1em">&#8226; $1</span>');
  return html;
}

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState("claude-sonnet-4-5");
  const [responseStyle, setResponseStyle] = useState("balanced");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isLoggedIn()) router.push("/login");
  }, [router]);

  const loadKb = useCallback(async () => {
    try {
      const data = await apiFetch<KnowledgeBase>(`/api/kb/${id}`);
      setKb(data);
    } catch {
      /* ignore */
    }
  }, [id]);

  useEffect(() => {
    loadKb();
  }, [loadKb]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function autoResize() {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/kb/${id}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          question,
          model,
          response_style: responseStyle,
        }),
      });

      if (!res.ok) throw new Error("Chat request failed");

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let assistantContent = "";

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "" },
      ]);

      if (reader) {
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              if (data === "[DONE]") continue;
              try {
                const parsed = JSON.parse(data);
                if (parsed.type === "token") {
                  assistantContent += parsed.content;
                  setMessages((prev) => {
                    const updated = [...prev];
                    updated[updated.length - 1] = {
                      role: "assistant",
                      content: assistantContent,
                    };
                    return updated;
                  });
                }
              } catch {
                // skip malformed
              }
            }
          }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          role: "assistant",
          content: "Something went wrong. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <>
      <nav>
        <h1>
          <Link href="/dashboard">KBaaS</Link>
          {kb && (
            <>
              {" / "}
              <Link href={`/kb/${id}`}>{kb.name}</Link>
            </>
          )}
        </h1>
      </nav>

      <div className="tabs">
        <Link href={`/kb/${id}`}>Sources</Link>
        <Link href={`/kb/${id}/chat`} className="active">
          Chat
        </Link>
        <Link href={`/kb/${id}/settings`}>Settings</Link>
      </div>

      <div className="chat-container">
        <div className="messages">
          {messages.length === 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                gap: "0.5rem",
              }}
            >
              <span style={{ fontSize: "2rem" }}>&#9672;</span>
              <p style={{ color: "var(--text-tertiary)", fontSize: "1rem" }}>
                Ask anything about your knowledge base
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              {msg.role === "assistant" && !msg.content && loading ? (
                <div className="thinking-dots">
                  <span />
                  <span />
                  <span />
                </div>
              ) : (
                <div
                  className="content"
                  style={{ whiteSpace: "pre-wrap" }}
                  dangerouslySetInnerHTML={{
                    __html:
                      msg.role === "assistant"
                        ? renderMarkdown(msg.content)
                        : escapeHtml(msg.content),
                  }}
                />
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-controls">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} &mdash; {m.desc}
                </option>
              ))}
            </select>
            <select
              value={responseStyle}
              onChange={(e) => setResponseStyle(e.target.value)}
            >
              {STYLES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="chat-input-wrapper">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  autoResize();
                }}
                onKeyDown={handleKeyDown}
                placeholder="Message..."
                disabled={loading}
                rows={1}
              />
              <button
                type="submit"
                className="chat-send-btn"
                disabled={loading || !input.trim()}
                aria-label="Send"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
