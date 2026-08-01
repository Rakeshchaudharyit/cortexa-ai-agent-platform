"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { fetchAdminSystem } from "@/services/admin";
import type { AdminSystemHealthResponse } from "@/types/admin";

export default function AdminSystemPage() {
  const [data, setData] = useState<AdminSystemHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const result = await fetchAdminSystem();
    if (!result.ok) {
      setError(result.error);
      setData(null);
      return;
    }
    setData(result.data);
    setError(null);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div data-testid="admin-system-page">
      <AdminPageHeader
        title="System health"
        description="Operational status without secrets, connection strings, or filesystem paths."
        actions={
          <button
            type="button"
            className="rounded-lg bg-cyan-500/20 px-3 py-2 text-sm text-cyan-100 ring-1 ring-cyan-400/30"
            onClick={() => void reload()}
            data-testid="admin-system-refresh"
          >
            Refresh
          </button>
        }
      />
      {error ? <p className="text-rose-300">{error}</p> : null}
      {data ? (
        <>
          <p className="mb-4 text-sm text-slate-400">
            Overall <StatusBadge status={data.overall} /> · refreshed{" "}
            {new Date(data.refreshed_at).toLocaleString()}
          </p>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.components.map((component) => (
              <div
                key={component.name}
                className="rounded-2xl border border-white/8 bg-slate-900/40 p-4"
                data-testid="admin-system-component"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-medium capitalize text-white">
                    {component.name.replaceAll("_", " ")}
                  </h3>
                  <StatusBadge status={component.status} />
                </div>
                {component.message ? (
                  <p className="mt-2 text-sm text-slate-400">{component.message}</p>
                ) : null}
                {component.detail ? (
                  <p className="mt-1 text-xs text-slate-500">{component.detail}</p>
                ) : null}
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="h-40 animate-pulse rounded-2xl bg-slate-800/40" data-testid="admin-system-loading" />
      )}
    </div>
  );
}
