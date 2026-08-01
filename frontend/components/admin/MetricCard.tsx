export function MetricCard({
  label,
  value,
  unit,
  unavailable,
  hint,
}: {
  label: string;
  value: number | null | undefined;
  unit?: string | null;
  unavailable?: boolean;
  hint?: string | null;
}) {
  return (
    <div
      className="rounded-2xl border border-white/8 bg-slate-900/55 p-4 shadow-[0_0_0_1px_rgba(34,211,238,0.04)] backdrop-blur"
      data-testid="admin-metric-card"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">
        {unavailable || value === null || value === undefined ? (
          <span className="text-slate-500">N/A</span>
        ) : (
          <>
            {typeof value === "number" ? value.toLocaleString() : value}
            {unit ? <span className="ml-1 text-sm font-normal text-slate-400">{unit}</span> : null}
          </>
        )}
      </p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
