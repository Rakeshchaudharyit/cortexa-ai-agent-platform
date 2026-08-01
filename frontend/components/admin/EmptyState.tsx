export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-slate-900/40 px-6 py-16 text-center"
      data-testid="admin-empty-state"
    >
      <div className="mb-4 h-12 w-12 rounded-full bg-cyan-500/10 ring-1 ring-cyan-400/20" />
      <h3 className="text-lg font-medium text-white">{title}</h3>
      {description ? <p className="mt-2 max-w-md text-sm text-slate-400">{description}</p> : null}
    </div>
  );
}
