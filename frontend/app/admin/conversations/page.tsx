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
  archiveAdminConversation,
  deleteAdminConversation,
  fetchAdminConversations,
  fetchConversationDeletionImpact,
} from "@/services/admin";
import type {
  AdminConversationDeletionImpact,
  AdminConversationSummary,
} from "@/types/admin";

export default function Page() {
  const [rows, setRows] = useState<AdminConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [total, setTotal] = useState(0);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<AdminConversationSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminConversationSummary | null>(null);
  const [impact, setImpact] = useState<AdminConversationDeletionImpact | null>(null);
  const [deleting, setDeleting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    const params: Record<string, string | number | undefined> = { limit: 50 };
    if (status) params.status = status;
    if (q) params.search = q;
    const result = await fetchAdminConversations(params);
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

  async function openDelete(row: AdminConversationSummary) {
    const result = await fetchConversationDeletionImpact(row.id);
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setImpact(result.data);
    setDeleteTarget(row);
  }

  return (
    <div data-testid="admin-conversations-page">
      <AdminPageHeader
        title="Conversations"
        description="Archive for soft retention, or permanently delete messages and citations."
      />
      <ActionResultToast message={toast?.message ?? null} tone={toast?.tone} />
      <FilterBar>
        <FilterInput
          placeholder="Filter…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="admin-conversations-search"
        />
        <FilterSelect
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          data-testid="admin-conversations-status-filter"
        >
          <option value="">All</option>
          <option value="active">active</option>
          <option value="archived">archived</option>
        </FilterSelect>
        <p className="ml-auto text-xs text-slate-500">{total} total</p>
      </FilterBar>
      <DataTable
        loading={loading}
        rows={rows}
        columns={[
          { key: "title", header: "Title", render: (r) => r.title || "—" },
          { key: "owner", header: "Owner", render: (r) => r.owner_email ?? "—" },
          {
            key: "status",
            header: "Status",
            render: (r) => <StatusBadge status={r.status} />,
          },
          {
            key: "messages",
            header: "Messages",
            render: (r) => String(r.message_count),
          },
          {
            key: "created",
            header: "Created",
            render: (r) => new Date(r.created_at).toLocaleString(),
          },
          {
            key: "actions",
            header: "",
            render: (r) => (
              <div className="flex flex-wrap gap-2">
                {r.status !== "archived" ? (
                  <button
                    type="button"
                    className="text-amber-300 hover:underline"
                    data-testid={`admin-conversation-archive-${r.id}`}
                    onClick={() => setArchiveTarget(r)}
                  >
                    Archive
                  </button>
                ) : null}
                <button
                  type="button"
                  className="text-rose-300 hover:underline"
                  data-testid={`admin-conversation-delete-${r.id}`}
                  onClick={() => void openDelete(r)}
                >
                  Delete permanently
                </button>
              </div>
            ),
          },
        ]}
      />
      <ConfirmDialog
        open={archiveTarget !== null}
        title="Archive conversation"
        message="Archiving hides the conversation from the active list. It can be restored by the owner."
        confirmLabel="Archive"
        onCancel={() => setArchiveTarget(null)}
        onConfirm={() => {
          if (!archiveTarget) return;
          void (async () => {
            const result = await archiveAdminConversation(archiveTarget.id);
            setArchiveTarget(null);
            setToast(
              result.ok
                ? { message: "Conversation archived", tone: "success" }
                : { message: result.error, tone: "error" },
            );
            await reload();
          })();
        }}
      />
      <DeletionImpactDialog
        open={deleteTarget !== null}
        title="Permanently delete conversation"
        warning="Messages and citations will be removed. Linked tool executions remain anonymized by conversation reference. Memory source links become null."
        loading={deleting}
        confirmLabel="Delete permanently"
        confirmEnabled
        impact={
          impact
            ? [
                { label: "Title", value: impact.title || "—" },
                { label: "Owner", value: impact.owner_email ?? "—" },
                { label: "Messages", value: impact.messages },
                { label: "Citations", value: impact.citations },
                { label: "Tool executions", value: impact.tool_executions },
                { label: "Linked memories", value: impact.linked_memories },
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
            const result = await deleteAdminConversation(deleteTarget.id);
            setDeleting(false);
            if (!result.ok) {
              setToast({ message: result.error, tone: "error" });
              return;
            }
            setDeleteTarget(null);
            setImpact(null);
            setToast({ message: "Conversation permanently deleted", tone: "success" });
            await reload();
          })();
        }}
      />
    </div>
  );
}
