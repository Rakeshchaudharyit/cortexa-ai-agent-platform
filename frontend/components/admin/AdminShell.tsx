"use client";

import { useState, type ReactNode } from "react";

import { AdminHeader } from "@/components/admin/AdminHeader";
import { AdminSidebar } from "@/components/admin/AdminSidebar";

export function AdminShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="cx-shell" data-testid="admin-shell">
      <div className="mx-auto flex min-h-screen max-w-[1680px]">
        <AdminSidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
        <div className="flex min-w-0 flex-1 flex-col">
          <AdminHeader onMenuClick={() => setMobileOpen(true)} />
          <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 overflow-x-hidden px-4 py-6 sm:px-6 lg:px-8 xl:px-10" data-testid="admin-main">
            <div className="mx-auto min-w-0 w-full max-w-[1380px]">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
