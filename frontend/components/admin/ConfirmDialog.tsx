"use client";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  danger,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="admin-confirm-dialog">
      <button type="button" className="absolute inset-0 bg-black/70" aria-label="Cancel" onClick={onCancel} />
      <div className="relative w-full max-w-md rounded-2xl border border-white/10 bg-slate-950 p-6 shadow-2xl">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="mt-2 text-sm text-slate-300">{message}</p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-100 ring-1 ring-white/10"
            onClick={onCancel}
            data-testid="admin-confirm-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              danger
                ? "bg-rose-500/20 text-rose-100 ring-1 ring-rose-400/40"
                : "bg-cyan-500/20 text-cyan-100 ring-1 ring-cyan-400/40"
            }`}
            onClick={onConfirm}
            data-testid="admin-confirm-ok"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
