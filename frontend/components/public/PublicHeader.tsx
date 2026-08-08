"use client";

import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

export function PublicHeader() {
  const { status } = useAuth();
  const signedIn = status === "authenticated";

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[#050b13]/82 backdrop-blur-xl">
      <div className="mx-auto flex min-h-16 w-full max-w-[1240px] items-center justify-between gap-4 px-4 sm:px-8 lg:px-10">
        <Link href="/" className="flex items-center gap-3" aria-label="Cortexa home">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400 text-xs font-black text-slate-950 shadow-lg shadow-cyan-950/30">C</span>
          <span>
            <span className="block text-sm font-semibold leading-none text-white">Cortexa</span>
            <span className="mt-1 block text-[10px] leading-none text-slate-500">AI Knowledge Platform</span>
          </span>
        </Link>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Public navigation">
          <a href="#capabilities" className="rounded-xl px-3 py-2 text-sm text-slate-400 transition hover:bg-white/[0.045] hover:text-white">Capabilities</a>
          <a href="#architecture" className="rounded-xl px-3 py-2 text-sm text-slate-400 transition hover:bg-white/[0.045] hover:text-white">Architecture</a>
          <a href="#quality" className="rounded-xl px-3 py-2 text-sm text-slate-400 transition hover:bg-white/[0.045] hover:text-white">AI Quality</a>
          <Link href="/demo" className="rounded-xl px-3 py-2 text-sm text-slate-400 transition hover:bg-white/[0.045] hover:text-white">Product tour</Link>
        </nav>
        <div className="flex items-center gap-2">
          {signedIn ? (
            <Link href="/workspace" className="cx-button-primary">Open workspace</Link>
          ) : (
            <>
              <Link href="/login" className="hidden sm:inline-flex cx-button-secondary">Sign in</Link>
              <Link href="/demo" className="cx-button-primary">View demo</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
