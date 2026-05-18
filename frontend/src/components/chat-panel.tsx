"use client";

import { useState, useRef, useEffect } from "react";
import { getToken } from "@/lib/auth";

interface Message {
  role: "user" | "assistant";
  content: string;
  deepDive?: DeepDiveState;
}

interface DeepDiveSource {
  url: string;
  title: string;
  description: string;
  source: string;
  selected?: boolean;
}

interface DeepDiveState {
  status: "idle" | "searching" | "streaming" | "done";
  statusMessage: string;
  content: string;
  sources: DeepDiveSource[];
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
  const codeBlocks: string[] = [];
  let processed = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(
      `<pre style="background:var(--bg-tertiary,#1e1e1e);border:1px solid var(--border);border-radius:6px;padding:0.75rem;overflow-x:auto;font-size:0.8rem;margin:0.5rem 0"><code>${escapeHtml(code.trimEnd())}</code></pre>`
    );
    return `__CODE_BLOCK_${idx}__`;
  });

  const inlineCode: string[] = [];
  processed = processed.replace(/`([^`]+)`/g, (_match, code) => {
    const idx = inlineCode.length;
    inlineCode.push(
      `<code style="background:var(--bg-tertiary,#1e1e1e);padding:0.1rem 0.35rem;border-radius:3px;font-size:0.85em">${escapeHtml(code)}</code>`
    );
    return `__INLINE_CODE_${idx}__`;
  });

  let html = escapeHtml(processed);

  codeBlocks.forEach((block, i) => {
    html = html.replace(`__CODE_BLOCK_${i}__`, block);
  });
  inlineCode.forEach((code, i) => {
    html = html.replace(`__INLINE_CODE_${i}__`, code);
  });

  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_match: string, text: string, url: string) => {
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
}

export default function ChatPanel({ kbId, kbName }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState("claude-sonnet-4-5");
  const [responseStyle, setResponseStyle] = useState("balanced");
  const [addingUrls, setAddingUrls] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  }, []);

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

  // ---- Deep Dive ----

  async function handleDeepDive(msgIndex: number) {
    const msg = messages[msgIndex];
    if (!msg || msg.role !== "assistant") return;

    let question = "";
    for (let i = msgIndex - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        question = messages[i].content;
        break;
      }
    }
    if (!question) return;

    setMessages((prev) => {
      const updated = [...prev];
      updated[msgIndex] = {
        ...updated[msgIndex],
        deepDive: {
          status: "searching",
          statusMessage: "Searching the web for more information...",
          content: "",
          sources: [],
        },
      };
      return updated;
    });

    try {
      const res = await fetch(`${API_URL}/api/kb/${kbId}/deep-dive`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          question,
          current_answer: msg.content,
        }),
      });

      if (!res.ok) throw new Error("Deep dive failed");

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let deepDiveContent = "";

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
                if (parsed.type === "status") {
                  setMessages((prev) => {
                    const updated = [...prev];
                    const dd = { ...updated[msgIndex].deepDive! };
                    dd.statusMessage = parsed.message;
                    dd.status = "searching";
                    updated[msgIndex] = { ...updated[msgIndex], deepDive: dd };
                    return updated;
                  });
                } else if (parsed.type === "token") {
                  deepDiveContent += parsed.content;
                  setMessages((prev) => {
                    const updated = [...prev];
                    const dd = { ...updated[msgIndex].deepDive! };
                    dd.content = deepDiveContent;
                    dd.status = "streaming";
                    updated[msgIndex] = { ...updated[msgIndex], deepDive: dd };
                    return updated;
                  });
                } else if (parsed.type === "sources_found") {
                  setMessages((prev) => {
                    const updated = [...prev];
                    const dd = { ...updated[msgIndex].deepDive! };
                    dd.sources = (parsed.sources || []).map((s: DeepDiveSource) => ({
                      ...s,
                      selected: false,
                    }));
                    dd.status = "done";
                    updated[msgIndex] = { ...updated[msgIndex], deepDive: dd };
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

      setMessages((prev) => {
        const updated = [...prev];
        if (updated[msgIndex].deepDive && updated[msgIndex].deepDive!.status !== "done") {
          const dd = { ...updated[msgIndex].deepDive! };
          dd.status = "done";
          updated[msgIndex] = { ...updated[msgIndex], deepDive: dd };
        }
        return updated;
      });
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        const dd = { ...updated[msgIndex].deepDive! };
        dd.content = "Deep dive failed. Please try again.";
        dd.status = "done";
        dd.sources = [];
        updated[msgIndex] = { ...updated[msgIndex], deepDive: dd };
        return updated;
      });
    }
  }

  function toggleDeepDiveSource(msgIndex: number, srcIndex: number) {
    setMessages((prev) => {
      const updated = [...prev];
      const dd = { ...updated[msgIndex].deepDive! };
      const sources = [...dd.sources];
      sources[srcIndex] = { ...sources[srcIndex], selected: !sources[srcIndex].selected };
      dd.sources = sources;
      updated[msgIndex] = { ...updated[msgIndex], deepDive: dd };
      return updated;
    });
  }

  function selectAllDeepDiveSources(msgIndex: number, selected: boolean) {
    setMessages((prev) => {
      const updated = [...prev];
      const dd = { ...updated[msgIndex].deepDive! };
      dd.sources = dd.sources.map((s) => ({ ...s, selected }));
      updated[msgIndex] = { ...updated[msgIndex], deepDive: dd };
      return updated;
    });
  }

  async function handleAddDeepDiveSources(msgIndex: number) {
    const dd = messages[msgIndex]?.deepDive;
    if (!dd) return;
    const selectedUrls = dd.sources.filter((s) => s.selected).map((s) => s.url);
    if (selectedUrls.length === 0) return;

    setAddingUrls(true);
    try {
      const res = await fetch(`${API_URL}/api/kb/${kbId}/documents/urls`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ urls: selectedUrls }),
      });
      if (!res.ok) throw new Error("Failed to add URLs");

      setMessages((prev) => {
        const updated = [...prev];
        const ddState = { ...updated[msgIndex].deepDive! };
        ddState.sources = ddState.sources.map((s) => ({
          ...s,
          selected: false,
        }));
        updated[msgIndex] = { ...updated[msgIndex], deepDive: ddState };
        return updated;
      });
    } catch {
      // silently fail
    } finally {
      setAddingUrls(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <div className="chat-full">
      {/* Controls bar */}
      <div className="chat-full-controls">
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

      {/* Messages */}
      <div className="chat-full-messages">
        {messages.length === 0 && (
          <div className="chat-full-empty">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.2 }}>
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <p>Ask anything about <strong>{kbName}</strong></p>
            <span>Your answers will be grounded in the documents in this knowledge base.</span>
          </div>
        )}
        <div className="chat-full-thread">
          {messages.map((msg, i) => (
            <div key={i} className={`chat-bubble ${msg.role}`}>
              {msg.role === "assistant" && !msg.content && loading ? (
                <div className="thinking-dots">
                  <span /><span /><span />
                </div>
              ) : (
                <>
                  <div
                    className="chat-bubble-content"
                    style={{ whiteSpace: "pre-wrap" }}
                    dangerouslySetInnerHTML={{
                      __html: msg.role === "assistant"
                        ? renderMarkdown(msg.content)
                        : escapeHtml(msg.content),
                    }}
                  />
                  {/* Deep Dive button + results */}
                  {msg.role === "assistant" && msg.content && !loading && (
                    <div className="deep-dive-container">
                      {!msg.deepDive && (
                        <button
                          className="deep-dive-btn"
                          onClick={() => handleDeepDive(i)}
                          title="Search the web for more information about this topic"
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <circle cx="11" cy="11" r="8" />
                            <line x1="21" y1="21" x2="16.65" y2="16.65" />
                          </svg>
                          Deep Dive
                        </button>
                      )}

                      {msg.deepDive && (
                        <>
                          {msg.deepDive.status === "searching" && (
                            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", margin: "0.75rem 0" }}>
                              <span className="deep-dive-spinner" style={{ display: "inline-block", verticalAlign: "middle", marginRight: 6 }} />
                              {msg.deepDive.statusMessage}
                            </p>
                          )}

                          {msg.deepDive.content && (
                            <div style={{ margin: "0.75rem 0", padding: "0.75rem 1rem", background: "var(--bg-secondary)", borderRadius: "var(--radius-md)", borderLeft: "3px solid var(--accent)" }}>
                              <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: 6 }}>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                  <circle cx="12" cy="12" r="10" />
                                  <line x1="2" y1="12" x2="22" y2="12" />
                                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                                </svg>
                                Web Insights
                                {msg.deepDive.status === "streaming" && (
                                  <span className="deep-dive-spinner" style={{ marginLeft: "auto" }} />
                                )}
                              </div>
                              <div
                                style={{ fontSize: "0.82rem", lineHeight: 1.55, whiteSpace: "pre-wrap", maxHeight: 400, overflowY: "auto" }}
                                dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.deepDive.content) }}
                              />
                            </div>
                          )}

                          {msg.deepDive.status === "done" && msg.deepDive.sources.length > 0 && (
                            <div style={{ margin: "0.75rem 0" }}>
                              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "0.5rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <span>
                                  <strong>Sources found</strong>{" "}
                                  <span style={{ fontSize: "0.7rem", color: "var(--accent)", fontWeight: 600 }}>
                                    {msg.deepDive.sources.length}
                                  </span>
                                </span>
                                <span style={{ display: "flex", gap: "0.5rem" }}>
                                  <button onClick={() => selectAllDeepDiveSources(i, true)} style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer" }}>Select all</button>
                                  <button onClick={() => selectAllDeepDiveSources(i, false)} style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer" }}>Clear</button>
                                </span>
                              </div>
                              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
                                <tbody>
                                  {msg.deepDive.sources.map((src, si) => (
                                    <tr
                                      key={si}
                                      onClick={() => toggleDeepDiveSource(i, si)}
                                      style={{
                                        cursor: "pointer",
                                        background: src.selected ? "var(--accent-light)" : "transparent",
                                      }}
                                    >
                                      <td style={{ width: 28, padding: "6px 4px 6px 0", verticalAlign: "top" }}>
                                        <input
                                          type="checkbox"
                                          checked={src.selected || false}
                                          onChange={() => toggleDeepDiveSource(i, si)}
                                          style={{ accentColor: "var(--accent)" }}
                                        />
                                      </td>
                                      <td style={{ padding: "6px 0" }}>
                                        <div
                                          style={{ color: "var(--link)", fontWeight: 500, cursor: "pointer" }}
                                          onClick={(e) => { e.stopPropagation(); window.open(src.url, "_blank"); }}
                                        >
                                          {src.title || src.url}
                                        </div>
                                        <div style={{ color: "var(--text-tertiary)", fontSize: "0.68rem", opacity: 0.6, marginTop: 2 }}>
                                          {src.url}
                                        </div>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              {msg.deepDive.sources.some((s) => s.selected) && (
                                <button
                                  onClick={() => handleAddDeepDiveSources(i)}
                                  disabled={addingUrls}
                                  style={{
                                    marginTop: 8,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: 6,
                                    width: "100%",
                                    padding: "0.5rem",
                                    fontSize: "0.78rem",
                                    fontWeight: 600,
                                    color: "#fff",
                                    background: "var(--accent)",
                                    border: "none",
                                    borderRadius: 8,
                                    cursor: "pointer",
                                  }}
                                >
                                  {addingUrls ? "Adding..." : `Add ${msg.deepDive.sources.filter((s) => s.selected).length} source${msg.deepDive.sources.filter((s) => s.selected).length !== 1 ? "s" : ""} to KB`}
                                </button>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="chat-full-input-area">
        <form onSubmit={handleSubmit}>
          <div className="chat-full-input-wrapper">
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
