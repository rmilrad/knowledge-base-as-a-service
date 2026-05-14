"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { isLoggedIn } from "@/lib/auth";
import AppLayout from "@/components/app-layout";

interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  status: string;
  document_count: number;
  chunk_count: number;
  created_at: string;
}

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [showForm, setShowForm] = useState(searchParams.get("new") === "1");
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

  return (
    <AppLayout onNewKB={() => setShowForm(true)}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Knowledge Bases</h2>
        <button className="primary" onClick={() => setShowForm(!showForm)}>
          + New
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{
            border: `1px solid var(--border)`,
            padding: "1.25rem",
            borderRadius: "var(--radius-md)",
            marginBottom: "1.5rem",
            background: "var(--bg-secondary)",
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
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="submit" className="primary">Create</button>
            <button type="button" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </form>
      )}

      {kbs.length === 0 && !showForm ? (
        <div style={{
          textAlign: "center",
          padding: "4rem 2rem",
          color: "var(--text-tertiary)",
        }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3, marginBottom: "1rem" }}>
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <p style={{ fontSize: "1rem" }}>No knowledge bases yet</p>
          <p style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>Create one to get started</p>
        </div>
      ) : (
        <div className="grid">
          {kbs.map((kb) => (
            <Link
              key={kb.id}
              href={`/kb/${kb.id}`}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div className="card">
                <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>{kb.name}</h3>
                {kb.description && (
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>
                    {kb.description}
                  </p>
                )}
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", fontSize: "0.8rem" }}>
                  <span className={`badge ${kb.status}`}>{kb.status}</span>
                  <span style={{ color: "var(--text-tertiary)" }}>
                    {kb.document_count} docs &middot; {kb.chunk_count} chunks
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppLayout>
  );
}

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardContent />
    </Suspense>
  );
}
