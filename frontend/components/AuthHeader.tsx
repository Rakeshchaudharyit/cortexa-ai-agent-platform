"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

function navClass(active: boolean): string {
  return `rounded-xl px-3 py-2 text-sm font-medium transition ${
    active
      ? "bg-cyan-400/12 text-cyan-100 ring-1 ring-cyan-400/25"
      : "text-slate-300 hover:bg-white/[0.055] hover:text-white"
  }`;
}

export function AuthHeader() {
  const { status, user, logout } = useAuth();
  const pathname = usePathname();

  return (
    <div
      className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-slate-950/35 p-3 backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between"
      data-testid="auth-header"
    >
      <div className="min-w-0 px-1">
        {status === "loading" ? (
          <p className="text-sm text-slate-400" data-testid="auth-loading">
            Restoring secure session…
          </p>
        ) : status === "authenticated" && user ? (
          <div data-testid="auth-user-display">
            <p className="truncate text-sm font-medium text-slate-100">{user.full_name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
          </div>
        ) : (
          <p className="text-sm text-slate-400" data-testid="auth-anonymous">
            Sign in to access your private knowledge workspace.
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1" data-testid="auth-nav">
        {status === "loading" ? null : status === "authenticated" ? (
          <>
            <Link href="/workspace" className={navClass(pathname === "/workspace")}>Overview</Link>
            <Link
              href="/chat"
              className={navClass(Boolean(pathname?.startsWith("/chat")))}
              data-testid="chat-link"
            >
              Chat
            </Link>
            <Link href="/workspace#documents" className={navClass(false)} data-testid="documents-link">
              Knowledge
            </Link>
            <Link
              href="/memories"
              className={navClass(Boolean(pathname?.startsWith("/memories")))}
              data-testid="memories-link"
            >
              Memory
            </Link>
            <Link
              href="/tools"
              className={navClass(Boolean(pathname?.startsWith("/tools")))}
              data-testid="tools-link"
            >
              Tools
            </Link>
            {user?.role === "admin" ? (
              <Link
                href="/admin"
                className={navClass(Boolean(pathname?.startsWith("/admin")))}
                data-testid="admin-link"
              >
                Admin
              </Link>
            ) : null}
            <button
              type="button"
              onClick={() => void logout()}
              className="ml-1 rounded-xl border border-white/10 px-3 py-2 text-sm font-medium text-slate-400 transition hover:bg-white/[0.05] hover:text-white"
              data-testid="logout-button"
            >
              Log out
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="cx-button-secondary" data-testid="login-link">
              Log in
            </Link>
            <Link href="/register" className="cx-button-primary" data-testid="register-link">
              Create account
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
