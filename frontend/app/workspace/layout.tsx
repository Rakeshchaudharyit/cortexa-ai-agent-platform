"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  if (status === "loading") {
    return (
      <main id="main-content" className="flex min-h-screen items-center justify-center bg-[#050b13] px-6">
        <div className="cx-panel flex items-center gap-3 px-5 py-4">
          <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
          <p className="text-sm text-slate-400">Restoring secure workspace…</p>
        </div>
      </main>
    );
  }

  if (status === "unauthenticated") return null;
  return children;
}
