"use client";

import { useEffect, useMemo, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { MetricCard } from "@/components/admin/MetricCard";
import {
  createEvaluationCase,
  deleteEvaluationCase,
  downloadEvaluationExport,
  fetchAdminJobs,
  fetchAdminUsers,
  fetchEvaluationCases,
  fetchEvaluationRuns,
  queueEvaluationExport,
  runRagEvaluation,
} from "@/services/admin";
import type { AdminUserSummary, RagEvaluationCase, RagEvaluationRun } from "@/types/admin";

function runStatusClass(status: string) {
  if (status === "completed") return "border-emerald-400/20 bg-emerald-500/10 text-emerald-200";
  if (status === "failed") return "border-rose-400/20 bg-rose-500/10 text-rose-200";
  if (status === "cancelled") return "border-slate-400/20 bg-slate-500/10 text-slate-300";
  return "border-cyan-400/20 bg-cyan-500/10 text-cyan-200";
}

export default function RagEvaluationsPage() {
  const [cases, setCases] = useState<RagEvaluationCase[]>([]);
  const [runs, setRuns] = useState<RagEvaluationRun[]>([]);
  const [owners, setOwners] = useState<AdminUserSummary[]>([]);
  const [ownerSearch, setOwnerSearch] = useState("");
  const [loadingOwners, setLoadingOwners] = useState(true);
  const [runningEvaluation, setRunningEvaluation] = useState(false);
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [exportReady, setExportReady] = useState(false);
  const [savingCase, setSavingCase] = useState(false);
  const [deletingCaseId, setDeletingCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [form, setForm] = useState({
    owner_user_id: "",
    name: "",
    question: "",
    expected_keywords: "",
    should_answer: true,
  });

  async function reload() {
    const [caseResult, runResult] = await Promise.all([
      fetchEvaluationCases(),
      fetchEvaluationRuns(),
    ]);
    if (caseResult.ok) setCases(caseResult.data.items);
    if (runResult.ok) setRuns(runResult.data.items);
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [caseResult, runResult, ownerResult, exportResult] = await Promise.all([
        fetchEvaluationCases(),
        fetchEvaluationRuns(),
        fetchAdminUsers({ status: "active", limit: 100 }),
        fetchAdminJobs(undefined, "evaluation.export"),
      ]);
      if (cancelled) return;
      if (caseResult.ok) setCases(caseResult.data.items);
      if (runResult.ok) {
        setRuns(runResult.data.items);
        const latestCompleted = runResult.data.items.find((run) => run.status === "completed");
        if (latestCompleted && exportResult.ok) {
          const existingExport = exportResult.data.items.find(
            (job) => job.resource_id === latestCompleted.id && job.status === "succeeded",
          );
          if (existingExport) {
            setExportJobId(existingExport.id);
            setExportReady(true);
          }
        }
      }
      if (ownerResult.ok) {
        const sortedOwners = [...ownerResult.data.items].sort((left, right) => {
          if (left.documents_count !== right.documents_count) return right.documents_count - left.documents_count;
          return left.full_name.localeCompare(right.full_name);
        });
        setOwners(sortedOwners);
        setForm((current) => ({
          ...current,
          owner_user_id:
            current.owner_user_id ||
            sortedOwners.find((owner) => owner.documents_count > 0)?.id ||
            sortedOwners[0]?.id ||
            "",
        }));
      } else {
        setError(ownerResult.error.message);
      }
      setLoadingOwners(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const hasActiveRun = runs.some((run) => run.status === "queued" || run.status === "running");
    if (!hasActiveRun && !exportJobId) return;
    const timer = window.setInterval(() => {
      void (async () => {
        if (hasActiveRun) await reload();
        if (exportJobId) {
          const jobs = await fetchAdminJobs(undefined, "evaluation.export");
          if (jobs.ok) {
            const job = jobs.data.items.find((item) => item.id === exportJobId);
            if (job?.status === "succeeded") setExportReady(true);
            if (job?.status === "failed") setError(job.error_message ?? "Evaluation export failed");
          }
        }
      })();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [runs, exportJobId]);

  const latest = runs[0];
  const latestCompleted = runs.find((run) => run.status === "completed");
  const activeEvaluation = runs.some((run) => run.status === "queued" || run.status === "running");
  const enabledCases = cases.filter((item) => item.enabled).length;
  const latestPassRate = latestCompleted && latestCompleted.total_cases > 0
    ? Math.round((latestCompleted.passed_cases / latestCompleted.total_cases) * 100)
    : null;
  const normalizedOwnerSearch = ownerSearch.trim().toLocaleLowerCase();
  const selectedOwner = owners.find((owner) => owner.id === form.owner_user_id);
  const visibleOwners = owners.filter((owner) =>
    owner.id === selectedOwner?.id ||
    !normalizedOwnerSearch ||
    `${owner.full_name} ${owner.email}`.toLocaleLowerCase().includes(normalizedOwnerSearch),
  );
  const canSave = Boolean(form.owner_user_id) && form.name.trim().length >= 2 && form.question.trim().length >= 3;
  const recentRuns = useMemo(() => runs.slice(0, 8), [runs]);

  return (
    <div className="min-w-0 max-w-full overflow-x-hidden" data-testid="admin-rag-evaluations-page">
      <AdminPageHeader
        title="RAG Evaluations"
        description="Run repeatable quality checks against your private knowledge base to catch regressions in grounding, citations, and safe no-answer behavior."
        actions={
          <button
            type="button"
            disabled={runningEvaluation || activeEvaluation || enabledCases === 0}
            className="cx-button-primary"
            onClick={() => {
              void (async () => {
                setRunningEvaluation(true);
                setError(null);
                setSuccess(null);
                const result = await runRagEvaluation();
                if (!result.ok) {
                  setError(result.error.message);
                } else {
                  setSuccess("Evaluation queued. Quality checks are running in the background.");
                  setRuns((current) => [result.data, ...current.filter((item) => item.id !== result.data.id)]);
                }
                await reload();
                setRunningEvaluation(false);
              })();
            }}
          >
            {runningEvaluation ? "Queueing…" : activeEvaluation ? "Evaluation running…" : "Run evaluation"}
          </button>
        }
      />

      <section className="mb-6 overflow-hidden rounded-3xl border border-cyan-400/15 bg-gradient-to-br from-cyan-500/10 via-slate-950/70 to-blue-500/5 p-6 shadow-[0_22px_70px_rgba(0,0,0,0.22)]">
        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,.65fr)] lg:items-end">
          <div className="min-w-0">
            <p className="cx-eyebrow">AI quality regression testing</p>
            <h3 className="mt-3 max-w-3xl text-2xl font-semibold tracking-tight text-white sm:text-3xl">
              Measure RAG quality before model, prompt, or retrieval changes reach users.
            </h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
              Each case defines an expected behavior for a user-owned knowledge collection. Runs execute asynchronously and preserve score history for comparison over time.
            </p>
          </div>
          <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Latest pass rate</p>
              <p className="mt-2 text-3xl font-semibold text-white">{latestPassRate === null ? "—" : `${latestPassRate}%`}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/45 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Latest score</p>
              <p className="mt-2 text-3xl font-semibold text-white">{latestCompleted ? `${Math.round(latestCompleted.average_score * 100)}%` : "—"}</p>
            </div>
          </div>
        </div>
      </section>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Evaluation cases" value={cases.length} hint="Reusable regression scenarios" />
        <MetricCard label="Enabled cases" value={enabledCases} hint="Included in the next run" />
        <MetricCard label="Passed last run" value={latestCompleted?.passed_cases ?? null} hint={latestCompleted ? `${latestCompleted.total_cases} cases evaluated` : "No completed run yet"} />
        <MetricCard label="Average quality" value={latestCompleted ? Math.round(latestCompleted.average_score * 100) : null} unit="%" hint="Composite groundedness and citation score" />
      </div>

      {success ? (
        <div className="mb-5 rounded-2xl border border-emerald-400/15 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100" role="status" aria-live="polite" data-testid="evaluation-success-message">
          {success}
        </div>
      ) : null}
      {error ? <div className="mb-5 rounded-2xl border border-rose-400/15 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">{error}</div> : null}

      <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,390px)_minmax(0,1fr)]">
        <section className="cx-panel min-w-0 max-w-full p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="cx-eyebrow">Test definition</p>
              <h2 className="mt-2 text-lg font-semibold text-white">Create evaluation case</h2>
              <p className="mt-1 text-sm leading-5 text-slate-400">Define what the knowledge base should—or should not—be able to answer.</p>
            </div>
            <span className="rounded-full border border-cyan-400/15 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-medium text-cyan-200">Private KB</span>
          </div>

          <div className="mt-5 space-y-4">
            <label className="block space-y-2 text-sm text-slate-300">
              <span className="font-medium text-slate-200">Knowledge owner</span>
              <input className="cx-input" placeholder="Search by name or email" value={ownerSearch} onChange={(event) => setOwnerSearch(event.target.value)} data-testid="evaluation-owner-search" />
              <select className="cx-input" value={form.owner_user_id} disabled={loadingOwners || owners.length === 0} onChange={(event) => setForm({ ...form, owner_user_id: event.target.value })} data-testid="evaluation-owner-select">
                <option value="">{loadingOwners ? "Loading users…" : owners.length === 0 ? "No active users found" : "Select a user"}</option>
                {visibleOwners.map((owner) => (
                  <option key={owner.id} value={owner.id}>
                    {owner.full_name} · {owner.email} · {owner.documents_count} document{owner.documents_count === 1 ? "" : "s"}
                  </option>
                ))}
              </select>
              {selectedOwner ? (
                <span className="block rounded-xl border border-white/8 bg-white/[0.035] px-3 py-2 text-xs leading-5 text-slate-400" data-testid="evaluation-owner-summary">
                  Evaluating {selectedOwner.documents_count} document{selectedOwner.documents_count === 1 ? "" : "s"} owned by <span className="text-slate-200">{selectedOwner.email}</span>.
                </span>
              ) : null}
            </label>

            <label className="block space-y-2 text-sm">
              <span className="font-medium text-slate-200">Case name</span>
              <input className="cx-input" placeholder="Case name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </label>

            <label className="block space-y-2 text-sm">
              <span className="font-medium text-slate-200">Test question</span>
              <textarea className="cx-input min-h-28 resize-y" placeholder="Question" value={form.question} onChange={(event) => setForm({ ...form, question: event.target.value })} />
            </label>

            <label className="block space-y-2 text-sm">
              <span className="font-medium text-slate-200">Expected keywords</span>
              <input className="cx-input" placeholder="Expected keywords, comma separated" value={form.expected_keywords} onChange={(event) => setForm({ ...form, expected_keywords: event.target.value })} />
              <span className="text-xs text-slate-500">Optional signals used for deterministic regression scoring.</span>
            </label>

            <label className="flex items-start gap-3 rounded-xl border border-white/8 bg-white/[0.025] p-3 text-sm text-slate-300">
              <input className="mt-0.5 size-4 accent-cyan-400" type="checkbox" checked={form.should_answer} onChange={(event) => setForm({ ...form, should_answer: event.target.checked })} />
              <span>
                <span className="block font-medium text-slate-200">The documents should contain an answer</span>
                <span className="mt-1 block text-xs leading-5 text-slate-500">Turn this off to test safe no-answer behavior and hallucination resistance.</span>
              </span>
            </label>

            <button type="button" className="cx-button-secondary w-full" disabled={!canSave || savingCase} data-testid="evaluation-save-case" onClick={() => {
              void (async () => {
                if (!canSave) return;
                setSavingCase(true);
                setError(null);
                setSuccess(null);
                const result = await createEvaluationCase({
                  owner_user_id: form.owner_user_id,
                  name: form.name,
                  question: form.question,
                  expected_keywords: form.expected_keywords.split(",").map((value) => value.trim()).filter(Boolean),
                  should_answer: form.should_answer,
                  enabled: true,
                });
                if (!result.ok) {
                  setError(result.error.message);
                  setSavingCase(false);
                  return;
                }
                setCases((current) => [result.data, ...current.filter((item) => item.id !== result.data.id)]);
                setSuccess(`Evaluation case “${result.data.name}” was created successfully.`);
                setForm((current) => ({ owner_user_id: current.owner_user_id, name: "", question: "", expected_keywords: "", should_answer: true }));
                setSavingCase(false);
                void reload();
              })();
            }}>
              {savingCase ? "Saving case…" : "Save evaluation case"}
            </button>
          </div>
        </section>

        <section className="min-w-0 max-w-full space-y-6">
          <div className="cx-panel min-w-0 max-w-full p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="cx-eyebrow">Regression suite</p>
                <h2 className="mt-2 text-lg font-semibold text-white">Evaluation cases</h2>
              </div>
              <span className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-1 text-xs text-slate-400">{enabledCases} enabled</span>
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-2">
              {cases.length === 0 ? (
                <div className="col-span-full rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-6 py-10 text-center">
                  <p className="text-sm font-medium text-slate-200">No evaluation cases yet</p>
                  <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">Add a grounded-answer case and a safe no-answer case to create a useful regression baseline.</p>
                </div>
              ) : cases.map((item) => (
                <article key={item.id} className="min-w-0 max-w-full rounded-2xl border border-white/8 bg-slate-950/45 p-4 transition hover:border-cyan-400/15">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate font-medium text-white">{item.name}</h3>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${item.enabled ? "border-emerald-400/20 bg-emerald-500/10 text-emerald-200" : "border-white/10 bg-white/[0.03] text-slate-500"}`}>{item.enabled ? "Enabled" : "Disabled"}</span>
                      </div>
                    </div>
                    <button type="button" className="cx-button-danger min-h-8 px-2.5 py-1 text-xs" disabled={deletingCaseId === item.id} data-testid={`evaluation-delete-${item.id}`} onClick={() => {
                      if (!window.confirm(`Delete evaluation case “${item.name}”? This cannot be undone.`)) return;
                      void (async () => {
                        setDeletingCaseId(item.id);
                        setError(null);
                        setSuccess(null);
                        const result = await deleteEvaluationCase(item.id);
                        if (!result.ok) {
                          setError(result.error.message);
                          setDeletingCaseId(null);
                          return;
                        }
                        setCases((current) => current.filter((candidate) => candidate.id !== item.id));
                        setSuccess(`Evaluation case “${item.name}” was deleted successfully.`);
                        setDeletingCaseId(null);
                      })();
                    }}>
                      {deletingCaseId === item.id ? "Deleting…" : "Delete"}
                    </button>
                  </div>
                  <p className="mt-3 line-clamp-3 break-words text-sm leading-6 text-slate-300">{item.question}</p>
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pt-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs ${item.should_answer ? "bg-cyan-500/10 text-cyan-200" : "bg-violet-500/10 text-violet-200"}`}>{item.should_answer ? "Grounded answer expected" : "Safe no-answer expected"}</span>
                    {item.expected_keywords.length ? <span className="text-xs text-slate-500">{item.expected_keywords.length} keyword signal{item.expected_keywords.length === 1 ? "" : "s"}</span> : null}
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="cx-panel min-w-0 max-w-full p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="cx-eyebrow">Quality history</p>
                <h2 className="mt-2 text-lg font-semibold text-white">Evaluation runs</h2>
              </div>
              {latestCompleted ? (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="cx-button-secondary" onClick={() => {
                    void (async () => {
                      setError(null);
                      setSuccess(null);
                      const result = await queueEvaluationExport(latestCompleted.id);
                      if (!result.ok) { setError(result.error.message); return; }
                      setExportJobId(result.data.job_id);
                      setExportReady(false);
                      setSuccess("CSV export queued in the background.");
                    })();
                  }}>Export latest CSV</button>
                  {exportJobId && exportReady ? (
                    <button type="button" className="cx-button-primary" onClick={() => {
                      void (async () => {
                        const result = await downloadEvaluationExport(exportJobId);
                        if (!result.ok) setError(result.error);
                      })();
                    }}>Download CSV</button>
                  ) : exportJobId ? <span className="self-center text-sm text-slate-400">Preparing export…</span> : null}
                </div>
              ) : null}
            </div>

            <div className="mt-5 max-w-full overflow-x-auto cx-scrollbar overscroll-x-contain rounded-2xl border border-white/8">
              <table className="min-w-[760px] w-full text-left text-sm">
                <thead className="bg-white/[0.035] text-[11px] uppercase tracking-[0.14em] text-slate-500">
                  <tr><th className="px-4 py-3">Created</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Pass rate</th><th className="px-4 py-3">Quality</th><th className="px-4 py-3">Duration</th></tr>
                </thead>
                <tbody>
                  {recentRuns.length === 0 ? (
                    <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500">No evaluation runs yet. Run the suite to establish a baseline.</td></tr>
                  ) : recentRuns.map((run) => {
                    const passRate = run.total_cases > 0 ? Math.round((run.passed_cases / run.total_cases) * 100) : 0;
                    return (
                      <tr key={run.id} className="border-t border-white/5 text-slate-300">
                        <td className="px-4 py-4"><span className="block text-slate-200">{new Date(run.created_at).toLocaleDateString()}</span><span className="mt-0.5 block text-xs text-slate-500">{new Date(run.created_at).toLocaleTimeString()}</span></td>
                        <td className="px-4 py-4"><span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${runStatusClass(run.status)}`}>{run.status}</span>{run.background_job_id && (run.status === "queued" || run.status === "running") ? <span className="ml-2 text-xs text-slate-500">background</span> : null}</td>
                        <td className="px-4 py-4"><span className="font-medium text-white">{passRate}%</span><span className="ml-2 text-xs text-slate-500">{run.passed_cases}/{run.total_cases}</span></td>
                        <td className="px-4 py-4"><span className="font-medium text-white">{Math.round(run.average_score * 100)}%</span></td>
                        <td className="px-4 py-4 text-slate-400">{run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
