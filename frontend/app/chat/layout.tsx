"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { status } = useAuth();

  // Redirect unauthenticated users.
  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-400" data-testid="chat-layout-loading">
          Restoring session…
        </p>
      </div>
    );
  }

  if (status === "unauthenticated") {
    return null;
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden" data-testid="chat-layout">
      {/* Top nav bar */}
      <header className="flex shrink-0 items-center justify-between border-b border-white/10 bg-black/30 px-4 py-2 backdrop-blur-sm">
        <nav className="flex items-center gap-4">
          <Link
            href="/"
            className="text-sm font-semibold text-cyan-300/90 hover:text-cyan-200 transition"
            data-testid="nav-home"
          >
            Cortexa
          </Link>
          <Link
            href="/chat"
            className="text-sm text-slate-300 hover:text-slate-100 transition"
            data-testid="nav-chat"
          >
            Chat
          </Link>
          <Link
            href="/tools"
            className="text-sm text-slate-300 hover:text-slate-100 transition"
            data-testid="nav-tools"
          >
            Tools
          </Link>
        </nav>
      </header>

      {/* Sidebar + panel */}
      <div className="flex flex-1 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
