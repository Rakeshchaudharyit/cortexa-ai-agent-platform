"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PasswordField } from "@/components/PasswordField";
import { acknowledgeAdminSession, reportAdminLoginDenied } from "@/services/admin";

const MIN_PASSWORD = 12;

export default function AdminLoginPage() {
  const router = useRouter();
  const { login, logout, status, user, error, clearError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [denying, setDenying] = useState(false);

  useEffect(() => {
    if (status === "authenticated" && user?.role === "admin" && user.status === "active") {
      router.replace("/admin");
    }
  }, [status, user, router]);

  async function denyNonAdminAccess() {
    setDenying(true);
    try {
      await reportAdminLoginDenied();
    } catch {
      // Best-effort audit; still clear the session.
    }
    await logout();
    setLocalError("Administrator access is required.");
    setDenying(false);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearError();
    setLocalError(null);

    if (!email.trim() || !password) {
      setLocalError("Email and password are required.");
      return;
    }

    setPending(true);
    const result = await login({ email: email.trim(), password });
    setPending(false);
    if (!result.ok) {
      setLocalError(result.error);
      return;
    }

    // Login stores the user in AuthProvider; read via a fresh /me is unnecessary —
    // result.ok means AuthProvider already set the authenticated user. We re-check
    // through a short tick by reading sessionStorage is not used; instead call login
    // response path via getCurrent from provider state after microtask.
    // The AuthProvider sets user synchronously before resolving, so we inspect via
    // a follow-up acknowledge call that requires admin.
    const ack = await acknowledgeAdminSession();
    if (!ack || !ack.ok) {
      if (ack && (ack.status === 403 || ack.status === 401)) {
        await denyNonAdminAccess();
        return;
      }
      // If acknowledge fails for other reasons but login succeeded as admin,
      // still allow portal entry — guard will enforce role.
    }

    router.replace("/admin");
  }

  // Handle already-authenticated non-admin visiting this page.
  useEffect(() => {
    if (status !== "authenticated" || !user || denying) return;
    if (user.role === "admin" && user.status === "active") return;
    void denyNonAdminAccess();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, user?.id, user?.role, user?.status]);

  const displayError = localError || error;
  const busy = pending || denying || status === "loading";

  return (
    <main
      className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-12"
      data-testid="admin-login-page"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(900px_480px_at_50%_-10%,rgba(34,211,238,0.18),transparent_55%),radial-gradient(700px_400px_at_80%_80%,rgba(14,165,233,0.08),transparent_50%),linear-gradient(165deg,#040b16,#0a1628_42%,#06101c)]"
      />
      <div className="relative z-10 grid w-full max-w-5xl gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-stretch">
        <section className="flex flex-col justify-center rounded-3xl border border-cyan-400/15 bg-slate-950/50 p-8 shadow-[0_0_80px_rgba(34,211,238,0.08)] backdrop-blur-md sm:p-10">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300/90">
            Cortexa
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Cortexa Administration
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-slate-400">
            Secure access to platform operations, users, AI services, and governance.
          </p>

          <form
            onSubmit={onSubmit}
            className="mt-8 flex flex-col gap-5"
            noValidate
            data-testid="admin-login-form"
          >
            <div className="flex flex-col gap-2">
              <label htmlFor="admin-email" className="text-sm font-medium text-slate-200">
                Email
              </label>
              <input
                id="admin-email"
                name="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2.5 text-slate-100 outline-none transition focus:ring-2 focus:ring-cyan-400/40"
                data-testid="admin-login-email"
              />
            </div>

            <PasswordField
              id="admin-password"
              name="password"
              label="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              minLength={MIN_PASSWORD}
              testId="admin-login-password"
            />

            {displayError ? (
              <p
                role="alert"
                className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200 ring-1 ring-rose-400/30"
                data-testid="admin-login-error"
              >
                {displayError}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-cyan-500/20 px-4 py-2.5 text-sm font-medium text-cyan-50 ring-1 ring-cyan-400/35 transition hover:bg-cyan-500/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="admin-login-submit"
            >
              {pending || denying ? "Signing in…" : "Sign in to Admin"}
            </button>
          </form>

          <div className="mt-6 flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-400">
            <Link
              href="/forgot-password"
              className="text-cyan-300 hover:text-cyan-200 focus-visible:underline"
              data-testid="admin-forgot-password-link"
            >
              Forgot password?
            </Link>
            <Link
              href="/login"
              className="text-slate-300 hover:text-white focus-visible:underline"
              data-testid="admin-back-to-user-login"
            >
              ← Back to user login
            </Link>
          </div>
        </section>

        <aside
          className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 backdrop-blur-sm"
          data-testid="admin-login-security-panel"
        >
          <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-300">
            Security controls
          </h2>
          <ul className="mt-6 space-y-5 text-sm leading-relaxed text-slate-400">
            <li>
              <p className="font-medium text-slate-100">Role-protected access</p>
              <p className="mt-1">Only active administrator accounts can enter the portal.</p>
            </li>
            <li>
              <p className="font-medium text-slate-100">Audited administrative actions</p>
              <p className="mt-1">Mutating operations are recorded for governance review.</p>
            </li>
            <li>
              <p className="font-medium text-slate-100">Secure session management</p>
              <p className="mt-1">
                HttpOnly refresh cookies and short-lived access tokens — never stored in
                localStorage.
              </p>
            </li>
          </ul>
        </aside>
      </div>
    </main>
  );
}
