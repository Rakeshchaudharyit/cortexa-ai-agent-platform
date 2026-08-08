"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";

const ACTIONS = [
  {
    href: "/chat",
    label: "Ask your knowledge",
    description: "Grounded answers with source citations",
    marker: "AI",
    testId: "quick-action-chat",
    requiresAuth: true,
  },
  {
    href: "/#documents",
    label: "Manage knowledge",
    description: "Upload, version, archive, and re-index",
    marker: "KB",
    testId: "quick-action-documents",
    requiresAuth: true,
  },
  {
    href: "/memories",
    label: "Review memory",
    description: "Control retained user context",
    marker: "M",
    testId: "quick-action-memories",
    requiresAuth: true,
  },
  {
    href: "/#system-status",
    label: "Platform health",
    description: "API, data, queue, and model readiness",
    marker: "OP",
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
        <p className="cx-eyebrow">Workspace</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight text-white">Start with a core workflow</h2>
        <p className="mt-1 text-sm text-slate-400">Move from knowledge ingestion to grounded answers and operations.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {ACTIONS.map((action) => {
          const locked = action.requiresAuth && !authenticated;
          return (
            <Link
              key={action.href}
              href={locked ? "/login" : action.href}
              className="group rounded-2xl border border-white/10 bg-white/[0.035] p-4 transition duration-200 hover:-translate-y-0.5 hover:border-cyan-400/25 hover:bg-cyan-400/[0.045]"
              data-testid={action.testId}
            >
              <div className="mb-5 flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400/10 text-[11px] font-bold tracking-wide text-cyan-200 ring-1 ring-cyan-400/20">
                {action.marker}
              </div>
              <p className="text-sm font-semibold text-slate-100 transition group-hover:text-cyan-100">{action.label}</p>
              <p className="mt-1.5 text-xs leading-5 text-slate-500">
                {locked ? "Sign in required · " : ""}{action.description}
              </p>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
