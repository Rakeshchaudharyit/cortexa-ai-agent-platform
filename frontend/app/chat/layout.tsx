"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { useAuth } from "@/components/AuthProvider";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.035] px-5 py-4">
          <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
          <p className="text-sm text-slate-400" data-testid="chat-layout-loading">Restoring secure session…</p>
        </div>
      </div>
    );
  }

  if (status === "unauthenticated") return null;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#050b13]" data-testid="chat-layout">
      <header className="flex min-h-16 shrink-0 items-center justify-between gap-2 border-b border-white/10 bg-slate-950/75 px-3 py-2 shadow-sm shadow-black/10 backdrop-blur-xl sm:px-6">
        <nav className="cx-scrollbar flex min-w-0 items-center gap-1 overflow-x-auto py-1">
          <Link href="/workspace" className="mr-3 flex items-center gap-2" data-testid="nav-home">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-400 text-[11px] font-black text-slate-950">C</span>
            <span className="hidden sm:block"><span className="block text-sm font-semibold leading-none text-white">Cortexa</span><span className="mt-1 block text-[10px] leading-none text-slate-500">Knowledge Chat</span></span>
          </Link>
          <Link href="/chat" className="rounded-xl border border-cyan-400/15 bg-cyan-400/[0.07] px-3 py-2 text-sm font-medium text-cyan-100" data-testid="nav-chat">Chat</Link>
          <Link href="/workspace#documents" className="hidden rounded-xl px-3 py-2 text-sm text-slate-400 transition hover:bg-white/[0.045] hover:text-white sm:inline-flex">Knowledge</Link>
          <Link href="/tools" className="hidden rounded-xl px-3 py-2 text-sm text-slate-400 transition hover:bg-white/[0.045] hover:text-white sm:inline-flex" data-testid="nav-tools">Tools</Link>
        </nav>
        <span className="hidden items-center gap-2 rounded-full border border-emerald-400/10 bg-emerald-500/[0.055] px-3 py-1.5 text-[11px] text-emerald-200 lg:inline-flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />Grounded enterprise assistant</span>
      </header>
      <div className="flex flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
