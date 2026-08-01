"use client";

import { useEffect, useId, useRef } from "react";

export function TypedConfirmationInput({
  label,
  expected,
  value,
  onChange,
  placeholder,
  testId = "typed-confirmation-input",
}: {
  label: string;
  expected: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  testId?: string;
}) {
  const id = useId();
  const matches = value.trim() === expected;
  return (
    <div className="mt-4">
      <label htmlFor={id} className="text-sm text-slate-300">
        {label}{" "}
        <span className="font-mono text-rose-200">{expected}</span>
      </label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? expected}
        autoComplete="off"
        className={`mt-2 w-full rounded-lg border bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 ${
          value && !matches
            ? "border-rose-400/40 focus:ring-rose-400/30"
            : "border-white/10 focus:ring-cyan-400/30"
        }`}
        data-testid={testId}
        aria-invalid={Boolean(value) && !matches}
      />
    </div>
  );
}

export function ConfirmDeleteDialog({
  open,
  title,
  warning,
  confirmLabel = "Delete permanently",
  cancelLabel = "Cancel",
  loading,
  confirmEnabled = true,
  onConfirm,
  onCancel,
  children,
}: {
  open: boolean;
  title: string;
  warning: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  confirmEnabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children?: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onCancelRef.current();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center p-3 sm:items-center sm:p-4"
      data-testid="admin-delete-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-delete-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/75"
        aria-label="Cancel"
        onClick={onCancel}
      />
      <div
        ref={dialogRef}
        className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-rose-500/25 bg-slate-950 p-5 shadow-2xl sm:p-6"
      >
        <h3 id="admin-delete-title" className="text-lg font-semibold text-white">
          {title}
        </h3>
        <p className="mt-2 text-sm text-rose-100/80">{warning}</p>
        {children}
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-900 ring-1 ring-white/10"
            onClick={onCancel}
            disabled={loading}
            data-testid="admin-delete-cancel"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className="rounded-lg bg-rose-500/25 px-4 py-2 text-sm font-medium text-rose-50 ring-1 ring-rose-400/40 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={onConfirm}
            disabled={loading || !confirmEnabled}
            data-testid="admin-delete-confirm"
          >
            {loading ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function DeletionImpactDialog({
  open,
  title,
  warning,
  impact,
  loading,
  confirmEnabled,
  confirmLabel,
  onConfirm,
  onCancel,
  typedConfirmation,
}: {
  open: boolean;
  title: string;
  warning: string;
  impact: Array<{ label: string; value: string | number }>;
  loading?: boolean;
  confirmEnabled?: boolean;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  typedConfirmation?: React.ReactNode;
}) {
  return (
    <ConfirmDeleteDialog
      open={open}
      title={title}
      warning={warning}
      loading={loading}
      confirmEnabled={confirmEnabled}
      confirmLabel={confirmLabel}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <dl className="mt-4 grid grid-cols-2 gap-2 rounded-xl bg-slate-900/70 p-3 text-sm" data-testid="deletion-impact-counts">
        {impact.map((item) => (
          <div key={item.label} className="contents">
            <dt className="text-slate-400">{item.label}</dt>
            <dd className="text-right font-medium text-slate-100">{item.value}</dd>
          </div>
        ))}
      </dl>
      {typedConfirmation}
    </ConfirmDeleteDialog>
  );
}

export function ActionResultToast({
  message,
  tone = "success",
}: {
  message: string | null;
  tone?: "success" | "error";
}) {
  if (!message) return null;
  return (
    <p
      role="status"
      className={`mb-4 rounded-lg px-3 py-2 text-sm ring-1 ${
        tone === "error"
          ? "bg-rose-500/10 text-rose-200 ring-rose-400/30"
          : "bg-emerald-500/10 text-emerald-200 ring-emerald-400/30"
      }`}
      data-testid="admin-action-toast"
    >
      {message}
    </p>
  );
}
