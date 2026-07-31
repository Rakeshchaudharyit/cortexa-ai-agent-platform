"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

function navClass(active: boolean): string {
  return `rounded-lg px-3 py-2 text-sm font-medium transition ring-1 ${
    active
      ? "bg-cyan-500/25 text-cyan-100 ring-cyan-400/40"
      : "bg-slate-500/20 text-slate-100 ring-slate-400/30 hover:bg-slate-500/30"
  }`;
}

export function AuthHeader() {
  const { status, user, logout } = useAuth();
  const pathname = usePathname();

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3"
      data-testid="auth-header"
    >
      <div className="min-w-0">
        {status === "loading" ? (
          <p className="text-sm text-slate-400" data-testid="auth-loading">
            Restoring session…
          </p>
        ) : status === "authenticated" && user ? (
          <p className="text-sm text-slate-300" data-testid="auth-user-display">
            Signed in as{" "}
            <span className="font-medium text-slate-100">{user.full_name}</span>
            <span className="text-slate-500"> ({user.email})</span>
          </p>
        ) : (
          <p className="text-sm text-slate-400" data-testid="auth-anonymous">
            Not signed in
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2" data-testid="auth-nav">
        {status === "loading" ? null : status === "authenticated" ? (
          <>
            <Link
              href="/chat"
              className={navClass(Boolean(pathname?.startsWith("/chat")))}
              data-testid="chat-link"
            >
              Chat
            </Link>
            <Link
              href="/#documents"
              className={navClass(false)}
              data-testid="documents-link"
            >
              Documents
            </Link>
            <Link
              href="/tools"
              className={navClass(Boolean(pathname?.startsWith("/tools")))}
              data-testid="tools-link"
            >
              Tool History
            </Link>
            <Link
              href="/memories"
              className={navClass(Boolean(pathname?.startsWith("/memories")))}
              data-testid="memories-link"
            >
              Memories
            </Link>
            {/* Admin-only navigation is intentionally omitted — no admin UI is shipped yet. */}
            <button
              type="button"
              onClick={() => {
                void logout();
              }}
              className="rounded-lg bg-slate-500/20 px-3 py-2 text-sm font-medium text-slate-100 ring-1 ring-slate-400/30 transition hover:bg-slate-500/30"
              data-testid="logout-button"
            >
              Log out
            </button>
          </>
        ) : (
          <>
            <Link
              href="/login"
              className="rounded-lg bg-slate-500/20 px-3 py-2 text-sm font-medium text-slate-100 ring-1 ring-slate-400/30 transition hover:bg-slate-500/30"
              data-testid="login-link"
            >
              Log in
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-cyan-500/20 px-3 py-2 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30"
              data-testid="register-link"
            >
              Register
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
