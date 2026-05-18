"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn } from "@/lib/auth";
import Sidebar from "./sidebar";
import ChatPanel from "./chat-panel";

interface AppLayoutProps {
  children: React.ReactNode;
  kbId?: string;
  kbName?: string;
  /** Which manage sub-tab is active (sources | settings). Default: sources */
  manageTab?: "sources" | "settings";
  onNewKB?: () => void;
}

const MIN_SIDEBAR_WIDTH = 180;
const MAX_SIDEBAR_WIDTH = 480;
const DEFAULT_SIDEBAR_WIDTH = 260;

function getInitialTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  const stored = localStorage.getItem("kbaas-theme");
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function AppLayout({ children, kbId, kbName, manageTab, onNewKB }: AppLayoutProps) {
  const router = useRouter();
  const [activeView, setActiveView] = useState<"chat" | "manage">(kbId ? "chat" : "manage");
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const isDragging = useRef(false);

  // Initialize theme on mount
  useEffect(() => {
    const t = getInitialTheme();
    setTheme(t);
    document.documentElement.setAttribute("data-theme", t);
  }, []);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/login");
    }
  }, [router]);

  // When we navigate to a manage sub-tab (settings page), show manage view
  useEffect(() => {
    if (manageTab) {
      setActiveView("manage");
    }
  }, [manageTab]);

  // When KB changes, reset to chat
  useEffect(() => {
    if (kbId) {
      setActiveView("chat");
    }
  }, [kbId]);

  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("kbaas-theme", next);
  }

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging.current) return;
    e.preventDefault();
    const shellPadding = 8;
    const newWidth = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, e.clientX - shellPadding));
    setSidebarWidth(newWidth);
  }, []);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  function handleResizeStart(e: React.MouseEvent) {
    e.preventDefault();
    isDragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  return (
    <div className="app-shell">
      <div className="sidebar-wrapper" style={{ width: sidebarWidth }}>
        <Sidebar
          onNewKB={onNewKB || (() => router.push("/dashboard?new=1"))}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
        <div
          className="sidebar-resize-handle"
          onMouseDown={handleResizeStart}
        />
      </div>
      <main className="main-content">
        {kbId && (
          <div className="main-header">
            <div className="main-header-left">
              <h2 className="main-header-title">{kbName || "Knowledge Base"}</h2>
            </div>
            <div className="view-switcher">
              <button
                className={`view-switcher-btn ${activeView === "chat" ? "active" : ""}`}
                onClick={() => setActiveView("chat")}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                Chat
              </button>
              <button
                className={`view-switcher-btn ${activeView === "manage" ? "active" : ""}`}
                onClick={() => {
                  setActiveView("manage");
                  // Navigate to sources view if not already on a manage page
                  if (!manageTab) {
                    router.push(`/kb/${kbId}`);
                  }
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
                Manage
              </button>
            </div>
          </div>
        )}
        {!kbId && (
          <div className="main-header" />
        )}
        <div className="main-body" style={activeView === "chat" && kbId ? { padding: 0, display: "flex", flexDirection: "column" } : undefined}>
          {kbId && activeView === "chat" ? (
            <ChatPanel kbId={kbId} kbName={kbName || ""} />
          ) : (
            children
          )}
        </div>
      </main>
    </div>
  );
}
