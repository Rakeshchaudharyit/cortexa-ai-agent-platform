"use client";

import { AdminBreadcrumbs } from "@/components/admin/AdminBreadcrumbs";

export function AdminHeader({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header
      className="sticky top-0 z-20 flex items-center gap-3 border-b border-white/5 bg-slate-950/50 px-4 py-3 backdrop-blur-md sm:px-6"
      data-testid="admin-header"
    >
      <button
        type="button"
        className="rounded-lg bg-slate-800/80 px-3 py-2 text-sm text-slate-100 ring-1 ring-white/10 lg:hidden"
        onClick={onMenuClick}
        data-testid="admin-mobile-menu"
        aria-label="Open navigation"
      >
        Menu
      </button>
      <AdminBreadcrumbs />
    </header>
  );
}
