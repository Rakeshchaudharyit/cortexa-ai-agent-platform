"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

const NAV = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/documents", label: "Documents" },
  { href: "/admin/conversations", label: "Conversations" },
  { href: "/admin/memories", label: "Memories" },
  { href: "/admin/tools", label: "Agent Tools" },
  { href: "/admin/tool-executions", label: "Tool Executions" },
  { href: "/admin/analytics", label: "Analytics" },
  { href: "/admin/audit", label: "Audit Logs" },
  { href: "/admin/system", label: "System Health" },
  { href: "/admin/settings", label: "Settings" },
];

function navActive(pathname: string | null, href: string, exact?: boolean) {
  if (!pathname) return false;
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AdminSidebar({
  mobileOpen,
  onClose,
}: {
  mobileOpen: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const router = useRouter();

  const panel = (
    <aside
      className="flex h-full w-64 flex-col border-r border-cyan-500/15 bg-slate-950/70 backdrop-blur-md"
      data-testid="admin-sidebar"
    >
      <div className="border-b border-white/5 px-5 py-5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300/80">Cortexa</p>
        <h1 className="mt-1 text-lg font-semibold text-white">Admin Portal</h1>
        <Link
          href="/chat"
          className="mt-3 inline-flex text-sm text-slate-300 underline-offset-2 hover:text-cyan-200 hover:underline"
          data-testid="admin-back-to-app"
        >
          ← Back to App
        </Link>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Admin">
        {NAV.map((item) => {
          const active = navActive(pathname, item.href, item.exact);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`block rounded-lg px-3 py-2 text-sm transition ${
                active
                  ? "bg-cyan-500/20 text-cyan-100 ring-1 ring-cyan-400/30"
                  : "text-slate-300 hover:bg-white/5 hover:text-white"
              }`}
              data-testid={`admin-nav-${item.href.replace("/admin", "admin").replace(/\//g, "-") || "admin"}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-white/5 px-4 py-4" data-testid="admin-user-card">
        <p className="truncate text-sm font-medium text-white">{user?.full_name}</p>
        <p className="truncate text-xs text-slate-400">{user?.email}</p>
        <p className="mt-1 text-xs uppercase tracking-wide text-cyan-300/80">{user?.role}</p>
        <button
          type="button"
          className="mt-3 w-full rounded-lg bg-slate-800/80 px-3 py-2 text-sm text-slate-100 ring-1 ring-white/10 hover:bg-slate-700"
          onClick={() => {
            void (async () => {
              await logout();
              router.replace("/admin/login");
            })();
          }}
          data-testid="admin-logout"
        >
          Log out
        </button>
      </div>
    </aside>
  );

  return (
    <>
      <div className="hidden lg:sticky lg:top-0 lg:flex lg:h-screen lg:shrink-0">{panel}</div>
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" data-testid="admin-mobile-drawer">
          <button
            type="button"
            className="absolute inset-0 bg-black/60"
            aria-label="Close navigation"
            onClick={onClose}
          />
          <div className="absolute inset-y-0 left-0 shadow-2xl">{panel}</div>
        </div>
      ) : null}
    </>
  );
}
