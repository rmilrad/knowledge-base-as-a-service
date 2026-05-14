"use client";

import { useState, useRef, useEffect } from "react";
import { getToken } from "@/lib/auth";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const MODELS = [
  { id: "claude-haiku-4-5", label: "Haiku 4.5", desc: "Fast" },
  { id: "claude-sonnet-4-5", label: "Sonnet 4.5", desc: "Balanced" },
  { id: "claude-opus-4-7", label: "Opus 4.7", desc: "Powerful" },
];

const STYLES = [
  { id: "concise", label: "Concise" },
  { id: "balanced", label: "Balanced" },
  { id: "comprehensive", label: "Detailed" },
];

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderMarkdown(text: string): string {
  let html = escapeHtml(text);
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_match: string, text: string, url: string) => {
      // Only allow http/https URLs to prevent javascript: XSS
      if (/^https?:\/\//i.test(url)) {
        return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`;
      }
      return `${text} (${url})`;
    }
  );
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(
    /## ([^\n]+)/g,
    '<strong style="font-size:1.05em;display:block;margin:0.75em 0 0.25em">$1</strong>'
  );
  html = html.replace(/^- (.+)$/gm, '<span style="display:block;padding-left:1em">&bull; $1</span>');
  return html;
}

interface ChatPanelProps {
  kbId: string;
  kbName: string;
  open: boolean;
  onClose: () => void;
}

export default function ChatPanel({ kbId, kbName, open, onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState("claude-sonnet-4-5");
  const [responseStyle, setResponseStyle] = useState("balanced");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (open && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [open]);

  // Reset messages when KB changes
  useEffect(() => {
    setMessages([]);
  }, [kbId]);

  function autoResize() {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/kb/${kbId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ question, model, response_style: responseStyle }),
      });

      if (!res.ok) throw new Error("Chat request failed");

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let assistantContent = "";

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

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
                /* skip */
              }
            }
          }
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: "assistant", content: "Something went wrong. Please try again." },
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

  if (!open) return null;

  return (
    <div className="chat-panel">
      <div className="chat-panel-header">
        <div>
          <h3 className="chat-panel-title">Chat</h3>
          <span className="chat-panel-kb">{kbName}</span>
        </div>
        <button className="chat-panel-close" onClick={onClose} aria-label="Close chat">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="chat-panel-controls">
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {MODELS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label} &mdash; {m.desc}
            </option>
          ))}
        </select>
        <select value={responseStyle} onChange={(e) => setResponseStyle(e.target.value)}>
          {STYLES.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      <div className="chat-panel-messages">
        {messages.length === 0 && (
          <div className="chat-panel-empty">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3 }}>
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <p>Ask anything about this knowledge base</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg ${msg.role}`}>
            {msg.role === "assistant" && !msg.content && loading ? (
              <div className="thinking-dots">
                <span /><span /><span />
              </div>
            ) : (
              <div
                className="chat-msg-content"
                style={{ whiteSpace: "pre-wrap" }}
                dangerouslySetInnerHTML={{
                  __html: msg.role === "assistant"
                    ? renderMarkdown(msg.content)
                    : escapeHtml(msg.content),
                }}
              />
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-panel-input-area">
        <form onSubmit={handleSubmit}>
          <div className="chat-panel-input-wrapper">
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
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
