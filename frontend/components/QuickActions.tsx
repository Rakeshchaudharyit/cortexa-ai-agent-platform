"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";

const ACTIONS = [
  {
    href: "/chat",
    label: "Open Chat",
    description: "Multi-turn assistant with streaming",
    testId: "quick-action-chat",
    requiresAuth: true,
  },
  {
    href: "/#documents",
    label: "Manage Documents",
    description: "Upload and review private files",
    testId: "quick-action-documents",
    requiresAuth: true,
  },
  {
    href: "/tools",
    label: "View Tool History",
    description: "Auditable agent tool executions",
    testId: "quick-action-tools",
    requiresAuth: true,
  },
  {
    href: "/memories",
    label: "Manage Memories",
    description: "Review and control long-term memory",
    testId: "quick-action-memories",
    requiresAuth: true,
  },
  {
    href: "/#system-status",
    label: "System Status",
    description: "API, database, Redis, and LLM health",
    testId: "quick-action-status",
    requiresAuth: false,
  },
] as const;

export function QuickActions() {
  const { status } = useAuth();
  const authenticated = status === "authenticated";

  return (
    <section className="flex flex-col gap-4" data-testid="quick-actions">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">Quick actions</h2>
        <p className="mt-1 text-sm text-slate-400">Jump to the main product surfaces.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {ACTIONS.map((action) => {
          const locked = action.requiresAuth && !authenticated;
          if (locked) {
            return (
              <Link
                key={action.href}
                href="/login"
                className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 transition hover:border-cyan-400/30 hover:bg-cyan-500/5"
                data-testid={action.testId}
              >
                <p className="text-sm font-medium text-slate-100">{action.label}</p>
                <p className="mt-1 text-xs text-slate-500">Sign in required · {action.description}</p>
              </Link>
            );
          }
          return (
            <Link
              key={action.href}
              href={action.href}
              className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 transition hover:border-cyan-400/30 hover:bg-cyan-500/5"
              data-testid={action.testId}
            >
              <p className="text-sm font-medium text-cyan-100">{action.label}</p>
              <p className="mt-1 text-xs text-slate-500">{action.description}</p>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
