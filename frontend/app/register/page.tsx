"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { PasswordField } from "@/components/PasswordField";

const MIN_PASSWORD = 12;

export default function RegisterPage() {
  const router = useRouter();
  const { register, status, error, clearError } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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

    if (!fullName.trim() || !email.trim() || !password || !confirmPassword) {
      setLocalError("All fields are required.");
      return;
    }
    if (password.length < MIN_PASSWORD) {
      setLocalError(`Password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (password !== confirmPassword) {
      setLocalError("Passwords do not match.");
      return;
    }

    setPending(true);
    const result = await register({
      email: email.trim(),
      password,
      confirm_password: confirmPassword,
      full_name: fullName.trim(),
    });
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
          Authentication
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-50">
          Create an account
        </h1>
        <p className="text-sm leading-relaxed text-slate-400">
          Register to access protected LLM generation endpoints. Passwords are not trimmed.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
        noValidate
        data-testid="register-form"
      >
        <div className="flex flex-col gap-2">
          <label htmlFor="full_name" className="text-sm font-medium text-slate-200">
            Full name
          </label>
          <input
            id="full_name"
            name="full_name"
            type="text"
            autoComplete="name"
            required
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            className="rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2 text-slate-100 outline-none transition focus:ring-2 focus:ring-cyan-400/40"
            data-testid="register-full-name"
          />
        </div>

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
            data-testid="register-email"
          />
        </div>

        <PasswordField
          id="password"
          name="password"
          label="Password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="new-password"
          minLength={MIN_PASSWORD}
          hint={`At least ${MIN_PASSWORD} characters. Passphrases are allowed.`}
          testId="register-password"
        />
        <PasswordField
          id="confirm_password"
          name="confirm_password"
          label="Confirm password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          autoComplete="new-password"
          minLength={MIN_PASSWORD}
          testId="register-confirm-password"
        />

        {displayError ? (
          <p
            role="alert"
            className="rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-200 ring-1 ring-rose-400/30"
            data-testid="register-error"
          >
            {displayError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={pending || status === "loading"}
          className="rounded-lg bg-cyan-500/20 px-4 py-2.5 text-sm font-medium text-cyan-100 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="register-submit"
        >
          {pending ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="text-sm text-slate-400">
        Already registered?{" "}
        <Link href="/login" className="text-cyan-300 hover:text-cyan-200">
          Log in
        </Link>
      </p>
    </main>
  );
}
