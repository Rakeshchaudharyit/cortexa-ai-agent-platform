"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";

export function AuthHeader() {
  const { status, user, logout } = useAuth();

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
      <div className="flex flex-wrap items-center gap-2">
        {status === "authenticated" ? (
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
