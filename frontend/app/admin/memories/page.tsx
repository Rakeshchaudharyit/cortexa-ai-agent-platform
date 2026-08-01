"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DataTable } from "@/components/admin/DataTable";
import {
  ActionResultToast,
  DeletionImpactDialog,
} from "@/components/admin/DeletionDialogs";
import { FilterBar, FilterInput, FilterSelect } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import {
  archiveAdminMemory,
  deleteAdminMemory,
  fetchAdminMemories,
  fetchMemoryDeletionImpact,
} from "@/services/admin";
import type { AdminMemoryDeletionImpact, AdminMemorySummary } from "@/types/admin";

export default function Page() {
  const [rows, setRows] = useState<AdminMemorySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [total, setTotal] = useState(0);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<AdminMemorySummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminMemorySummary | null>(null);
  const [impact, setImpact] = useState<AdminMemoryDeletionImpact | null>(null);
  const [deleting, setDeleting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    const params: Record<string, string | number | undefined> = { limit: 50 };
    if (status) params.status = status;
    if (q) params.search = q;
    const result = await fetchAdminMemories(params);
    if (result.ok) {
      setRows(result.data.items);
      setTotal(result.data.total);
    } else {
      setRows([]);
      setTotal(0);
    }
    setLoading(false);
  }, [q, status]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function openDelete(row: AdminMemorySummary) {
    const result = await fetchMemoryDeletionImpact(row.id);
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setImpact(result.data);
    setDeleteTarget(row);
  }

  return (
    <div data-testid="admin-memories-page">
      <AdminPageHeader
        title="Memories"
        description="Archive, or delete and redact memory content so it is excluded from retrieval."
      />
      <ActionResultToast message={toast?.message ?? null} tone={toast?.tone} />
      <FilterBar>
        <FilterInput
          placeholder="Filter…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="admin-memories-search"
        />
        <FilterSelect
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          data-testid="admin-memories-status-filter"
        >
          <option value="">All</option>
          <option value="active">active</option>
          <option value="proposed">proposed</option>
          <option value="archived">archived</option>
          <option value="rejected">rejected</option>
          <option value="deleted">deleted</option>
        </FilterSelect>
        <p className="ml-auto text-xs text-slate-500">{total} total</p>
      </FilterBar>
      <DataTable
        loading={loading}
        rows={rows}
        columns={[
          { key: "title", header: "Title", render: (r) => r.title },
          { key: "owner", header: "Owner", render: (r) => r.owner_email ?? "—" },
          {
            key: "status",
            header: "Status",
            render: (r) => <StatusBadge status={r.status} />,
          },
          {
            key: "created",
            header: "Created",
            render: (r) => new Date(r.created_at).toLocaleString(),
          },
          {
            key: "actions",
            header: "",
            render: (r) =>
              r.status === "deleted" ? (
                <span className="text-xs text-slate-500">Redacted</span>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {r.status !== "archived" ? (
                    <button
                      type="button"
                      className="text-amber-300 hover:underline"
                      data-testid={`admin-memory-archive-${r.id}`}
                      onClick={() => setArchiveTarget(r)}
                    >
                      Archive
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="text-rose-300 hover:underline"
                    data-testid={`admin-memory-delete-${r.id}`}
                    onClick={() => void openDelete(r)}
                  >
                    Delete and redact
                  </button>
                </div>
              ),
          },
        ]}
      />
      <ConfirmDialog
        open={archiveTarget !== null}
        title="Archive memory"
        message="Archived memories are excluded from active retrieval."
        confirmLabel="Archive"
        onCancel={() => setArchiveTarget(null)}
        onConfirm={() => {
          if (!archiveTarget) return;
          void (async () => {
            const result = await archiveAdminMemory(archiveTarget.id);
            setArchiveTarget(null);
            setToast(
              result.ok
                ? { message: "Memory archived", tone: "success" }
                : { message: result.error, tone: "error" },
            );
            await reload();
          })();
        }}
      />
      <DeletionImpactDialog
        open={deleteTarget !== null}
        title="Delete and redact memory"
        warning="Content and embeddings will be redacted. The memory will never be retrieved again. Audit metadata is retained without raw content."
        confirmLabel="Delete and redact"
        loading={deleting}
        confirmEnabled={Boolean(impact?.can_delete)}
        impact={
          impact
            ? [
                { label: "Title", value: impact.title },
                { label: "Owner", value: impact.owner_email ?? "—" },
                { label: "Status", value: impact.status },
                { label: "Embedding", value: impact.has_embedding ? "present" : "none" },
              ]
            : []
        }
        onCancel={() => {
          setDeleteTarget(null);
          setImpact(null);
        }}
        onConfirm={() => {
          if (!deleteTarget) return;
          void (async () => {
            setDeleting(true);
            const result = await deleteAdminMemory(deleteTarget.id);
            setDeleting(false);
            if (!result.ok) {
              setToast({ message: result.error, tone: "error" });
              return;
            }
            setDeleteTarget(null);
            setImpact(null);
            setToast({ message: "Memory deleted and redacted", tone: "success" });
            await reload();
          })();
        }}
      />
    </div>
  );
}
