"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { isLoggedIn, clearToken } from "@/lib/auth";

interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  status: string;
  document_count: number;
  chunk_count: number;
  created_at: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    loadKBs();
  }, [router]);

  async function loadKBs() {
    try {
      const data = await apiFetch<KnowledgeBase[]>("/api/kb");
      setKbs(data);
    } catch {
      setError("Failed to load knowledge bases");
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiFetch("/api/kb", {
        method: "POST",
        body: JSON.stringify({ name, description }),
      });
      setName("");
      setDescription("");
      setShowForm(false);
      loadKBs();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create");
    }
  }

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <>
      <nav>
        <h1>KBaaS</h1>
        <button onClick={handleLogout}>Log Out</button>
      </nav>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
        }}
      >
        <h2>Your Knowledge Bases</h2>
        <button className="primary" onClick={() => setShowForm(!showForm)}>
          + New Knowledge Base
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{
            border: "1px solid #ddd",
            padding: "1.25rem",
            borderRadius: 8,
            marginBottom: "1.5rem",
          }}
        >
          <div className="form-group">
            <label>Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="e.g. Company Wiki"
            />
          </div>
          <div className="form-group">
            <label>Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="What is this knowledge base about?"
            />
          </div>
          <button type="submit" className="primary">
            Create
          </button>
          <button
            type="button"
            onClick={() => setShowForm(false)}
            style={{ marginLeft: "0.5rem" }}
          >
            Cancel
          </button>
        </form>
      )}

      {kbs.length === 0 && !showForm ? (
        <p style={{ color: "#666" }}>
          No knowledge bases yet. Create one to get started.
        </p>
      ) : (
        <div className="grid">
          {kbs.map((kb) => (
            <Link
              key={kb.id}
              href={`/kb/${kb.id}`}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div className="card">
                <h3>{kb.name}</h3>
                {kb.description && (
                  <p style={{ color: "#666", fontSize: "0.9rem" }}>
                    {kb.description}
                  </p>
                )}
                <div style={{ marginTop: "0.75rem", fontSize: "0.85rem" }}>
                  <span className={`badge ${kb.status}`}>{kb.status}</span>
                  <span style={{ marginLeft: "0.75rem", color: "#666" }}>
                    {kb.document_count} docs &middot; {kb.chunk_count} chunks
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
