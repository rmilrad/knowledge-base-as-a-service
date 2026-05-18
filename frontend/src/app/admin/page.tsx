"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { isLoggedIn } from "@/lib/auth";

interface AdminStats {
  totals: {
    users: number;
    knowledge_bases: number;
    documents: number;
    chunks: number;
    storage_bytes: number;
  };
  doc_statuses: Record<string, number>;
  recent_users: {
    id: string;
    email: string;
    name: string | null;
    created_at: string | null;
  }[];
  top_kbs: {
    id: string;
    name: string;
    document_count: number;
    chunk_count: number;
    owner_email: string;
  }[];
  recent_docs: {
    id: string;
    title: string | null;
    status: string;
    file_type: string | null;
    chunk_count: number;
    created_at: string | null;
    kb_name: string;
  }[];
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "-";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function AdminPage() {
  const router = useRouter();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    apiFetch<AdminStats>("/api/admin/stats")
      .then(setStats)
      .catch((err) => setError(err instanceof Error ? err.message : "Access denied"))
      .finally(() => setLoading(false));
  }, [router]);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", background: "var(--shell-bg)", fontFamily: "var(--font-sans)" }}>
        <p style={{ color: "var(--text-tertiary)" }}>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", height: "100vh", gap: "1rem", background: "var(--shell-bg)", fontFamily: "var(--font-sans)" }}>
        <p style={{ color: "var(--error)", fontSize: "1.1rem" }}>{error}</p>
        <Link href="/dashboard" style={{ color: "var(--accent)", textDecoration: "none" }}>Back to Dashboard</Link>
      </div>
    );
  }

  if (!stats) return null;

  const cardStyle: React.CSSProperties = {
    background: "var(--bg-primary)",
    borderRadius: "var(--radius-md)",
    padding: "1.25rem",
    boxShadow: "var(--shadow-card)",
    border: "1px solid var(--border-light)",
  };

  const statCardStyle: React.CSSProperties = {
    ...cardStyle,
    textAlign: "center" as const,
    display: "flex",
    flexDirection: "column" as const,
    gap: "0.25rem",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: "0.75rem",
    color: "var(--text-tertiary)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
    fontWeight: 500,
  };

  const valueStyle: React.CSSProperties = {
    fontSize: "2rem",
    fontWeight: 600,
    color: "var(--text-primary)",
    lineHeight: 1.2,
  };

  const thStyle: React.CSSProperties = {
    textAlign: "left" as const,
    padding: "0.5rem 0.75rem",
    fontSize: "0.75rem",
    color: "var(--text-tertiary)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
    fontWeight: 500,
    borderBottom: "1px solid var(--border)",
  };

  const tdStyle: React.CSSProperties = {
    padding: "0.5rem 0.75rem",
    fontSize: "0.85rem",
    borderBottom: "1px solid var(--border-light)",
    color: "var(--text-primary)",
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--shell-bg)", fontFamily: "var(--font-sans)" }}>
      {/* Header */}
      <div style={{
        background: "var(--bg-primary)",
        borderBottom: "1px solid var(--border)",
        padding: "0.75rem 1.5rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Link href="/dashboard" style={{ color: "var(--text-tertiary)", textDecoration: "none", fontSize: "0.85rem" }}>
            KBaaS
          </Link>
          <span style={{ color: "var(--border)" }}>/</span>
          <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Admin Dashboard</span>
        </div>
        <Link href="/dashboard" style={{ color: "var(--accent)", textDecoration: "none", fontSize: "0.85rem" }}>
          Back to App
        </Link>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "1.5rem" }}>

        {/* Stat Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "1rem", marginBottom: "1.5rem" }}>
          <div style={statCardStyle}>
            <span style={labelStyle}>Users</span>
            <span style={valueStyle}>{stats.totals.users}</span>
          </div>
          <div style={statCardStyle}>
            <span style={labelStyle}>Knowledge Bases</span>
            <span style={valueStyle}>{stats.totals.knowledge_bases}</span>
          </div>
          <div style={statCardStyle}>
            <span style={labelStyle}>Documents</span>
            <span style={valueStyle}>{stats.totals.documents}</span>
          </div>
          <div style={statCardStyle}>
            <span style={labelStyle}>Chunks</span>
            <span style={valueStyle}>{stats.totals.chunks.toLocaleString()}</span>
          </div>
          <div style={statCardStyle}>
            <span style={labelStyle}>Storage</span>
            <span style={valueStyle}>{formatBytes(stats.totals.storage_bytes)}</span>
          </div>
        </div>

        {/* Doc Status Breakdown */}
        {Object.keys(stats.doc_statuses).length > 0 && (
          <div style={{ ...cardStyle, marginBottom: "1.5rem" }}>
            <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.75rem", color: "var(--text-primary)" }}>Document Status Breakdown</h3>
            <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
              {Object.entries(stats.doc_statuses).map(([status, count]) => (
                <div key={status} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span className={`badge ${status}`} style={{ fontSize: "0.75rem" }}>{status}</span>
                  <span style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text-primary)" }}>{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Two-column layout for tables */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>

          {/* Recent Users */}
          <div style={cardStyle}>
            <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.75rem", color: "var(--text-primary)" }}>Recent Users</h3>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Email</th>
                    <th style={thStyle}>Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_users.map((u) => (
                    <tr key={u.id}>
                      <td style={tdStyle}>
                        <div style={{ fontWeight: 500 }}>{u.email}</div>
                        {u.name && <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{u.name}</div>}
                      </td>
                      <td style={{ ...tdStyle, whiteSpace: "nowrap", color: "var(--text-secondary)" }}>{timeAgo(u.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Top Knowledge Bases */}
          <div style={cardStyle}>
            <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.75rem", color: "var(--text-primary)" }}>Top Knowledge Bases</h3>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Name</th>
                    <th style={thStyle}>Docs</th>
                    <th style={thStyle}>Chunks</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.top_kbs.map((kb) => (
                    <tr key={kb.id}>
                      <td style={tdStyle}>
                        <div style={{ fontWeight: 500 }}>{kb.name}</div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{kb.owner_email}</div>
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>{kb.document_count}</td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>{kb.chunk_count.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Recent Documents */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.75rem", color: "var(--text-primary)" }}>Recent Documents</h3>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle}>Title</th>
                  <th style={thStyle}>KB</th>
                  <th style={thStyle}>Type</th>
                  <th style={thStyle}>Status</th>
                  <th style={thStyle}>Chunks</th>
                  <th style={thStyle}>Added</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_docs.map((doc) => (
                  <tr key={doc.id}>
                    <td style={{ ...tdStyle, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {doc.title || "Untitled"}
                    </td>
                    <td style={{ ...tdStyle, color: "var(--text-secondary)", fontSize: "0.8rem" }}>{doc.kb_name}</td>
                    <td style={{ ...tdStyle, color: "var(--text-secondary)", fontSize: "0.8rem" }}>{doc.file_type || "-"}</td>
                    <td style={tdStyle}><span className={`badge ${doc.status}`}>{doc.status}</span></td>
                    <td style={{ ...tdStyle, textAlign: "center" }}>{doc.chunk_count}</td>
                    <td style={{ ...tdStyle, whiteSpace: "nowrap", color: "var(--text-secondary)" }}>{timeAgo(doc.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}
