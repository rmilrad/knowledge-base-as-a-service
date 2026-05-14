"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { isLoggedIn } from "@/lib/auth";

interface ApiKey {
  id: string;
  name: string | null;
  key_prefix: string;
  last_used_at: string | null;
  created_at: string;
}

export default function SettingsPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState("");

  const loadKeys = useCallback(async () => {
    try {
      const data = await apiFetch<ApiKey[]>(`/api/kb/${id}/keys`);
      setKeys(data);
    } catch {
      setError("Failed to load API keys");
    }
  }, [id]);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    loadKeys();
  }, [router, loadKeys]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const data = await apiFetch<{ key: string }>(`/api/kb/${id}/keys`, {
        method: "POST",
        body: JSON.stringify({ name: keyName || null }),
      });
      setNewKey(data.key);
      setKeyName("");
      loadKeys();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create key");
    }
  }

  async function handleRevoke(keyId: string) {
    try {
      await apiFetch(`/api/kb/${id}/keys/${keyId}`, { method: "DELETE" });
      loadKeys();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to revoke key");
    }
  }

  const mcpConfig = JSON.stringify(
    {
      mcpServers: {
        kbaas: {
          url: "http://localhost:3001/mcp",
          headers: {
            Authorization: `Bearer ${newKey || "kb_your-api-key"}`,
          },
        },
      },
    },
    null,
    2
  );

  return (
    <>
      <nav>
        <h1>
          <Link href="/dashboard">KBaaS</Link> /{" "}
          <Link href={`/kb/${id}`}>KB</Link> / Settings
        </h1>
      </nav>

      <div className="tabs">
        <Link href={`/kb/${id}`}>Sources</Link>
        <Link href={`/kb/${id}/chat`}>Chat</Link>
        <Link href={`/kb/${id}/settings`} className="active">
          Settings
        </Link>
      </div>

      {error && <p className="error">{error}</p>}

      <h3>API Keys</h3>
      <p style={{ color: "#666", marginBottom: "1rem" }}>
        Use API keys to query this knowledge base programmatically or via MCP.
      </p>

      <form
        onSubmit={handleCreate}
        style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}
      >
        <input
          value={keyName}
          onChange={(e) => setKeyName(e.target.value)}
          placeholder="Key name (optional)"
          style={{ maxWidth: 300 }}
        />
        <button type="submit" className="primary">
          Create API Key
        </button>
      </form>

      {newKey && (
        <div
          style={{
            background: "#fffbdd",
            border: "1px solid #e6d421",
            padding: "1rem",
            borderRadius: 8,
            marginBottom: "1rem",
          }}
        >
          <strong>New API Key (copy now — it won&apos;t be shown again):</strong>
          <pre
            style={{
              background: "#f5f5f5",
              padding: "0.5rem",
              marginTop: "0.5rem",
              borderRadius: 4,
              overflowX: "auto",
            }}
          >
            {newKey}
          </pre>
          <button
            onClick={() => {
              navigator.clipboard.writeText(newKey);
            }}
            style={{ marginTop: "0.5rem" }}
          >
            Copy
          </button>
        </div>
      )}

      {keys.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "2rem" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #eee", textAlign: "left" }}>
              <th style={{ padding: "0.5rem" }}>Name</th>
              <th style={{ padding: "0.5rem" }}>Prefix</th>
              <th style={{ padding: "0.5rem" }}>Created</th>
              <th style={{ padding: "0.5rem" }}></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "0.5rem" }}>{k.name || "—"}</td>
                <td style={{ padding: "0.5rem" }}>
                  <code>{k.key_prefix}...</code>
                </td>
                <td style={{ padding: "0.5rem" }}>
                  {new Date(k.created_at).toLocaleDateString()}
                </td>
                <td style={{ padding: "0.5rem" }}>
                  <button
                    className="danger"
                    style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                    onClick={() => handleRevoke(k.id)}
                  >
                    Revoke
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>MCP Connection</h3>
      <p style={{ color: "#666", marginBottom: "0.5rem" }}>
        Add this to your Claude Desktop or MCP client configuration:
      </p>
      <pre
        style={{
          background: "#f5f5f5",
          padding: "1rem",
          borderRadius: 8,
          overflowX: "auto",
          fontSize: "0.85rem",
        }}
      >
        {mcpConfig}
      </pre>
      <button
        onClick={() => navigator.clipboard.writeText(mcpConfig)}
        style={{ marginTop: "0.5rem" }}
      >
        Copy Config
      </button>
    </>
  );
}
