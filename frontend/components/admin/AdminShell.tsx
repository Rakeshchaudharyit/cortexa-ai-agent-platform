"use client";

import { useState, type ReactNode } from "react";

import { AdminHeader } from "@/components/admin/AdminHeader";
import { AdminSidebar } from "@/components/admin/AdminSidebar";

export function AdminShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[radial-gradient(1200px_600px_at_0%_-10%,rgba(34,211,238,0.12),transparent_50%),linear-gradient(160deg,#06101c,#0a1628_45%,#071018)] text-slate-100" data-testid="admin-shell">
      <div className="mx-auto flex min-h-screen max-w-[1600px]">
        <AdminSidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
        <div className="flex min-w-0 flex-1 flex-col">
          <AdminHeader onMenuClick={() => setMobileOpen(true)} />
          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8" data-testid="admin-main">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
