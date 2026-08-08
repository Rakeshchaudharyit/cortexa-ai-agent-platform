"use client";

import Link from "next/link";

import { AdminBreadcrumbs } from "@/components/admin/AdminBreadcrumbs";

export function AdminHeader({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header
      className="sticky top-0 z-20 flex min-h-14 items-center justify-between gap-3 border-b border-white/10 bg-[#07111c]/85 px-4 backdrop-blur-xl sm:px-6"
      data-testid="admin-header"
    >
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 lg:hidden"
          onClick={onMenuClick}
          data-testid="admin-mobile-menu"
          aria-label="Open navigation"
        >
          Menu
        </button>
        <AdminBreadcrumbs />
      </div>
      <Link href="/chat" className="hidden rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:bg-white/[0.045] hover:text-white sm:inline-flex">
        Open assistant
      </Link>
    </header>
  );
}
