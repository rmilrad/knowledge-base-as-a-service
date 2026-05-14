"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { isLoggedIn } from "@/lib/auth";
import AppLayout from "@/components/app-layout";

interface KnowledgeBase {
  id: string;
  name: string;
}

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

  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState("");

  const loadData = useCallback(async () => {
    try {
      const [kbData, keysData] = await Promise.all([
        apiFetch<KnowledgeBase>(`/api/kb/${id}`),
        apiFetch<ApiKey[]>(`/api/kb/${id}/keys`),
      ]);
      setKb(kbData);
      setKeys(keysData);
    } catch {
      setError("Failed to load settings");
    }
  }, [id]);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    loadData();
  }, [router, loadData]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      const data = await apiFetch<{ key: string }>(`/api/kb/${id}/keys`, {
        method: "POST",
        body: JSON.stringify({ name: keyName || null }),
      });
      setNewKey(data.key);
      setKeyName("");
      loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create key");
    }
  }

  async function handleRevoke(keyId: string) {
    try {
      await apiFetch(`/api/kb/${id}/keys/${keyId}`, { method: "DELETE" });
      loadData();
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

  if (!kb) return <AppLayout><p style={{ padding: "2rem", color: "var(--text-tertiary)" }}>Loading...</p></AppLayout>;

  return (
    <AppLayout kbId={kb.id} kbName={kb.name}>
      <div className="tabs">
        <Link href={`/kb/${id}`}>Sources</Link>
        <Link href={`/kb/${id}/settings`} className="active">Settings</Link>
      </div>

      {error && <p className="error" style={{ marginBottom: "1rem" }}>{error}</p>}

      <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>API Keys</h3>
      <p style={{ color: "var(--text-tertiary)", marginBottom: "1rem", fontSize: "0.85rem" }}>
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
            background: "var(--warning-bg)",
            border: "1px solid #ffd54f",
            padding: "1rem",
            borderRadius: "var(--radius-md)",
            marginBottom: "1rem",
          }}
        >
          <strong style={{ fontSize: "0.85rem" }}>New API Key (copy now — it won&apos;t be shown again):</strong>
          <pre
            style={{
              background: "var(--bg-tertiary)",
              padding: "0.5rem 0.75rem",
              marginTop: "0.5rem",
              borderRadius: "var(--radius-sm)",
              overflowX: "auto",
              fontFamily: "var(--font-mono)",
              fontSize: "0.8rem",
            }}
          >
            {newKey}
          </pre>
          <button
            onClick={() => navigator.clipboard.writeText(newKey)}
            style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}
          >
            Copy
          </button>
        </div>
      )}

      {keys.length > 0 && (
        <table style={{ marginBottom: "2rem" }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Prefix</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id}>
                <td>{k.name || "—"}</td>
                <td>
                  <code style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>{k.key_prefix}...</code>
                </td>
                <td>{new Date(k.created_at).toLocaleDateString()}</td>
                <td>
                  <button
                    className="danger"
                    style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
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

      <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>MCP Connection</h3>
      <p style={{ color: "var(--text-tertiary)", marginBottom: "0.5rem", fontSize: "0.85rem" }}>
        Add this to your Claude Desktop or MCP client configuration:
      </p>
      <pre
        style={{
          background: "var(--bg-tertiary)",
          padding: "1rem",
          borderRadius: "var(--radius-md)",
          overflowX: "auto",
          fontFamily: "var(--font-mono)",
          fontSize: "0.8rem",
          lineHeight: 1.6,
        }}
      >
        {mcpConfig}
      </pre>
      <button
        onClick={() => navigator.clipboard.writeText(mcpConfig)}
        style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}
      >
        Copy Config
      </button>
    </AppLayout>
  );
}
