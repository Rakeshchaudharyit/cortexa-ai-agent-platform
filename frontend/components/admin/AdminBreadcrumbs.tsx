"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LABELS: Record<string, string> = {
  admin: "Admin",
  users: "Users",
  documents: "Documents",
  conversations: "Conversations",
  memories: "Memories",
  tools: "Agent Tools",
  "tool-executions": "Tool Executions",
  analytics: "Analytics",
  audit: "Audit Logs",
  system: "System Health",
  settings: "Settings",
};

export function AdminBreadcrumbs() {
  const pathname = usePathname() || "/admin";
  const parts = pathname.split("/").filter(Boolean);
  let href = "";
  return (
    <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm" data-testid="admin-breadcrumbs">
      {parts.map((part, index) => {
        href += `/${part}`;
        const last = index === parts.length - 1;
        const label = LABELS[part] || part;
        return (
          <span key={href} className="flex items-center gap-2">
            {index > 0 ? <span className="text-slate-600">/</span> : null}
            {last ? (
              <span className="font-medium text-slate-100">{label}</span>
            ) : (
              <Link href={href} className="text-slate-400 hover:text-cyan-200">
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
