"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, apiUpload } from "@/lib/api-client";
import { isLoggedIn } from "@/lib/auth";
import AppLayout from "@/components/app-layout";

interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  status: string;
  document_count: number;
  chunk_count: number;
}

interface DocumentMetadata {
  progress_step?: string;
  progress_pct?: number;
  progress_detail?: string;
  progress_updated_at?: number;
  processing_time_secs?: number;
}

interface Document {
  id: string;
  title: string | null;
  source_type: string;
  source_url: string | null;
  file_type: string | null;
  status: string;
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  metadata_: DocumentMetadata | null;
}

export default function KBDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [url, setUrl] = useState("");
  const [bulkUrls, setBulkUrls] = useState("");
  const [showBulk, setShowBulk] = useState(false);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadingUrl, setUploadingUrl] = useState(false);
  const [uploadingBulk, setUploadingBulk] = useState(false);
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [kbData, docsData] = await Promise.all([
        apiFetch<KnowledgeBase>(`/api/kb/${id}`),
        apiFetch<Document[]>(`/api/kb/${id}/documents`),
      ]);
      setKb(kbData);
      setDocs(docsData);
      setError("");
      return docsData;
    } catch {
      setError("Failed to load knowledge base");
      return [];
    }
  }, [id]);

  const hasProcessing = useCallback(
    (docList: Document[]) =>
      docList.some((d) => d.status === "pending" || d.status === "processing"),
    []
  );

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      const fresh = await load();
      if (!hasProcessing(fresh)) {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    }, 2000);
  }, [load, hasProcessing]);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
      return;
    }
    load().then((docList) => {
      if (hasProcessing(docList)) startPolling();
    });
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [router, load, hasProcessing, startPolling]);

  function parseUrls(text: string): string[] {
    const urlPattern = /https?:\/\/[^\s,;|"'<>\]\)]+/gi;
    const matches = text.match(urlPattern) || [];
    const cleaned = matches.map((u) => u.replace(/[.,;:!?)]+$/, ""));
    return [...new Set(cleaned)];
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length) return;
    setUploading(true);
    setError("");
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) formData.append("files", files[i]);
    try {
      await apiUpload(`/api/kb/${id}/documents/upload`, formData);
      await load();
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
    e.target.value = "";
  }

  async function handleUrlSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setUploadingUrl(true);
    setError("");
    try {
      await apiFetch(`/api/kb/${id}/documents/url`, {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      setUrl("");
      await load();
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "URL ingestion failed");
    } finally {
      setUploadingUrl(false);
    }
  }

  async function handleBulkUrlSubmit(e: React.FormEvent) {
    e.preventDefault();
    const urls = parseUrls(bulkUrls);
    if (!urls.length) return;
    setUploadingBulk(true);
    setError("");
    try {
      await apiFetch(`/api/kb/${id}/documents/urls`, {
        method: "POST",
        body: JSON.stringify({ urls }),
      });
      setBulkUrls("");
      setShowBulk(false);
      await load();
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Bulk URL ingestion failed");
    } finally {
      setUploadingBulk(false);
    }
  }

  async function handleRetryDoc(docId: string) {
    setError("");
    try {
      await apiFetch(`/api/kb/${id}/documents/${docId}/retry`, { method: "POST" });
      await load();
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Retry failed");
    }
  }

  async function handleRenameDoc(docId: string, newTitle: string) {
    if (!newTitle.trim()) {
      setEditingDocId(null);
      return;
    }
    try {
      await apiFetch(`/api/kb/${id}/documents/${docId}`, {
        method: "PATCH",
        body: JSON.stringify({ title: newTitle.trim() }),
      });
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Rename failed");
    }
    setEditingDocId(null);
  }

  async function handleDeleteDoc(docId: string) {
    try {
      await apiFetch(`/api/kb/${id}/documents/${docId}`, { method: "DELETE" });
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const processingCount = docs.filter(
    (d) => d.status === "pending" || d.status === "processing"
  ).length;

  if (!kb) return <AppLayout><p style={{ padding: "2rem", color: "var(--text-tertiary)" }}>Loading...</p></AppLayout>;

  return (
    <AppLayout kbId={kb.id} kbName={kb.name}>
      <div className="manage-sub-tabs">
        <Link href={`/kb/${id}`} className="active">Sources</Link>
        <Link href={`/kb/${id}/settings`}>API Keys</Link>
      </div>

      {error && <p className="error" style={{ marginBottom: "1rem" }}>{error}</p>}

      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.5rem" }}>
        <span style={{ color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
          {kb.document_count} documents &middot; {kb.chunk_count} chunks
        </span>
      </div>

      {processingCount > 0 && (
        <div style={{
          background: "var(--warning-bg)",
          border: "1px solid #ffd54f",
          borderRadius: "var(--radius-md)",
          padding: "0.75rem 1rem",
          marginBottom: "1rem",
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          fontSize: "0.85rem",
        }}>
          <span className="spinner" />
          <span style={{ color: "var(--warning-text)", fontWeight: 500 }}>
            Processing {processingCount} document{processingCount > 1 ? "s" : ""}...
          </span>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem", alignItems: "flex-end", flexWrap: "wrap" }}>
        <label style={{
          display: "inline-flex",
          alignItems: "center",
          cursor: uploading ? "wait" : "pointer",
          padding: "0.5rem 0.875rem",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          background: uploading ? "var(--bg-secondary)" : "var(--bg-primary)",
          opacity: uploading ? 0.7 : 1,
          fontSize: "0.85rem",
          fontWeight: 500,
          gap: "0.375rem",
          marginBottom: 0,
          textTransform: "none",
          letterSpacing: "normal",
          color: "var(--text-primary)",
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          {uploading ? "Uploading..." : "Upload Files"}
          <input type="file" multiple accept=".pdf,.md,.txt" onChange={handleFileUpload} disabled={uploading} style={{ display: "none" }} />
        </label>

        <form onSubmit={handleUrlSubmit} style={{ display: "flex", gap: "0.375rem", flex: 1, minWidth: 240 }}>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
            disabled={uploadingUrl}
            style={{ fontSize: "0.85rem" }}
          />
          <button type="submit" disabled={uploadingUrl} style={{ whiteSpace: "nowrap" }}>
            {uploadingUrl ? "Adding..." : "Add URL"}
          </button>
        </form>

        <button
          type="button"
          onClick={() => setShowBulk(!showBulk)}
          style={{
            background: showBulk ? "var(--bg-tertiary)" : "var(--bg-primary)",
            whiteSpace: "nowrap",
          }}
        >
          Bulk URLs
        </button>
      </div>

      {showBulk && (
        <form onSubmit={handleBulkUrlSubmit} style={{ marginBottom: "1.5rem" }}>
          <textarea
            value={bulkUrls}
            onChange={(e) => setBulkUrls(e.target.value)}
            placeholder={"Paste URLs in any format — one per line, comma-separated, or mixed in with text.\nhttps://example.com/page1\nhttps://example.com/page2"}
            rows={5}
            disabled={uploadingBulk}
            style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem", marginBottom: "0.5rem" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: parseUrls(bulkUrls).length > 10 ? "var(--error)" : "var(--text-tertiary)", fontSize: "0.8rem" }}>
              {parseUrls(bulkUrls).length} URL{parseUrls(bulkUrls).length !== 1 ? "s" : ""} detected
              {parseUrls(bulkUrls).length > 10 && " (max 10)"}
            </span>
            <button type="submit" className="primary" disabled={uploadingBulk || parseUrls(bulkUrls).length === 0 || parseUrls(bulkUrls).length > 10}>
              {uploadingBulk ? "Adding..." : `Add ${parseUrls(bulkUrls).length} URLs`}
            </button>
          </div>
        </form>
      )}

      {docs.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem 2rem", color: "var(--text-tertiary)" }}>
          <p>No documents yet. Upload files or add URLs above.</p>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Type</th>
              <th>Status</th>
              <th>Chunks</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <tr key={doc.id}>
                <td style={{ maxWidth: 300 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    {editingDocId === doc.id ? (
                      <input
                        type="text"
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onBlur={() => handleRenameDoc(doc.id, editingTitle)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRenameDoc(doc.id, editingTitle);
                          if (e.key === "Escape") setEditingDocId(null);
                        }}
                        autoFocus
                        style={{ fontSize: "0.85rem", width: "100%", padding: "0.15rem 0.4rem" }}
                      />
                    ) : (
                      <span
                        onClick={() => { setEditingDocId(doc.id); setEditingTitle(doc.title || ""); }}
                        style={{ cursor: "pointer", borderBottom: "1px dashed var(--border)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: 1, minWidth: 0 }}
                        title="Click to rename"
                      >
                        {doc.title || "Untitled"}
                      </span>
                    )}
                    {doc.source_url && editingDocId !== doc.id && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigator.clipboard.writeText(doc.source_url!);
                          const btn = e.currentTarget;
                          btn.style.color = "var(--success, #4caf50)";
                          setTimeout(() => { btn.style.color = ""; }, 1200);
                        }}
                        title={doc.source_url}
                        style={{
                          background: "none",
                          border: "none",
                          padding: "0.1rem",
                          cursor: "pointer",
                          color: "var(--text-tertiary)",
                          flexShrink: 0,
                          display: "flex",
                          alignItems: "center",
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                        </svg>
                      </button>
                    )}
                  </div>
                </td>
                <td>{doc.file_type || doc.source_type}</td>
                <td>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    <span className={`badge ${doc.status}`} style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                      {(doc.status === "pending" || doc.status === "processing") && <span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} />}
                      {doc.status}
                    </span>
                    {doc.status === "processing" && doc.metadata_?.progress_detail && (
                      <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>
                        <span>{doc.metadata_.progress_detail}</span>
                        {doc.metadata_.progress_pct != null && (
                          <div style={{
                            marginTop: "0.15rem",
                            height: 3,
                            background: "var(--border)",
                            borderRadius: 2,
                            overflow: "hidden",
                            width: "100%",
                            minWidth: 60,
                          }}>
                            <div style={{
                              height: "100%",
                              width: `${doc.metadata_.progress_pct}%`,
                              background: "var(--accent, #2196f3)",
                              borderRadius: 2,
                              transition: "width 0.5s ease",
                            }} />
                          </div>
                        )}
                      </div>
                    )}
                    {doc.error_message && (
                      <span style={{ fontSize: "0.7rem", color: "var(--error)" }}>
                        {doc.error_message}
                      </span>
                    )}
                  </div>
                </td>
                <td>{doc.chunk_count}</td>
                <td style={{ display: "flex", gap: "0.25rem" }}>
                  {(doc.status === "error" || doc.status === "completed") && (
                    <button style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }} onClick={() => handleRetryDoc(doc.id)}>
                      Reload
                    </button>
                  )}
                  <button className="danger" style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }} onClick={() => handleDeleteDoc(doc.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <style jsx global>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </AppLayout>
  );
}
