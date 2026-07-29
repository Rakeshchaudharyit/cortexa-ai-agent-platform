"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";

const MIN_PASSWORD = 12;

export default function LoginPage() {
  const router = useRouter();
  const { login, status, error, clearError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/");
    }
  }, [status, router]);

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
    if (result.ok) {
      router.replace("/");
      return;
    }
    setLocalError(result.error);
  }

  const displayError = localError || error;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col gap-8 px-6 py-12 sm:px-10">
      <header className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300/90">
          Phase 3 — Authentication
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-50">Log in</h1>
        <p className="text-sm leading-relaxed text-slate-400">
          Access the Cortexa platform with your email and password.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
        noValidate
        data-testid="login-form"
      >
        <div className="flex flex-col gap-2">
          <label htmlFor="email" className="text-sm font-medium text-slate-200">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2 text-slate-100 outline-none ring-cyan-400/0 transition focus:ring-2 focus:ring-cyan-400/40"
            data-testid="login-email"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="password" className="text-sm font-medium text-slate-200">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            minLength={MIN_PASSWORD}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2 text-slate-100 outline-none ring-cyan-400/0 transition focus:ring-2 focus:ring-cyan-400/40"
            data-testid="login-password"
          />
        </div>

        {displayError ? (
          <p
            role="alert"
            className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200 ring-1 ring-rose-400/30"
            data-testid="login-error"
          >
            {displayError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={pending || status === "loading"}
          className="rounded-lg bg-cyan-500/20 px-4 py-2.5 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="login-submit"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="text-sm text-slate-400">
        Need an account?{" "}
        <Link href="/register" className="text-cyan-300 hover:text-cyan-200">
          Register
        </Link>
      </p>
    </main>
  );
}
