"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function AgentRunsLayout({ children: _children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace("/chat?notice=agent-runs-disabled");
    if (status === "unauthenticated") router.replace("/login");
  }, [router, status]);

  return (
    <div className="flex min-h-screen items-center justify-center px-6 text-center">
      <div>
        <p className="text-sm font-medium text-slate-200">Agent Runs are temporarily disabled.</p>
        <p className="mt-2 text-sm text-slate-500">Redirecting to the stable Chat and RAG experience…</p>
      </div>
    </div>
  );
}
