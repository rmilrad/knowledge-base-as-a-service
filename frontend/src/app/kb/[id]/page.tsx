"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, apiUpload } from "@/lib/api-client";
import { isLoggedIn } from "@/lib/auth";

interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  status: string;
  document_count: number;
  chunk_count: number;
}

interface Document {
  id: string;
  title: string | null;
  source_type: string;
  file_type: string | null;
  status: string;
  error_message: string | null;
  chunk_count: number;
  created_at: string;
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
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [kbData, docsData] = await Promise.all([
        apiFetch<KnowledgeBase>(`/api/kb/${id}`),
        apiFetch<Document[]>(`/api/kb/${id}/documents`),
      ]);
      setKb(kbData);
      setDocs(docsData);
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

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length) return;
    setUploading(true);
    setError("");
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }
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

  function parseUrls(text: string): string[] {
    const urlPattern = /https?:\/\/[^\s,;|"'<>\]\)]+/gi;
    const matches = text.match(urlPattern) || [];
    const cleaned = matches.map((u) => u.replace(/[.,;:!?)]+$/, ""));
    return [...new Set(cleaned)];
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
      await apiFetch(`/api/kb/${id}/documents/${docId}/retry`, {
        method: "POST",
      });
      await load();
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Retry failed");
    }
  }

  async function handleDeleteDoc(docId: string) {
    try {
      await apiFetch(`/api/kb/${id}/documents/${docId}`, {
        method: "DELETE",
      });
      load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const processingCount = docs.filter(
    (d) => d.status === "pending" || d.status === "processing"
  ).length;

  if (!kb) return <p>Loading...</p>;

  return (
    <>
      <nav>
        <h1>
          <Link href="/dashboard">KBaaS</Link> / {kb.name}
        </h1>
      </nav>

      <div className="tabs">
        <Link href={`/kb/${id}`} className="active">
          Sources
        </Link>
        <Link href={`/kb/${id}/chat`}>Chat</Link>
        <Link href={`/kb/${id}/settings`}>Settings</Link>
      </div>

      {error && <p className="error">{error}</p>}

      <div style={{ marginBottom: "1.5rem" }}>
        <p style={{ color: "#666" }}>
          {kb.document_count} documents &middot; {kb.chunk_count} chunks
        </p>
      </div>

      {processingCount > 0 && (
        <div
          style={{
            background: "#fff3cd",
            border: "1px solid #ffc107",
            borderRadius: 8,
            padding: "0.75rem 1rem",
            marginBottom: "1rem",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 16,
              height: 16,
              border: "2px solid #856404",
              borderTopColor: "transparent",
              borderRadius: "50%",
              animation: "spin 1s linear infinite",
            }}
          />
          <span style={{ color: "#856404", fontWeight: 500 }}>
            Processing {processingCount} document{processingCount > 1 ? "s" : ""}...
          </span>
        </div>
      )}

      <div
        style={{
          display: "flex",
          gap: "1rem",
          marginBottom: "1.5rem",
          alignItems: "flex-end",
        }}
      >
        <div>
          <label
            style={{
              display: "inline-block",
              cursor: uploading ? "wait" : "pointer",
              padding: "0.5rem 1rem",
              border: "1px solid #ccc",
              borderRadius: 4,
              background: uploading ? "#f0f0f0" : "#fff",
              opacity: uploading ? 0.7 : 1,
            }}
          >
            {uploading ? "Uploading..." : "Upload Files"}
            <input
              type="file"
              multiple
              accept=".pdf,.md,.txt"
              onChange={handleFileUpload}
              disabled={uploading}
              style={{ display: "none" }}
            />
          </label>
        </div>
        <form
          onSubmit={handleUrlSubmit}
          style={{ display: "flex", gap: "0.5rem", flex: 1 }}
        >
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
            disabled={uploadingUrl}
          />
          <button type="submit" disabled={uploadingUrl}>
            {uploadingUrl ? "Adding..." : "Add URL"}
          </button>
        </form>
        <button
          type="button"
          onClick={() => setShowBulk(!showBulk)}
          style={{
            padding: "0.5rem 1rem",
            border: "1px solid #ccc",
            borderRadius: 4,
            background: showBulk ? "#e8e8e8" : "#fff",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          Bulk URLs
        </button>
      </div>

      {showBulk && (
        <form
          onSubmit={handleBulkUrlSubmit}
          style={{ marginBottom: "1.5rem" }}
        >
          <textarea
            value={bulkUrls}
            onChange={(e) => setBulkUrls(e.target.value)}
            placeholder={"Paste URLs, one per line:\nhttps://example.com/page1\nhttps://example.com/page2\nhttps://example.com/page3"}
            rows={6}
            disabled={uploadingBulk}
            style={{
              width: "100%",
              padding: "0.5rem",
              fontFamily: "monospace",
              fontSize: "0.85rem",
              marginBottom: "0.5rem",
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "#666", fontSize: "0.85rem" }}>
              {parseUrls(bulkUrls).length} URL{parseUrls(bulkUrls).length !== 1 ? "s" : ""} detected
            </span>
            <button type="submit" disabled={uploadingBulk || parseUrls(bulkUrls).length === 0}>
              {uploadingBulk ? "Adding..." : `Add ${parseUrls(bulkUrls).length} URLs`}
            </button>
          </div>
        </form>
      )}

      {docs.length === 0 ? (
        <p style={{ color: "#666" }}>
          No documents yet. Upload files or add URLs above.
        </p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr
              style={{
                borderBottom: "2px solid #eee",
                textAlign: "left",
              }}
            >
              <th style={{ padding: "0.5rem" }}>Title</th>
              <th style={{ padding: "0.5rem" }}>Type</th>
              <th style={{ padding: "0.5rem" }}>Status</th>
              <th style={{ padding: "0.5rem" }}>Chunks</th>
              <th style={{ padding: "0.5rem" }}></th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <tr
                key={doc.id}
                style={{ borderBottom: "1px solid #eee" }}
              >
                <td style={{ padding: "0.5rem" }}>
                  {doc.title || "Untitled"}
                </td>
                <td style={{ padding: "0.5rem" }}>
                  {doc.file_type || doc.source_type}
                </td>
                <td style={{ padding: "0.5rem" }}>
                  <span
                    className={`badge ${doc.status}`}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.35rem",
                    }}
                  >
                    {(doc.status === "pending" || doc.status === "processing") && (
                      <span
                        style={{
                          display: "inline-block",
                          width: 10,
                          height: 10,
                          border: "2px solid currentColor",
                          borderTopColor: "transparent",
                          borderRadius: "50%",
                          animation: "spin 1s linear infinite",
                        }}
                      />
                    )}
                    {doc.status}
                  </span>
                  {doc.error_message && (
                    <span
                      style={{
                        fontSize: "0.75rem",
                        color: "#cc0000",
                        marginLeft: "0.5rem",
                      }}
                    >
                      {doc.error_message}
                    </span>
                  )}
                </td>
                <td style={{ padding: "0.5rem" }}>{doc.chunk_count}</td>
                <td style={{ padding: "0.5rem", display: "flex", gap: "0.25rem" }}>
                  {(doc.status === "error" || doc.status === "completed") && (
                    <button
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                      onClick={() => handleRetryDoc(doc.id)}
                    >
                      Retry
                    </button>
                  )}
                  <button
                    className="danger"
                    style={{ padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                    onClick={() => handleDeleteDoc(doc.id)}
                  >
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
    </>
  );
}
