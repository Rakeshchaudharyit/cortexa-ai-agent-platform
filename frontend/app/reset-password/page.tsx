"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, type FormEvent, useMemo, useState } from "react";

import { PasswordField } from "@/components/PasswordField";
import { resetPassword } from "@/services/auth";

const MIN_PASSWORD = 12;

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tokenFromUrl = useMemo(() => searchParams.get("token")?.trim() ?? "", [searchParams]);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);
    setSuccessMessage(null);

    const token = tokenFromUrl;
    if (!token) {
      setLocalError("This password reset link is invalid or has expired.");
      return;
    }
    if (newPassword.length < MIN_PASSWORD) {
      setLocalError(`Password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setLocalError("Passwords do not match.");
      return;
    }

    setPending(true);
    const result = await resetPassword({
      token,
      new_password: newPassword,
      confirm_password: confirmPassword,
    });
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
      setLocalError(result.error || "Unable to reset password.");
      return;
    }

    setSuccessMessage(result.data.message);
    setNewPassword("");
    setConfirmPassword("");
    // Remove the raw token from the URL after success.
    router.replace("/reset-password");
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col gap-8 px-6 py-12 sm:px-10">
      <header className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300/90">
          Authentication
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-50">
          Reset password
        </h1>
        <p className="text-sm leading-relaxed text-slate-400">
          Choose a new password, then sign in again. Passwords are accepted exactly as entered.
        </p>
      </header>

      {successMessage ? (
        <div
          className="flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
          data-testid="reset-password-success"
        >
          <p role="status" className="text-sm text-emerald-100">
            {successMessage}
          </p>
          <Link href="/login" className="text-sm text-cyan-300 hover:text-cyan-200">
            Go to login
          </Link>
        </div>
      ) : (
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
          noValidate
          data-testid="reset-password-form"
        >
          <PasswordField
            name="new_password"
            label="New password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            autoComplete="new-password"
            minLength={MIN_PASSWORD}
            hint={`At least ${MIN_PASSWORD} characters. Passphrases are allowed. Leading and trailing spaces are kept.`}
            testId="reset-password-new"
          />
          <PasswordField
            name="confirm_password"
            label="Confirm new password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            autoComplete="new-password"
            minLength={MIN_PASSWORD}
            testId="reset-password-confirm"
          />

          {localError ? (
            <p
              role="alert"
              className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200 ring-1 ring-rose-400/30"
              data-testid="reset-password-error"
            >
              {localError}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={pending || !tokenFromUrl}
            className="rounded-lg bg-cyan-500/20 px-4 py-2.5 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="reset-password-submit"
          >
            {pending ? "Updating…" : "Reset password"}
          </button>
        </form>
      )}

      <p className="text-sm text-slate-400">
        <Link href="/login" className="text-cyan-300 hover:text-cyan-200">
          Back to login
        </Link>
      </p>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex min-h-screen w-full max-w-lg items-center px-6 py-12 text-slate-400">
          Loading…
        </main>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
