import Link from "next/link";

export function PublicFooter() {
  return (
    <footer className="border-t border-white/10 py-10">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-6 px-4 sm:px-8 md:flex-row md:items-center md:justify-between lg:px-10">
        <div>
          <p className="text-sm font-semibold text-white">Cortexa AI Knowledge Platform</p>
          <p className="mt-1 text-xs text-slate-500">Enterprise RAG · Knowledge Management · AI Quality Operations</p>
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <Link href="/demo" className="rounded-lg px-3 py-2 text-slate-400 transition hover:text-white">Product tour</Link>
          <Link href="/login" className="rounded-lg px-3 py-2 text-slate-400 transition hover:text-white">Sign in</Link>
          <a href="#architecture" className="rounded-lg px-3 py-2 text-slate-400 transition hover:text-white">Architecture</a>
        </div>
      </div>
    </footer>
  );
}
