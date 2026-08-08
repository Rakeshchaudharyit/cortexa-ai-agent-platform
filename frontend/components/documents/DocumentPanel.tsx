"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import {
  activateDocumentVersion,
  archiveDocument,
  compareDocumentVersions,
  createDocumentFolder,
  deleteDocument,
  deleteDocumentFolder,
  getDocumentTimeline,
  getDocumentVersions,
  listDocumentFolders,
  listDocuments,
  queryRag,
  reindexDocumentVersion,
  restoreDocument,
  updateDocumentMetadata,
  uploadDocument,
  validateDocumentFile,
} from "@/services/documents";
import type {
  DocumentFolderResponse,
  DocumentResponse,
  DocumentTimelineResponse,
  DocumentVersionCompareResponse,
  DocumentVersionHistoryResponse,
  RagCitation,
  RagQueryResponse,
} from "@/types/api";

type PanelState = "idle" | "loading" | "uploading" | "querying" | "saving";

function statusTone(status: DocumentResponse["status"]): string {
  if (status === "ready") return "text-emerald-300";
  if (status === "failed") return "text-rose-300";
  return "text-amber-300";
}
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}
function eventLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function isActiveJob(doc: DocumentResponse): boolean {
  return doc.job_status === "queued" || doc.job_status === "running" || doc.job_status === "retrying";
}

export function DocumentPanel() {
  const { status: authStatus } = useAuth();
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [folders, setFolders] = useState<DocumentFolderResponse[]>([]);
  const [panelState, setPanelState] = useState<PanelState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [ragResult, setRagResult] = useState<RagQueryResponse | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedFolder, setSelectedFolder] = useState("");
  const [folderFilter, setFolderFilter] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [versionTarget, setVersionTarget] = useState<DocumentResponse | null>(null);
  const [history, setHistory] = useState<DocumentVersionHistoryResponse | null>(null);
  const [timeline, setTimeline] = useState<DocumentTimelineResponse | null>(null);
  const [comparison, setComparison] = useState<DocumentVersionCompareResponse | null>(null);

  const readyCount = documents.filter(
    (doc) => doc.status === "ready" && doc.is_active_version && !doc.is_archived,
  ).length;
  const canQuery = readyCount > 0 && panelState === "idle";
  const hasActiveJobs = documents.some((doc) =>
    doc.job_status === "queued" || doc.job_status === "running" || doc.job_status === "retrying"
  );

  const refresh = useCallback(async () => {
    setPanelState("loading");
    setError(null);
    const [docs, folderResult] = await Promise.all([
      listDocuments({ archived: showArchived, folderId: folderFilter || null }),
      listDocumentFolders(),
    ]);
    if (!docs.ok) setError(docs.error);
    else setDocuments(docs.data.items);
    if (!folderResult.ok) setError(folderResult.error);
    else setFolders(folderResult.data.items);
    setPanelState("idle");
  }, [showArchived, folderFilter]);

  useEffect(() => {
    if (authStatus === "authenticated") void refresh();
  }, [authStatus, refresh]);

  useEffect(() => {
    if (authStatus !== "authenticated" || !hasActiveJobs) return;
    const timer = window.setInterval(() => {
      void listDocuments({ archived: showArchived, folderId: folderFilter || null }).then((result) => {
        if (result.ok) setDocuments(result.data.items);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [authStatus, hasActiveJobs, showArchived, folderFilter]);

  if (authStatus !== "authenticated") return null;

  async function handleCreateFolder(event: FormEvent) {
    event.preventDefault();
    if (!newFolderName.trim()) return;
    setPanelState("saving"); setError(null); setNotice(null);
    const result = await createDocumentFolder(newFolderName.trim());
    if (!result.ok) setError(result.error);
    else { setNewFolderName(""); setNotice(`Folder “${result.data.name}” created.`); }
    await refresh();
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setNotice(null); setRagResult(null);
    if (!selectedFile) { setError("Choose a document to upload"); return; }
    const validationError = validateDocumentFile(selectedFile);
    if (validationError) { setError(validationError); return; }
    setPanelState("uploading");
    const result = await uploadDocument(
      selectedFile,
      selectedFolder || versionTarget?.folder_id || null,
      versionTarget?.id || null,
    );
    if (!result.ok) { setError(result.error); setPanelState("idle"); return; }
    setSelectedFile(null); setVersionTarget(null);
    setNotice(`Version ${result.data.version_number} of “${result.data.title || result.data.original_filename}” was queued for background indexing.`);
    const input = document.getElementById("document-upload-input") as HTMLInputElement | null;
    if (input) input.value = "";
    await refresh();
  }

  async function handleArchive(doc: DocumentResponse) {
    setPanelState("saving"); setError(null); setNotice(null);
    const result = doc.is_archived ? await restoreDocument(doc.id) : await archiveDocument(doc.id);
    if (!result.ok) setError(result.error);
    else setNotice(doc.is_archived ? "Version restored and activated." : "Version archived and excluded from RAG.");
    await refresh();
  }

  async function handleEdit(doc: DocumentResponse) {
    const title = window.prompt("Document title", doc.title ?? doc.original_filename);
    if (title === null) return;
    const tags = window.prompt("Tags (comma separated)", doc.tags.join(", "));
    if (tags === null) return;
    const result = await updateDocumentMetadata(doc.id, {
      title, folder_id: doc.folder_id, tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
    });
    if (!result.ok) setError(result.error); else setNotice("Document metadata updated and added to its timeline.");
    await refresh();
  }

  async function handleDelete(doc: DocumentResponse) {
    if (!window.confirm(`Delete version ${doc.version_number} of “${doc.title || doc.original_filename}”? This cannot be undone.`)) return;
    const result = await deleteDocument(doc.id);
    if (!result.ok) setError(result.error); else setNotice("Document version permanently deleted.");
    await refresh();
  }

  async function handleDeleteFolder(folder: DocumentFolderResponse) {
    if (!window.confirm(`Delete folder “${folder.name}”? Documents will move to Unfiled.`)) return;
    const result = await deleteDocumentFolder(folder.id);
    if (!result.ok) setError(result.error); else setNotice("Folder deleted. Documents were preserved.");
    if (folderFilter === folder.id) setFolderFilter("");
    await refresh();
  }

  async function openHistory(doc: DocumentResponse) {
    setError(null); setComparison(null);
    const [versionsResult, timelineResult] = await Promise.all([
      getDocumentVersions(doc.id), getDocumentTimeline(doc.id),
    ]);
    if (!versionsResult.ok) { setError(versionsResult.error); return; }
    setHistory(versionsResult.data);
    if (timelineResult.ok) setTimeline(timelineResult.data);
  }

  async function handleActivate(id: string) {
    const result = await activateDocumentVersion(id);
    if (!result.ok) { setError(result.error); return; }
    setNotice(`Version ${result.data.version_number} is now active for RAG.`);
    await openHistory(result.data);
    await refresh();
  }

  async function handleCompare() {
    if (!history || history.versions.length < 2) return;
    const [right, left] = history.versions;
    const result = await compareDocumentVersions(left.id, right.id);
    if (!result.ok) setError(result.error); else setComparison(result.data);
  }

  async function handleReindex(doc: DocumentResponse) {
    if (!window.confirm(`Rebuild chunks and embeddings for version ${doc.version_number}?`)) return;
    setPanelState("saving"); setError(null); setNotice(null);
    const result = await reindexDocumentVersion(doc.id);
    if (!result.ok) setError(result.error);
    else setNotice(`Version ${result.data.version_number} was queued for background re-indexing.`);
    await refresh();
  }

  async function handleRagSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setRagResult(null);
    const trimmed = question.trim();
    if (!trimmed) { setError("Enter a question about your documents"); return; }
    setPanelState("querying");
    const result = await queryRag({ question: trimmed });
    if (!result.ok) setError(result.error); else setRagResult(result.data);
    setPanelState("idle");
  }

  return (
    <section id="documents" className="cx-panel overflow-hidden" data-testid="document-panel">
      <div className="border-b border-white/[0.07] px-5 py-6 sm:px-6 lg:px-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="cx-eyebrow">Governed knowledge workspace</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">Knowledge library</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              Organize source material, publish immutable versions, track indexing progress, and control exactly which knowledge is active for grounded RAG.
            </p>
          </div>
          <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-3 lg:w-auto lg:min-w-[360px]">
            <div className="cx-panel-soft p-3.5"><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Active sources</p><p className="mt-1.5 text-xl font-semibold text-white">{readyCount}</p></div>
            <div className="cx-panel-soft p-3.5"><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Folders</p><p className="mt-1.5 text-xl font-semibold text-white">{folders.length}</p></div>
            <div className="cx-panel-soft p-3.5"><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">In progress</p><p className="mt-1.5 text-xl font-semibold text-white">{documents.filter(isActiveJob).length}</p></div>
          </div>
        </div>
      </div>

      <div className="space-y-5 p-5 sm:p-6 lg:p-7">
        {notice ? <div role="status" aria-live="polite" className="flex items-start gap-2 rounded-xl border border-emerald-400/15 bg-emerald-500/[0.07] px-4 py-3 text-sm text-emerald-200"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />{notice}</div> : null}
        {error ? <div className="rounded-xl border border-rose-400/15 bg-rose-500/[0.07] px-4 py-3 text-sm text-rose-200" role="alert" data-testid="document-error">{error}</div> : null}

        <div className="grid gap-4 lg:grid-cols-[minmax(240px,0.7fr)_minmax(0,1.7fr)]">
          <div className="cx-panel-soft p-4 sm:p-5">
            <div className="flex items-center justify-between gap-3">
              <div><p className="text-sm font-semibold text-white">Folders</p><p className="mt-1 text-xs text-slate-500">Keep knowledge organized by domain.</p></div>
              {folderFilter ? <button type="button" onClick={() => setFolderFilter("")} className="text-xs text-cyan-300 hover:text-cyan-200">View all</button> : null}
            </div>
            <form className="mt-4 flex gap-2" onSubmit={handleCreateFolder}>
              <input value={newFolderName} onChange={(e) => setNewFolderName(e.target.value)} placeholder="New folder" className="cx-input min-w-0 flex-1 py-2" />
              <button disabled={!newFolderName.trim() || panelState !== "idle"} className="cx-button-secondary min-h-0 px-3 py-2 text-xs">Create</button>
            </form>
            <div className="mt-4 space-y-1.5">
              {folders.map((folder) => (
                <div key={folder.id} className={`group flex items-center justify-between rounded-xl border px-3 py-2.5 text-sm transition ${folderFilter === folder.id ? "border-cyan-400/15 bg-cyan-400/[0.06]" : "border-transparent bg-white/[0.02] hover:border-white/[0.06] hover:bg-white/[0.035]"}`}>
                  <button type="button" onClick={() => setFolderFilter(folder.id)} className="min-w-0 flex-1 truncate text-left text-slate-200">
                    {folder.name} <span className="ml-1 text-xs text-slate-600">{folder.document_count}</span>
                  </button>
                  <button type="button" onClick={() => void handleDeleteFolder(folder)} className="ml-2 text-xs text-slate-600 opacity-0 transition hover:text-rose-300 group-hover:opacity-100 focus:opacity-100">Delete</button>
                </div>
              ))}
              {folders.length === 0 ? <div className="rounded-xl border border-dashed border-white/10 px-4 py-5 text-center"><p className="text-sm text-slate-500">No folders yet.</p><p className="mt-1 text-xs text-slate-600">Create one to group knowledge by project, team, or domain.</p></div> : null}
            </div>
          </div>

          <form className="relative overflow-hidden rounded-2xl border border-cyan-400/10 bg-cyan-400/[0.025] p-4 sm:p-5" onSubmit={handleUpload} aria-label="Upload document">
            <div className="pointer-events-none absolute -right-20 -top-20 h-48 w-48 rounded-full bg-cyan-400/[0.05] blur-3xl" />
            <div className="relative flex flex-col gap-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-white">{versionTarget ? `Publish version ${versionTarget.version_number + 1}` : "Add knowledge source"}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">TXT, Markdown, PDF, and DOCX are indexed in the background so the workspace remains responsive.</p>
                </div>
                {versionTarget ? <button type="button" onClick={() => setVersionTarget(null)} className="text-xs text-slate-500 hover:text-white">Cancel versioning</button> : null}
              </div>
              {versionTarget ? <div className="rounded-xl border border-violet-400/10 bg-violet-500/[0.05] px-3 py-2.5 text-xs leading-5 text-violet-200">Creating a new immutable version of <strong>{versionTarget.title || versionTarget.original_filename}</strong>. The active version changes only after indexing succeeds.</div> : null}
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_220px_auto] sm:items-end">
                <label className="block min-w-0">
                  <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-600">Document</span>
                  <input id="document-upload-input" data-testid="document-upload-input" aria-label="Upload document" type="file" accept=".txt,.md,.pdf,.docx" onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)} className="block w-full rounded-xl border border-white/10 bg-slate-950/55 px-3 py-2 text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-white/[0.07] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-200" />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-600">Folder</span>
                  <select value={selectedFolder} onChange={(e) => setSelectedFolder(e.target.value)} className="cx-input py-2.5"><option value="">Unfiled</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select>
                </label>
                <button data-testid="document-upload-button" disabled={!selectedFile || panelState !== "idle"} className="cx-button-primary min-w-[110px]">{panelState === "uploading" ? "Uploading…" : versionTarget ? "Publish version" : "Upload"}</button>
              </div>
            </div>
          </form>
        </div>

        <div className="flex flex-col gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3 sm:flex-row sm:items-center">
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <select value={folderFilter} onChange={(e) => setFolderFilter(e.target.value)} className="rounded-lg border border-white/10 bg-slate-950/70 px-3 py-2 text-xs text-slate-300"><option value="">All folders</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select>
            <label className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-slate-400"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="accent-cyan-400" /> Show archived</label>
          </div>
          <button type="button" onClick={() => void refresh()} className="cx-button-secondary min-h-0 px-3 py-2 text-xs">Refresh</button>
        </div>

        <div className="space-y-2.5" data-testid="document-list">
          {documents.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.015] px-6 py-10 text-center">
              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.04] text-sm text-slate-500">KB</div>
              <p className="mt-4 text-sm font-medium text-slate-300">No documents uploaded yet</p>
              <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-600">Upload a source above to start building a governed, citation-ready knowledge base.</p>
            </div>
          ) : documents.map((doc) => (
            <article key={doc.id} data-testid="document-row" className="rounded-2xl border border-white/[0.07] bg-slate-950/35 px-4 py-4 transition hover:border-white/10 hover:bg-slate-950/45 sm:px-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="max-w-full truncate text-sm font-semibold text-slate-100">{doc.title || doc.original_filename}</p>
                    {doc.is_active_version ? <span className="rounded-full border border-emerald-400/15 bg-emerald-500/[0.08] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-200">Active for RAG</span> : null}
                    <span className="rounded-full border border-white/[0.06] bg-white/[0.035] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">{doc.lifecycle_state}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs text-slate-500">
                    <span className={`font-medium ${statusTone(doc.status)}`}>{eventLabel(doc.status)}</span><span>·</span><span>{folders.find((folder) => folder.id === doc.folder_id)?.name || "Unfiled"}</span><span>·</span><span>v{doc.version_number}</span><span>·</span><span>{formatBytes(doc.file_size_bytes)}</span><span>·</span><span>{doc.chunk_count} chunks</span>
                  </div>
                  {doc.job_status ? (
                    <div className="mt-3 max-w-xl rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
                      <div className="flex items-center justify-between gap-3 text-[11px] text-slate-500"><span className="truncate">{doc.job_status_message || `Background ${doc.job_status}`}</span><span className="shrink-0 font-medium text-slate-400">{doc.job_progress_percent ?? 0}%</span></div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.07]"><div className="h-full rounded-full bg-cyan-400 transition-all" style={{ width: `${doc.job_progress_percent ?? 0}%` }} /></div>
                    </div>
                  ) : null}
                  {doc.error_message ? <p className="mt-2 text-xs text-rose-300">{doc.error_message}</p> : null}
                  {doc.tags.length ? <div className="mt-2.5 flex flex-wrap gap-1.5">{doc.tags.map((tag) => <span key={tag} className="rounded-md bg-cyan-400/[0.055] px-2 py-1 text-[10px] text-cyan-200/80">#{tag}</span>)}</div> : null}
                </div>
                <div className="flex flex-wrap gap-1.5 lg:max-w-[360px] lg:justify-end">
                  <button type="button" onClick={() => void openHistory(doc)} className="rounded-lg border border-cyan-400/10 bg-cyan-400/[0.05] px-2.5 py-1.5 text-xs text-cyan-200 transition hover:bg-cyan-400/[0.09]">Versions</button>
                  <button type="button" disabled={isActiveJob(doc)} onClick={() => { setVersionTarget(doc); setSelectedFolder(doc.folder_id || ""); window.scrollTo({ top: 0, behavior: "smooth" }); }} className="rounded-lg border border-violet-400/10 bg-violet-500/[0.05] px-2.5 py-1.5 text-xs text-violet-200 transition hover:bg-violet-500/[0.09] disabled:opacity-40">New version</button>
                  <button type="button" disabled={isActiveJob(doc)} onClick={() => void handleReindex(doc)} className="rounded-lg border border-blue-400/10 bg-blue-500/[0.05] px-2.5 py-1.5 text-xs text-blue-200 transition hover:bg-blue-500/[0.09] disabled:opacity-40">Re-index</button>
                  <button type="button" onClick={() => void handleEdit(doc)} className="rounded-lg border border-white/[0.07] bg-white/[0.035] px-2.5 py-1.5 text-xs text-slate-300 transition hover:bg-white/[0.06]">Edit</button>
                  <button type="button" disabled={isActiveJob(doc)} onClick={() => void handleArchive(doc)} className="rounded-lg border border-amber-400/10 bg-amber-500/[0.05] px-2.5 py-1.5 text-xs text-amber-200 transition hover:bg-amber-500/[0.09] disabled:opacity-40">{doc.is_archived ? "Restore" : "Archive"}</button>
                  <button type="button" data-testid="document-delete-button" disabled={isActiveJob(doc)} onClick={() => void handleDelete(doc)} className="rounded-lg border border-rose-400/10 bg-rose-500/[0.05] px-2.5 py-1.5 text-xs text-rose-200 transition hover:bg-rose-500/[0.09] disabled:opacity-40">Delete</button>
                </div>
              </div>
            </article>
          ))}
        </div>

        <form className="rounded-2xl border border-white/[0.07] bg-gradient-to-br from-white/[0.035] to-cyan-400/[0.025] p-4 sm:p-5" onSubmit={handleRagSubmit}>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
            <label className="min-w-0 flex-1 text-sm font-medium text-slate-200">
              <span>Ask a grounded question</span>
              <span className="mt-1 block text-xs font-normal leading-5 text-slate-500">Quickly verify that active knowledge is retrievable and citation-ready.</span>
              <textarea data-testid="rag-question-input" rows={3} value={question} disabled={!canQuery} onChange={(e) => setQuestion(e.target.value)} placeholder={readyCount ? "Ask a question answered only from active versions…" : "Publish or restore an active ready version first"} className="cx-input mt-3 resize-y disabled:opacity-50" />
            </label>
            <button data-testid="rag-submit-button" disabled={!canQuery || !question.trim()} className="cx-button-primary lg:mb-0.5">{panelState === "querying" ? "Searching…" : "Ask knowledge"}</button>
          </div>
        </form>
        {ragResult ? <RagResultView result={ragResult} /> : null}

        {history ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-3 backdrop-blur-sm sm:p-4" role="dialog" aria-modal="true" aria-labelledby="version-history-title">
            <div className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-3xl border border-white/10 bg-[#081321] p-5 shadow-2xl shadow-black/40 sm:p-7">
              <div className="flex items-start justify-between gap-4 border-b border-white/[0.07] pb-5">
                <div><p className="cx-eyebrow">Knowledge governance</p><h3 id="version-history-title" className="mt-2 break-words text-xl font-semibold text-white">{history.title}</h3><p className="mt-1 text-sm text-slate-500">Immutable versions, active-source control, and lifecycle audit history.</p></div>
                <button type="button" onClick={() => { setHistory(null); setTimeline(null); setComparison(null); }} className="cx-button-secondary min-h-0 px-3 py-2 text-xs">Close</button>
              </div>
              <div className="mt-6 grid gap-6 lg:grid-cols-2">
                <div>
                  <div className="flex items-center justify-between"><h4 className="text-sm font-semibold text-slate-200">Versions</h4>{history.versions.length > 1 ? <button type="button" onClick={() => void handleCompare()} className="text-xs font-medium text-cyan-300 hover:text-cyan-200">Compare latest two</button> : null}</div>
                  <div className="mt-3 space-y-2.5">
                    {history.versions.map((version) => <div key={version.id} className={`rounded-2xl border p-3.5 ${version.is_active_version ? "border-emerald-400/15 bg-emerald-500/[0.04]" : "border-white/[0.07] bg-white/[0.025]"}`}><div className="flex items-center justify-between gap-3"><div><div className="flex items-center gap-2"><p className="text-sm font-medium text-white">Version {version.version_number}</p>{version.is_active_version ? <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-200">Active</span> : null}</div><p className="mt-1 text-xs text-slate-500">{eventLabel(version.lifecycle_state)} · {version.chunk_count} chunks · {new Date(version.created_at).toLocaleString()}</p></div>{!version.is_active_version && version.status === "ready" ? <button type="button" onClick={() => void handleActivate(version.id)} className="rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-200">Make active</button> : null}</div></div>)}
                  </div>
                  {comparison ? <div className="mt-4 rounded-2xl border border-cyan-400/10 bg-cyan-400/[0.04] p-4 text-sm text-cyan-100"><p className="font-medium">Version comparison</p><p className="mt-2 text-xs leading-5 text-cyan-100/70">Changed fields: {comparison.changed_fields.length ? comparison.changed_fields.join(", ") : "No tracked metadata fields"}</p><div className="mt-3 grid grid-cols-2 gap-2"><div className="rounded-lg bg-black/10 p-2.5"><p className="text-[10px] uppercase tracking-wider text-cyan-200/50">Chunk delta</p><p className="mt-1 font-semibold">{comparison.chunk_count_delta >= 0 ? "+" : ""}{comparison.chunk_count_delta}</p></div><div className="rounded-lg bg-black/10 p-2.5"><p className="text-[10px] uppercase tracking-wider text-cyan-200/50">Character delta</p><p className="mt-1 font-semibold">{comparison.character_count_delta >= 0 ? "+" : ""}{comparison.character_count_delta}</p></div></div></div> : null}
                </div>
                <div><h4 className="text-sm font-semibold text-slate-200">Lifecycle timeline</h4><div className="mt-3 space-y-0">{timeline?.items.map((event, index) => <div key={event.id} className="relative flex gap-3 pb-4"><div className="relative flex w-3 shrink-0 justify-center"><span className="mt-1.5 h-2 w-2 rounded-full bg-cyan-400" />{index < (timeline?.items.length ?? 0) - 1 ? <span className="absolute bottom-0 top-4 w-px bg-white/10" /> : null}</div><div><p className="text-sm text-slate-300">{eventLabel(event.event_type)}</p><p className="mt-0.5 text-xs text-slate-600">{new Date(event.created_at).toLocaleString()}</p></div></div>)}{timeline?.items.length === 0 ? <div className="rounded-xl border border-dashed border-white/10 p-5 text-sm text-slate-500">No lifecycle events yet.</div> : null}</div></div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function RagResultView({ result }: { result: RagQueryResponse }) {
  const hasCitations = result.citations.length > 0;
  const noResult = !result.grounded || result.retrieval_count === 0;
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">Knowledge check</p><p className="mt-1 text-sm text-slate-400">{noResult ? "No grounded source found" : `${result.retrieval_count} relevant passage${result.retrieval_count === 1 ? "" : "s"} retrieved`}</p></div>
        {!noResult ? <span className="rounded-full border border-emerald-400/15 bg-emerald-500/[0.07] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-200">Grounded</span> : null}
      </div>
      {noResult ? <p className="mt-4 rounded-xl border border-amber-400/15 bg-amber-500/[0.06] px-4 py-3 text-sm leading-6 text-amber-100" data-testid="rag-no-result">{result.answer}</p> : <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.025] px-4 py-4" data-testid="rag-answer"><p className="whitespace-pre-wrap text-sm leading-7 text-slate-200">{result.answer}</p></div>}
      {hasCitations ? <div data-testid="rag-citations" className="mt-4 grid gap-2 lg:grid-cols-2"><div className="lg:col-span-2"><h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-600">Supporting citations</h3></div>{result.citations.map((citation: RagCitation) => <article key={`${citation.citation_id}-${citation.chunk_id}`} className="rounded-xl border border-cyan-400/10 bg-cyan-400/[0.025] px-4 py-3" data-testid="rag-citation"><p className="text-xs font-medium text-cyan-200">{citation.citation_id} {citation.filename}{citation.page_number != null ? ` · p.${citation.page_number}` : ""}</p><p className="mt-1 text-[10px] uppercase tracking-wider text-slate-600">Similarity {(citation.similarity * 100).toFixed(0)}%</p><p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-500">{citation.excerpt}</p></article>)}</div> : null}
    </div>
  );
}
