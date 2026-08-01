"use client";

import type { ReactNode } from "react";

import { EmptyState } from "@/components/admin/EmptyState";

export type DataColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
};

export function DataTable<T extends { id?: string }>({
  columns,
  rows,
  loading,
  emptyTitle = "No results",
  emptyDescription,
  onRowClick,
}: {
  columns: DataColumn<T>[];
  rows: T[];
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onRowClick?: (row: T) => void;
}) {
  if (loading) {
    return (
      <div className="space-y-2" data-testid="admin-table-loading">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-12 animate-pulse rounded-xl bg-slate-800/50" />
        ))}
      </div>
    );
  }
  if (!rows.length) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <>
      <div className="hidden overflow-hidden rounded-2xl border border-white/8 md:block" data-testid="admin-data-table">
        <table className="min-w-full divide-y divide-white/5 text-left text-sm">
          <thead className="bg-slate-950/60 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              {columns.map((col) => (
                <th key={col.key} className={`px-4 py-3 font-medium ${col.className || ""}`}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 bg-slate-900/30">
            {rows.map((row, index) => (
              <tr
                key={row.id || String(index)}
                className={onRowClick ? "cursor-pointer hover:bg-cyan-500/5" : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key} className={`px-4 py-3 text-slate-200 ${col.className || ""}`}>
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-3 md:hidden" data-testid="admin-data-cards">
        {rows.map((row, index) => (
          <button
            type="button"
            key={row.id || String(index)}
            className="w-full rounded-2xl border border-white/8 bg-slate-900/50 p-4 text-left"
            onClick={onRowClick ? () => onRowClick(row) : undefined}
          >
            {columns.slice(0, 4).map((col) => (
              <div key={col.key} className="mb-2 last:mb-0">
                <p className="text-[10px] uppercase tracking-wide text-slate-500">{col.header}</p>
                <div className="text-sm text-slate-100">{col.render(row)}</div>
              </div>
            ))}
          </button>
        ))}
      </div>
    </>
  );
}
