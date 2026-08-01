"use client";

import type { ReactNode } from "react";

export function DangerZone({
  title = "Danger zone",
  description,
  children,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section
      className="rounded-2xl border border-rose-500/30 bg-rose-950/20 p-4 sm:p-5"
      data-testid="admin-danger-zone"
    >
      <h3 className="text-sm font-semibold text-rose-100">{title}</h3>
      {description ? <p className="mt-1 text-sm text-rose-100/70">{description}</p> : null}
      <div className="mt-4 space-y-3">{children}</div>
    </section>
  );
}
