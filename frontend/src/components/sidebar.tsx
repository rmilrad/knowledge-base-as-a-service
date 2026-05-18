"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { clearToken } from "@/lib/auth";

interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  status: string;
  document_count: number;
  chunk_count: number;
}

interface SidebarProps {
  onNewKB: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onNavigate?: () => void;
}

export default function Sidebar({ onNewKB, theme, onToggleTheme, onNavigate }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);

  const loadKBs = useCallback(async () => {
    try {
      const data = await apiFetch<KnowledgeBase[]>("/api/kb");
      setKbs(data);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    apiFetch<{ is_admin: boolean }>("/api/auth/me")
      .then((me) => setIsAdmin(me.is_admin))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadKBs();
  }, [loadKBs]);

  useEffect(() => {
    if (pathname === "/dashboard") loadKBs();
  }, [pathname, loadKBs]);

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  const activeKbId = pathname.match(/\/kb\/([^/]+)/)?.[1] || null;

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link href="/dashboard" className="sidebar-logo">
          KBaaS
        </Link>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-header">
          <span className="sidebar-section-title">Knowledge Bases</span>
          <button className="sidebar-action" onClick={onNewKB} title="New KB">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        </div>

        <div className="sidebar-kb-list">
          {kbs.map((kb) => (
            <Link
              key={kb.id}
              href={`/kb/${kb.id}`}
              className={`sidebar-kb-item ${activeKbId === kb.id ? "active" : ""}`}
              onClick={onNavigate}
            >
              <span className="sidebar-kb-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                </svg>
              </span>
              <div className="sidebar-kb-info">
                <span className="sidebar-kb-name">{kb.name}</span>
                <span className="sidebar-kb-meta">
                  {kb.document_count} docs &middot; {kb.chunk_count} chunks
                </span>
              </div>
            </Link>
          ))}
          {kbs.length === 0 && (
            <p className="sidebar-empty">No knowledge bases yet</p>
          )}
        </div>
      </div>

      <div className="sidebar-footer">
        {isAdmin && (
          <Link href="/admin" className="sidebar-footer-btn" style={{ textDecoration: "none" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
            </svg>
            Admin
          </Link>
        )}
        <button className="sidebar-footer-btn" onClick={handleLogout}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          Log Out
        </button>
        <button className="theme-toggle" onClick={onToggleTheme} title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}>
          {theme === "light" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          )}
        </button>
      </div>
    </aside>
  );
}
