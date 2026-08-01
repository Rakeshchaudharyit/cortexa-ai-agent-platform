"use client";

import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div
      className="mb-4 flex flex-wrap items-end gap-3 rounded-2xl border border-white/8 bg-slate-900/40 p-3"
      data-testid="admin-filter-bar"
    >
      {children}
    </div>
  );
}

export function FilterInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none ring-cyan-400/0 focus:ring-2 ${props.className || ""}`}
    />
  );
}

export function FilterSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-cyan-400/40 ${props.className || ""}`}
    />
  );
}
