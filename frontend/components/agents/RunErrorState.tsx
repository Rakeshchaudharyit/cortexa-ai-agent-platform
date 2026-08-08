export function RunErrorState({ notFound = false, message }: { notFound?: boolean; message?: string }) {
  return <div className="rounded-2xl border border-rose-400/20 bg-rose-500/[0.06] p-8 text-center" role="alert" data-testid="agent-run-error"><h2 className="text-lg font-semibold text-slate-100">{notFound ? "Agent run not found" : "Unable to load agent activity"}</h2><p className="mt-2 text-sm text-slate-400">{notFound ? "This run does not exist or is not available to your account." : message || "Please try again."}</p></div>;
}
