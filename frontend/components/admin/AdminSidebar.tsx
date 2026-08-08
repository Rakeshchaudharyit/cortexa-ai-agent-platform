"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

type NavItem = { href: string; label: string; exact?: boolean };
type NavGroup = { label: string; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { href: "/admin", label: "Overview", exact: true },
      { href: "/admin/analytics", label: "AI Quality & Analytics" },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { href: "/admin/documents", label: "Documents" },
      { href: "/admin/conversations", label: "Conversations" },
      { href: "/admin/memories", label: "Memory" },
    ],
  },
  {
    label: "AI Quality",
    items: [
      { href: "/admin/evaluations", label: "Evaluations" },
      { href: "/admin/feedback", label: "Feedback Review" },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/admin/jobs", label: "Background Jobs" },
      { href: "/admin/tools", label: "Tools" },
      { href: "/admin/tool-executions", label: "Tool Activity" },
      { href: "/admin/audit", label: "Audit Logs" },
      { href: "/admin/system", label: "System Health" },
    ],
  },
  {
    label: "Administration",
    items: [
      { href: "/admin/users", label: "Users" },
      { href: "/admin/settings", label: "Settings" },
    ],
  },
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
      className="flex h-full w-72 flex-col border-r border-white/10 bg-[#050b13]/95 backdrop-blur-xl"
      data-testid="admin-sidebar"
    >
      <div className="border-b border-white/10 px-5 py-5">
        <Link href="/workspace" className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-cyan-400 text-sm font-black text-slate-950 shadow-lg shadow-cyan-950/30">C</span>
          <div>
            <p className="text-sm font-semibold text-white">Cortexa</p>
            <p className="text-xs text-slate-500">AI Operations Console</p>
          </div>
        </Link>
        <Link
          href="/chat"
          className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-slate-400 transition hover:text-cyan-200"
          data-testid="admin-back-to-app"
        >
          ← Return to workspace
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Admin">
        <div className="space-y-5">
          {NAV_GROUPS.map((group) => (
            <section key={group.label}>
              <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">{group.label}</p>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const active = navActive(pathname, item.href, item.exact);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={onClose}
                      className={`block rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                        active
                          ? "bg-cyan-400/10 text-cyan-100 ring-1 ring-cyan-400/20"
                          : "text-slate-400 hover:bg-white/[0.045] hover:text-slate-100"
                      }`}
                      data-testid={`admin-nav-${item.href.replace("/admin", "admin").replace(/\//g, "-") || "admin"}`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </nav>

      <div className="border-t border-white/10 p-4" data-testid="admin-user-card">
        <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-xs font-semibold text-slate-200 ring-1 ring-white/10">
              {user?.full_name?.slice(0, 1).toUpperCase() || "A"}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">{user?.full_name}</p>
              <p className="truncate text-xs text-slate-500">{user?.email}</p>
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="rounded-full bg-cyan-400/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-cyan-200">{user?.role}</span>
            <button
              type="button"
              className="text-xs font-medium text-slate-500 transition hover:text-white"
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
        </div>
      </div>
    </aside>
  );

  return (
    <>
      <div className="hidden lg:sticky lg:top-0 lg:flex lg:h-screen lg:shrink-0">{panel}</div>
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" data-testid="admin-mobile-drawer" role="dialog" aria-modal="true" aria-label="Admin navigation">
          <button type="button" className="absolute inset-0 bg-black/70 backdrop-blur-sm" aria-label="Close navigation" onClick={onClose} />
          <div className="absolute inset-y-0 left-0 w-[min(18rem,88vw)] shadow-2xl">{panel}</div>
        </div>
      ) : null}
    </>
  );
}
