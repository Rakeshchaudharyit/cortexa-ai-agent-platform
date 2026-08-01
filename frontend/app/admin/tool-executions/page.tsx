"use client";

import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { DataTable } from "@/components/admin/DataTable";
import { FilterBar, FilterInput, FilterSelect } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminToolExecutions } from "@/services/admin";

export default function Page() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      const params: Record<string, string | number | undefined> = { limit: 50 };
      if (status) params.status = status;
      if (q) params.tool_name = q;
      const result = await fetchAdminToolExecutions(params);
      if (cancelled) return;
      if (result.ok) {
        setRows(result.data.items as Record<string, unknown>[]);
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
  }, [q, status]);

  return (
    <div data-testid="admin-tool-executions-page">
      <AdminPageHeader title="Tool Executions" description="Administrative metadata view with privacy-safe fields." />
      <FilterBar>
        <FilterInput
          placeholder="Filter…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="admin-tool-executions-search"
        />
        <FilterSelect
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          data-testid="admin-tool-executions-status-filter"
        >
          <option value="">All</option>
          <option value="active">active</option>
          <option value="ready">ready</option>
          <option value="failed">failed</option>
          <option value="succeeded">succeeded</option>
          <option value="disabled">disabled</option>
        </FilterSelect>
        <p className="ml-auto text-xs text-slate-500">{total} total</p>
      </FilterBar>
      <DataTable
        loading={loading}
        rows={rows.map((r, index) => ({ ...r, id: String(r.id ?? index) })) as Array<Record<string, unknown> & { id: string }>}
        columns={[
          {
            key: "primary",
            header: "Tool",
            render: (r: Record<string, unknown> & { id: string }) =>
              String(r.tool_name ?? r.safe_summary ?? r.filename ?? r.title ?? r.tool_name ?? "—"),
          },
          {
            key: "owner",
            header: "Owner / Actor",
            render: (r: Record<string, unknown> & { id: string }) =>
              String(r.owner_email ?? r.user_email ?? r.actor_email ?? "—"),
          },
          {
            key: "status",
            header: "Status / Type",
            render: (r: Record<string, unknown> & { id: string }) => (
              <StatusBadge status={String(r.status ?? r.target_type ?? "unknown")} />
            ),
          },
          {
            key: "created",
            header: "Created",
            render: (r: Record<string, unknown> & { id: string }) =>
              new Date(String(r.created_at ?? r.started_at ?? Date.now())).toLocaleString(),
          },
        ]}
      />
    </div>
  );
}
