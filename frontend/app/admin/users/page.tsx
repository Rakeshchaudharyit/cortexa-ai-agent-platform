"use client";

import { useEffect, useState } from "react";
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
      const result = await fetchAdminUsers({
        search: search || undefined,
        role: role || undefined,
        status: status || undefined,
        limit: 50,
      });
      if (cancelled) return;
      if (result.ok) {
        setRows(result.data.items);
        setTotal(result.data.total);
      } else {
        setRows([]);
        setTotal(0);
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [search, role, status]);

  return (
    <div data-testid="admin-users-page">
      <AdminPageHeader
        title="Users"
        description="Search accounts, deactivate access, or permanently delete with impact preview and typed confirmation."
      />
      <FilterBar>
        <FilterInput
          placeholder="Search name or email"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="admin-users-search"
        />
        <FilterSelect
          value={role}
          onChange={(e) => setRole(e.target.value)}
          data-testid="admin-users-role-filter"
        >
          <option value="">All roles</option>
          <option value="user">User</option>
          <option value="admin">Admin</option>
        </FilterSelect>
        <FilterSelect
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          data-testid="admin-users-status-filter"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </FilterSelect>
        <p className="ml-auto text-xs text-slate-500">{total} total</p>
      </FilterBar>
      <DataTable
        loading={loading}
        rows={rows}
        columns={[
          { key: "name", header: "Name", render: (r) => r.full_name },
          { key: "email", header: "Email", render: (r) => r.email },
          { key: "role", header: "Role", render: (r) => <StatusBadge status={r.role} /> },
          { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
          {
            key: "verified",
            header: "Verified",
            render: (r) => (r.is_email_verified ? "Yes" : "No"),
          },
          {
            key: "created",
            header: "Created",
            render: (r) => new Date(r.created_at).toLocaleDateString(),
          },
          {
            key: "counts",
            header: "Conv / Docs / Mem",
            render: (r) =>
              `${r.conversations_count} / ${r.documents_count} / ${r.memories_count}`,
          },
          {
            key: "actions",
            header: "",
            render: (r) => (
              <button
                type="button"
                className="text-cyan-300 hover:underline"
                onClick={() => router.push(`/admin/users/${r.id}`)}
                data-testid="admin-user-view"
              >
                View
              </button>
            ),
          },
        ]}
      />
    </div>
  );
}
