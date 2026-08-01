"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminUser, patchAdminUser, revokeAdminUserSessions } from "@/services/admin";
import type { AdminUserDetail } from "@/types/admin";

export default function AdminUserDetailPage() {
  const params = useParams<{ userId: string }>();
  const router = useRouter();
  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | { kind: "disable" | "role" | "revoke"; value?: string }>(null);
  const [message, setMessage] = useState<string | null>(null);

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

  async function apply() {
    if (!user || !confirm) return;
    if (confirm.kind === "disable") {
      const result = await patchAdminUser(user.id, {
        status: user.status === "active" ? "disabled" : "active",
      });
      setMessage(result.ok ? `Updated. Sessions revoked: ${result.data.sessions_revoked}` : result.error);
    } else if (confirm.kind === "role") {
      const result = await patchAdminUser(user.id, {
        role: user.role === "admin" ? "user" : "admin",
      });
      setMessage(result.ok ? "Role updated" : result.error);
    } else if (confirm.kind === "revoke") {
      const result = await revokeAdminUserSessions(user.id);
      setMessage(result.ok ? `Revoked ${result.data.sessions_revoked} sessions` : result.error);
    }
    setConfirm(null);
    await reload();
  }

  if (error) return <p className="text-rose-300">{error}</p>;
  if (!user) return <div className="h-40 animate-pulse rounded-2xl bg-slate-800/40" data-testid="admin-user-detail-loading" />;

  return (
    <div data-testid="admin-user-detail">
      <AdminPageHeader
        title={user.full_name}
        description={user.email}
        actions={
          <button type="button" className="text-sm text-slate-400 hover:text-white" onClick={() => router.push("/admin/users")}>
            ← Users
          </button>
        }
      />
      {message ? <p className="mb-4 text-sm text-cyan-200" data-testid="admin-user-action-message">{message}</p> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4 text-sm text-slate-300">
          <p>Role: <StatusBadge status={user.role} /></p>
          <p className="mt-2">Status: <StatusBadge status={user.status} /></p>
          <p className="mt-2">Verified: {user.is_email_verified ? "Yes" : "No"}</p>
          <p className="mt-2">Created: {new Date(user.created_at).toLocaleString()}</p>
          <p className="mt-2">Last login: {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "—"}</p>
          <p className="mt-2">Active sessions: {user.active_sessions_count}</p>
          <p className="mt-2">Conversations / documents / memories: {user.conversations_count} / {user.documents_count} / {user.memories_count}</p>
          <p className="mt-2">Tool executions: {user.tool_executions_count} (ok {user.tool_success_count} / fail {user.tool_failure_count})</p>
          <p className="mt-4 text-xs text-slate-500">Password hashes are never displayed.</p>
        </section>
        <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4 space-y-3">
          <button type="button" className="w-full rounded-lg bg-amber-500/15 px-3 py-2 text-sm text-amber-100 ring-1 ring-amber-400/30" data-testid="admin-user-toggle-status" onClick={() => setConfirm({ kind: "disable" })}>
            {user.status === "active" ? "Disable account" : "Enable account"}
          </button>
          <button type="button" className="w-full rounded-lg bg-cyan-500/15 px-3 py-2 text-sm text-cyan-100 ring-1 ring-cyan-400/30" data-testid="admin-user-toggle-role" onClick={() => setConfirm({ kind: "role" })}>
            {user.role === "admin" ? "Demote to user" : "Promote to admin"}
          </button>
          <button type="button" className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100 ring-1 ring-white/10" data-testid="admin-user-revoke-sessions" onClick={() => setConfirm({ kind: "revoke" })}>
            Revoke refresh sessions
          </button>
        </section>
      </div>
      <ConfirmDialog
        open={confirm !== null}
        title="Confirm administrative action"
        message="This change is audited. Disabling an account also revokes active sessions."
        danger={confirm?.kind === "disable"}
        onCancel={() => setConfirm(null)}
        onConfirm={() => void apply()}
      />
    </div>
  );
}
