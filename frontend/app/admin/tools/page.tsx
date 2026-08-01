"use client";

import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DataTable } from "@/components/admin/DataTable";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminTools, patchAdminTool } from "@/services/admin";
import type { AdminToolSummary } from "@/types/admin";

export default function AdminToolsPage() {
  const [tools, setTools] = useState<AdminToolSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<AdminToolSummary | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    const result = await fetchAdminTools();
    if (result.ok) setTools(result.data.tools);
    setLoading(false);
  }

  useEffect(() => {
    void reload();
  }, []);

  return (
    <div data-testid="admin-tools-page">
      <AdminPageHeader
        title="Agent Tools"
        description="Enable or disable registered server tools. Arbitrary tool code cannot be uploaded."
      />
      {message ? (
        <p className="mb-3 text-sm text-cyan-200" data-testid="admin-tools-message">
          {message}
        </p>
      ) : null}
      <DataTable
        loading={loading}
        rows={tools.map((t) => ({ ...t, id: t.name }))}
        columns={[
          { key: "name", header: "Name", render: (t) => t.name },
          { key: "category", header: "Category", render: (t) => t.category },
          { key: "version", header: "Version", render: (t) => t.version },
          {
            key: "enabled",
            header: "Enabled",
            render: (t) => <StatusBadge status={t.enabled ? "active" : "disabled"} />,
          },
          {
            key: "stats",
            header: "Executions",
            render: (t) =>
              `${t.execution_count} · ${
                t.success_rate == null ? "n/a" : `${Math.round(t.success_rate * 100)}%`
              }`,
          },
          {
            key: "actions",
            header: "",
            render: (t) => (
              <button
                type="button"
                className="text-cyan-300 hover:underline"
                data-testid={`admin-tool-toggle-${t.name}`}
                onClick={() => setPending(t)}
              >
                {t.enabled ? "Disable" : "Enable"}
              </button>
            ),
          },
        ]}
      />
      <ConfirmDialog
        open={pending !== null}
        title={pending?.enabled ? "Disable tool" : "Enable tool"}
        message={`This changes availability of '${pending?.name}' for all users and is audited.`}
        danger={Boolean(pending?.enabled)}
        onCancel={() => setPending(null)}
        onConfirm={() => {
          if (!pending) return;
          void (async () => {
            const result = await patchAdminTool(pending.name, { enabled: !pending.enabled });
            setMessage(result.ok ? `Updated ${pending.name}` : result.error);
            setPending(null);
            await reload();
          })();
        }}
      />
    </div>
  );
}
