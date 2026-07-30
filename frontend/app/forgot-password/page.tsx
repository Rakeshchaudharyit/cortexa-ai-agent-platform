"use client";

import Link from "next/link";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { requestPasswordReset } from "@/services/auth";
import { fetchSystemInfo } from "@/services/system";

function publicDevNoticeEnabled(): boolean {
  return process.env.NEXT_PUBLIC_PASSWORD_RESET_DEV_NOTICE === "true";
}

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  // Only show after backend confirms the feature flag (avoids sticky notice on fetch failure).
  const [showDevNotice, setShowDevNotice] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!publicDevNoticeEnabled()) {
        return;
      }
      const result = await fetchSystemInfo();
      if (cancelled) {
        return;
      }
      if (!result.ok) {
        setShowDevNotice(false);
        return;
      }
      setShowDevNotice(Boolean(result.data.features.password_reset_dev_notice));
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    setSuccessMessage(null);

    if (!email.trim()) {
      setLocalError("Email is required.");
      return;
    }

    setPending(true);
    const result = await requestPasswordReset({ email: email.trim() });
    setPending(false);

    if (!result.ok) {
      if (result.status === null) {
        setLocalError("Unable to connect to the server");
        return;
      }
      if (result.status >= 500) {
        setLocalError("Something went wrong on the server. Please try again.");
        return;
      }
      setLocalError(result.error || "Unable to process the request.");
      return;
    }

    setSuccessMessage(result.data.message);
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col gap-8 px-6 py-12 sm:px-10">
      <header className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300/90">
          Authentication
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-50">
          Forgot password
        </h1>
        <p className="text-sm leading-relaxed text-slate-400">
          Enter your email and we will prepare password reset instructions if an
          account exists.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
        noValidate
        data-testid="forgot-password-form"
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
            className="rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2 text-slate-100 outline-none transition focus:ring-2 focus:ring-cyan-400/40"
            data-testid="forgot-password-email"
          />
        </div>

        {localError ? (
          <p
            role="alert"
            className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200 ring-1 ring-rose-400/30"
            data-testid="forgot-password-error"
          >
            {localError}
          </p>
        ) : null}

        {successMessage ? (
          <p
            role="status"
            className="rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100 ring-1 ring-emerald-400/30"
            data-testid="forgot-password-success"
          >
            {successMessage}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-cyan-500/20 px-4 py-2.5 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="forgot-password-submit"
        >
          {pending ? "Submitting…" : "Send reset instructions"}
        </button>
      </form>

      {showDevNotice ? (
        <aside
          className="rounded-xl border border-amber-400/25 bg-amber-500/5 px-4 py-3 text-sm leading-relaxed text-amber-100/90"
          data-testid="forgot-password-dev-notice"
        >
          <p className="font-medium text-amber-100">Local development notice</p>
          <p className="mt-1 text-amber-100/80">
            Email delivery is not configured in this local environment. Developers
            can retrieve a generated reset link using the documented CLI.
          </p>
        </aside>
      ) : null}

      <p className="text-sm text-slate-400">
        Remembered your password?{" "}
        <Link href="/login" className="text-cyan-300 hover:text-cyan-200">
          Log in
        </Link>
      </p>
    </main>
  );
}
