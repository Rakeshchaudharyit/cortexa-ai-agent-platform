"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { DataTable } from "@/components/admin/DataTable";
import {
  ActionResultToast,
  DeletionImpactDialog,
  TypedConfirmationInput,
} from "@/components/admin/DeletionDialogs";
import { FilterBar, FilterInput, FilterSelect } from "@/components/admin/FilterBar";
import { StatusBadge } from "@/components/admin/StatusBadge";
import {
  deleteAdminDocument,
  fetchAdminDocuments,
  fetchDocumentDeletionImpact,
} from "@/services/admin";
import type { AdminDocumentDeletionImpact, AdminDocumentSummary } from "@/types/admin";

export default function Page() {
  const [rows, setRows] = useState<AdminDocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [total, setTotal] = useState(0);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [pending, setPending] = useState<AdminDocumentSummary | null>(null);
  const [impact, setImpact] = useState<AdminDocumentDeletionImpact | null>(null);
  const [typedName, setTypedName] = useState("");
  const [deleting, setDeleting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    const params: Record<string, string | number | undefined> = { limit: 50 };
    if (status) params.status = status;
    if (q) params.search = q;
    const result = await fetchAdminDocuments(params);
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

  async function openDelete(doc: AdminDocumentSummary) {
    const result = await fetchDocumentDeletionImpact(doc.id);
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setPending(doc);
    setImpact(result.data);
    setTypedName("");
  }

  async function confirmDelete() {
    if (!pending || !impact) return;
    if (typedName !== impact.filename) return;
    setDeleting(true);
    const result = await deleteAdminDocument(pending.id, typedName);
    setDeleting(false);
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setPending(null);
    setImpact(null);
    setToast({ message: "Document deleted", tone: "success" });
    await reload();
  }

  return (
    <div data-testid="admin-documents-page">
      <AdminPageHeader
        title="Documents"
        description="Administrative metadata view. Permanent delete removes chunks, embeddings, and stored files."
      />
      <ActionResultToast message={toast?.message ?? null} tone={toast?.tone} />
      <FilterBar>
        <FilterInput
          placeholder="Filter…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="admin-documents-search"
        />
        <FilterSelect
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          data-testid="admin-documents-status-filter"
        >
          <option value="">All</option>
          <option value="pending">pending</option>
          <option value="processing">processing</option>
          <option value="ready">ready</option>
          <option value="failed">failed</option>
        </FilterSelect>
        <p className="ml-auto text-xs text-slate-500">{total} total</p>
      </FilterBar>
      <DataTable
        loading={loading}
        rows={rows}
        columns={[
          { key: "filename", header: "Filename", render: (r) => r.filename },
          { key: "owner", header: "Owner", render: (r) => r.owner_email ?? "—" },
          {
            key: "status",
            header: "Status",
            render: (r) => <StatusBadge status={r.status} />,
          },
          {
            key: "chunks",
            header: "Chunks",
            render: (r) => String(r.chunk_count),
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
              <button
                type="button"
                className="text-rose-300 hover:underline"
                data-testid={`admin-document-delete-${r.id}`}
                onClick={() => void openDelete(r)}
              >
                Delete
              </button>
            ),
          },
        ]}
      />
      <DeletionImpactDialog
        open={pending !== null}
        title="Permanently delete document"
        warning="Embeddings and the stored upload file will be removed. This cannot be undone."
        loading={deleting}
        confirmEnabled={Boolean(impact && typedName === impact.filename)}
        impact={
          impact
            ? [
                { label: "Filename", value: impact.filename },
                { label: "Owner", value: impact.owner_email ?? "—" },
                { label: "Chunks", value: impact.chunk_count },
                { label: "Stored file", value: impact.has_stored_file ? "yes" : "no" },
              ]
            : []
        }
        typedConfirmation={
          impact ? (
            <TypedConfirmationInput
              label="Type the filename to confirm:"
              expected={impact.filename}
              value={typedName}
              onChange={setTypedName}
              testId="admin-document-filename-confirm"
            />
          ) : null
        }
        onCancel={() => {
          setPending(null);
          setImpact(null);
        }}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
