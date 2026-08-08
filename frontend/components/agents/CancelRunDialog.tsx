"use client";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";

export function CancelRunDialog({ open, busy, onConfirm, onCancel }: { open: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void }) {
  return <ConfirmDialog open={open} title="Cancel coordinated response?" message="No new specialist tasks will start. Completed safe task summaries will remain in the run history." confirmLabel={busy ? "Cancelling…" : "Cancel run"} danger onConfirm={onConfirm} onCancel={onCancel} />;
}
