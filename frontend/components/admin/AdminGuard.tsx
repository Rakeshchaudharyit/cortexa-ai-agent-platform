"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/components/AuthProvider";

export function AdminGuard({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login?next=/admin");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300" data-testid="admin-auth-loading">
        Restoring admin session…
      </div>
    );
  }

  if (status === "unauthenticated") {
    return null;
  }

  if (user?.role !== "admin") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-950 px-6 text-center" data-testid="admin-access-denied">
        <h1 className="text-2xl font-semibold text-white">Access denied</h1>
        <p className="max-w-md text-sm text-slate-400">
          This area is restricted to platform administrators. Your account does not have the admin role.
        </p>
        <button
          type="button"
          className="rounded-lg bg-cyan-500/20 px-4 py-2 text-sm text-cyan-100 ring-1 ring-cyan-400/30"
          onClick={() => router.replace("/chat")}
          data-testid="admin-denied-back"
        >
          Back to app
        </button>
      </div>
    );
  }

  return <>{children}</>;
}
