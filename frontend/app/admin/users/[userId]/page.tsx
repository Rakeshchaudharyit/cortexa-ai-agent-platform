"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DangerZone } from "@/components/admin/DangerZone";
import {
  ActionResultToast,
  DeletionImpactDialog,
  TypedConfirmationInput,
} from "@/components/admin/DeletionDialogs";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { useAuth } from "@/components/AuthProvider";
import {
  activateAdminUser,
  deactivateAdminUser,
  deleteAdminUser,
  fetchAdminUser,
  fetchUserDeletionImpact,
  patchAdminUser,
  revokeAdminUserSessions,
} from "@/services/admin";
import type { AdminUserDeletionImpact, AdminUserDetail } from "@/types/admin";

export default function AdminUserDetailPage() {
  const params = useParams<{ userId: string }>();
  const router = useRouter();
  const { user: actor } = useAuth();
  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | { kind: "role" | "revoke" }>(null);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [impact, setImpact] = useState<AdminUserDeletionImpact | null>(null);
  const [typedEmail, setTypedEmail] = useState("");
  const [deleting, setDeleting] = useState(false);

  const reload = useCallback(async () => {
    const result = await fetchAdminUser(params.userId);
    if (!result.ok) {
      setError(result.error);
      setUser(null);
      return;
    }
    setUser(result.data);
    setError(null);
  }, [params.userId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const isSelf = Boolean(actor && user && actor.id === user.id);
  const lastAdminBlocked = Boolean(
    impact && !impact.can_delete && impact.blocking_reason?.toLowerCase().includes("last active admin"),
  );

  async function applyRoleOrRevoke() {
    if (!user || !confirm) return;
    if (confirm.kind === "role") {
      const result = await patchAdminUser(user.id, {
        role: user.role === "admin" ? "user" : "admin",
      });
      setToast(
        result.ok
          ? { message: "Role updated", tone: "success" }
          : { message: result.error, tone: "error" },
      );
    } else if (confirm.kind === "revoke") {
      const result = await revokeAdminUserSessions(user.id);
      setToast(
        result.ok
          ? { message: `Revoked ${result.data.sessions_revoked} sessions`, tone: "success" }
          : { message: result.error, tone: "error" },
      );
    }
    setConfirm(null);
    await reload();
  }

  async function toggleActive() {
    if (!user) return;
    const result =
      user.status === "active"
        ? await deactivateAdminUser(user.id)
        : await activateAdminUser(user.id);
    setDeactivateOpen(false);
    setToast(
      result.ok
        ? {
            message:
              user.status === "active"
                ? `Account deactivated. Sessions revoked: ${result.data.sessions_revoked}`
                : "Account activated",
            tone: "success",
          }
        : { message: result.error, tone: "error" },
    );
    await reload();
  }

  async function openDelete() {
    if (!user || isSelf) return;
    const result = await fetchUserDeletionImpact(user.id);
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setImpact(result.data);
    setTypedEmail("");
    setDeleteOpen(true);
  }

  async function confirmDelete() {
    if (!user || !impact?.can_delete) return;
    if (typedEmail.trim().toLowerCase() !== user.email.toLowerCase()) return;
    setDeleting(true);
    const result = await deleteAdminUser(user.id, typedEmail.trim());
    setDeleting(false);
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setDeleteOpen(false);
    setToast({
      message: `User permanently deleted (fingerprint ${result.data.email_fingerprint})`,
      tone: "success",
    });
    router.push("/admin/users");
  }

  if (error) return <p className="text-rose-300">{error}</p>;
  if (!user)
    return (
      <div
        className="h-40 animate-pulse rounded-2xl bg-slate-800/40"
        data-testid="admin-user-detail-loading"
      />
    );

  return (
    <div data-testid="admin-user-detail">
      <AdminPageHeader
        title={user.full_name}
        description={user.email}
        actions={
          <button
            type="button"
            className="text-sm text-slate-400 hover:text-white"
            onClick={() => router.push("/admin/users")}
          >
            ← Users
          </button>
        }
      />
      <ActionResultToast message={toast?.message ?? null} tone={toast?.tone} />
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4 text-sm text-slate-300">
          <p>
            Role: <StatusBadge status={user.role} />
          </p>
          <p className="mt-2">
            Status: <StatusBadge status={user.status} />
          </p>
          <p className="mt-2">Verified: {user.is_email_verified ? "Yes" : "No"}</p>
          <p className="mt-2">Created: {new Date(user.created_at).toLocaleString()}</p>
          <p className="mt-2">
            Last login: {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "—"}
          </p>
          <p className="mt-2">Active sessions: {user.active_sessions_count}</p>
          <p className="mt-2">
            Conversations / documents / memories: {user.conversations_count} /{" "}
            {user.documents_count} / {user.memories_count}
          </p>
          <p className="mt-2">
            Tool executions: {user.tool_executions_count} (ok {user.tool_success_count} / fail{" "}
            {user.tool_failure_count})
          </p>
          <p className="mt-4 text-xs text-slate-500">Password hashes are never displayed.</p>
        </section>
        <section className="space-y-3 rounded-2xl border border-white/8 bg-slate-900/40 p-4">
          <button
            type="button"
            className="w-full rounded-lg bg-amber-500/15 px-3 py-2 text-sm text-amber-100 ring-1 ring-amber-400/30"
            data-testid="admin-user-toggle-status"
            onClick={() => setDeactivateOpen(true)}
          >
            {user.status === "active" ? "Deactivate account" : "Activate account"}
          </button>
          <button
            type="button"
            className="w-full rounded-lg bg-cyan-500/15 px-3 py-2 text-sm text-cyan-100 ring-1 ring-cyan-400/30"
            data-testid="admin-user-toggle-role"
            onClick={() => setConfirm({ kind: "role" })}
          >
            {user.role === "admin" ? "Demote to user" : "Promote to admin"}
          </button>
          <button
            type="button"
            className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100 ring-1 ring-white/10"
            data-testid="admin-user-revoke-sessions"
            onClick={() => setConfirm({ kind: "revoke" })}
          >
            Revoke refresh sessions
          </button>
        </section>
      </div>

      <div className="mt-6">
        <DangerZone
          title="Permanent deletion"
          description="Prefer deactivation. Permanent deletion anonymizes governance records and removes owned content."
        >
          <button
            type="button"
            className="rounded-lg bg-rose-500/20 px-4 py-2 text-sm text-rose-50 ring-1 ring-rose-400/40 disabled:cursor-not-allowed disabled:opacity-40"
            data-testid="admin-user-permanent-delete"
            disabled={isSelf}
            title={isSelf ? "Cannot delete your own account" : undefined}
            onClick={() => void openDelete()}
          >
            Permanently delete user
          </button>
          {isSelf ? (
            <p className="text-xs text-rose-200/70" data-testid="admin-self-delete-blocked">
              Self-deletion is not available.
            </p>
          ) : null}
        </DangerZone>
      </div>

      <ConfirmDialog
        open={confirm !== null}
        title="Confirm administrative action"
        message="This change is audited."
        danger={false}
        onCancel={() => setConfirm(null)}
        onConfirm={() => void applyRoleOrRevoke()}
      />
      <ConfirmDialog
        open={deactivateOpen}
        title={user.status === "active" ? "Deactivate account" : "Activate account"}
        message={
          user.status === "active"
            ? "Deactivation revokes refresh sessions and is audited."
            : "Reactivate this account. This action is audited."
        }
        danger={user.status === "active"}
        confirmLabel={user.status === "active" ? "Deactivate" : "Activate"}
        onCancel={() => setDeactivateOpen(false)}
        onConfirm={() => void toggleActive()}
      />
      <DeletionImpactDialog
        open={deleteOpen}
        title="Permanently delete user"
        warning="This will remove or anonymize the user’s documents, conversations, memories, and active sessions. This action cannot be undone."
        loading={deleting}
        confirmEnabled={
          Boolean(impact?.can_delete) &&
          typedEmail.trim().toLowerCase() === user.email.toLowerCase()
        }
        impact={
          impact
            ? [
                { label: "Documents", value: impact.documents },
                { label: "Chunks", value: impact.document_chunks },
                { label: "Conversations", value: impact.conversations },
                { label: "Messages", value: impact.messages },
                { label: "Memories", value: impact.memories },
                { label: "Sessions", value: impact.refresh_sessions },
                { label: "Tool executions", value: impact.tool_executions },
              ]
            : []
        }
        typedConfirmation={
          <>
            {impact && !impact.can_delete ? (
              <p className="mt-3 text-sm text-amber-200" data-testid="admin-delete-blocked-reason">
                {impact.blocking_reason}
                {lastAdminBlocked ? " Last-admin safeguard is active." : ""}
              </p>
            ) : (
              <TypedConfirmationInput
                label="Type the user email to confirm:"
                expected={user.email}
                value={typedEmail}
                onChange={setTypedEmail}
                testId="admin-delete-email-confirm"
              />
            )}
          </>
        }
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
