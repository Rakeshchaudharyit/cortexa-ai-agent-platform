"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { DataTable } from "@/components/admin/DataTable";
import { FilterBar, FilterInput, FilterSelect } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminUsers } from "@/services/admin";
import type { AdminUserSummary } from "@/types/admin";

export default function AdminUsersPage() {
  const router = useRouter();
  const [rows, setRows] = useState<AdminUserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      const result = await fetchAdminUsers({ search: search || undefined, role: role || undefined, status: status || undefined, limit: 50 });
      if (cancelled) return;
      if (result.ok) { setRows(result.data.items); setTotal(result.data.total); } else { setRows([]); setTotal(0); }
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [search, role, status]);

  const activeUsers = useMemo(() => rows.filter((user) => user.status === "active").length, [rows]);
  const admins = useMemo(() => rows.filter((user) => user.role === "admin").length, [rows]);
  const verified = useMemo(() => rows.filter((user) => user.is_email_verified).length, [rows]);

  return <div className="space-y-6" data-testid="admin-users-page">
    <AdminPageHeader title="Users" description="Manage account access, roles, activity, and ownership across the Cortexa workspace." />
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div className="rounded-2xl border border-white/8 bg-slate-900/50 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Accounts</p><p className="mt-2 text-2xl font-semibold text-white">{total}</p><p className="mt-1 text-xs text-slate-500">Across the workspace</p></div>
      <div className="rounded-2xl border border-white/8 bg-slate-900/50 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Active shown</p><p className="mt-2 text-2xl font-semibold text-emerald-200">{activeUsers}</p><p className="mt-1 text-xs text-slate-500">In current result set</p></div>
      <div className="rounded-2xl border border-white/8 bg-slate-900/50 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Administrators</p><p className="mt-2 text-2xl font-semibold text-cyan-200">{admins}</p><p className="mt-1 text-xs text-slate-500">Privileged accounts shown</p></div>
      <div className="rounded-2xl border border-white/8 bg-slate-900/50 p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Email verified</p><p className="mt-2 text-2xl font-semibold text-white">{verified}</p><p className="mt-1 text-xs text-slate-500">In current result set</p></div>
    </div>
    <section className="rounded-2xl border border-white/8 bg-slate-900/40 p-4">
      <FilterBar>
        <FilterInput placeholder="Search name or email" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="admin-users-search" />
        <FilterSelect value={role} onChange={(e) => setRole(e.target.value)} data-testid="admin-users-role-filter"><option value="">All roles</option><option value="user">User</option><option value="admin">Admin</option></FilterSelect>
        <FilterSelect value={status} onChange={(e) => setStatus(e.target.value)} data-testid="admin-users-status-filter"><option value="">All statuses</option><option value="active">Active</option><option value="disabled">Disabled</option></FilterSelect>
        <p className="ml-auto text-xs text-slate-500">{total} total accounts</p>
      </FilterBar>
    </section>
    <DataTable loading={loading} rows={rows} emptyTitle="No users found" emptyDescription="Try a different search term or filter." columns={[
      { key: "name", header: "User", render: (r) => <div><p className="font-medium text-white">{r.full_name || "Unnamed user"}</p><p className="mt-0.5 text-xs text-slate-500">{r.email}</p></div> },
      { key: "role", header: "Role", render: (r) => <StatusBadge status={r.role} /> },
      { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
      { key: "verified", header: "Verification", render: (r) => <span className={r.is_email_verified ? "text-emerald-300" : "text-amber-300"}>{r.is_email_verified ? "Verified" : "Pending"}</span> },
      { key: "created", header: "Joined", render: (r) => new Date(r.created_at).toLocaleDateString() },
      { key: "counts", header: "Workspace activity", render: (r) => <span className="text-xs text-slate-300">{r.conversations_count} chats · {r.documents_count} docs · {r.memories_count} memories</span> },
      { key: "actions", header: "", render: (r) => <button type="button" className="rounded-lg border border-cyan-400/20 px-3 py-1.5 text-xs font-medium text-cyan-200 hover:bg-cyan-400/8" onClick={() => router.push(`/admin/users/${r.id}`)} data-testid="admin-user-view">View account</button> },
    ]} />
  </div>;
}
