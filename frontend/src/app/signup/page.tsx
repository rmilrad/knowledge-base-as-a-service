"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api-client";
import { setToken } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [guestLoading, setGuestLoading] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("kbaas-theme");
    if (stored === "dark" || stored === "light") {
      document.documentElement.setAttribute("data-theme", stored);
    } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      document.documentElement.setAttribute("data-theme", "dark");
    }
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const data = await apiFetch<{ access_token: string }>(
        "/api/auth/register",
        {
          method: "POST",
          body: JSON.stringify({ name, email, password }),
        }
      );
      setToken(data.access_token);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Signup failed");
    }
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h1>Sign Up</h1>
        <p>Create your KBaaS account</p>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
            />
          </div>
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="At least 8 characters"
            />
          </div>
          {error && <p className="error" style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>{error}</p>}
          <button type="submit" className="primary" style={{ width: "100%" }}>
            Sign Up
          </button>
        </form>
        <p style={{ marginTop: "1.25rem", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
          Have an account? <Link href="/login">Log in</Link>
        </p>

        <div style={{
          marginTop: "1.25rem",
          paddingTop: "1.25rem",
          borderTop: "1px solid var(--border-light)",
          textAlign: "center",
        }}>
          <button
            type="button"
            onClick={async () => {
              setGuestLoading(true);
              setError("");
              try {
                const data = await apiFetch<{ access_token: string }>("/api/auth/guest", { method: "POST" });
                setToken(data.access_token);
                router.push("/dashboard");
              } catch (err: unknown) {
                setError(err instanceof Error ? err.message : "Guest login failed");
                setGuestLoading(false);
              }
            }}
            disabled={guestLoading}
            style={{
              width: "100%",
              background: "var(--bg-secondary)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border)",
              marginBottom: "0.5rem",
            }}
          >
            {guestLoading ? "Setting up..." : "Try without an account"}
          </button>
          <p style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", lineHeight: 1.4 }}>
            Your data will be deleted after 24 hours.
          </p>
        </div>
      </div>
    </div>
  );
}
