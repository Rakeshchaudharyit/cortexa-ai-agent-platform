"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { createConversation, streamMessage } from "@/services/conversations";

const MIN_PROMPT_LENGTH = 12;

export function NewAgentRunDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const abortRef = useRef<AbortController | null>(null);
  const [prompt, setPrompt] = useState("");
  const [profile, setProfile] = useState<"fast" | "balanced" | "deep">("fast");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const close = () => {
    if (busy) return;
    setPrompt("");
    setProfile("fast");
    setStatus(null);
    setError(null);
    onClose();
  };

  const submit = async () => {
    const content = prompt.trim();
    if (content.length < MIN_PROMPT_LENGTH || busy) return;

    setBusy(true);
    setError(null);
    setStatus("Creating a private workspace…");

    const conversation = await createConversation({
      title: "Agent execution",
    });
    if (!conversation.ok) {
      setBusy(false);
      setStatus(null);
      setError(conversation.error);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    let runId: string | null = null;
    let completed = false;

    try {
      setStatus("Creating a coordinated execution plan…");
      for await (const event of streamMessage(
        conversation.data.id,
        {
          content,
          force_multi_agent: true,
          execution_profile: profile,
        },
        controller.signal,
      )) {
        const data = event.data as Record<string, unknown>;
        const eventRunId = data.agent_run_id ?? data.run_id;
        if (typeof eventRunId === "string" && eventRunId) {
          runId = eventRunId;
          setStatus("Agent run created. Keeping the execution channel open…");
        }

        if (event.event === "planning_started" || event.event === "plan_created") {
          setStatus("Building the execution plan…");
        }
        if (event.event === "agent_started" || event.event === "task_started") {
          setStatus("Specialist agents are executing…");
        }
        if (event.event === "approval_required") setStatus("Approval is required…");
        if (event.event === "run_completed") setStatus("Saving the final response…");
        if (event.event === "complete") {
          completed = true;
          setStatus("Final response saved. Opening the completed run…");
          if (runId) {
            router.push(`/agent-runs/${runId}`);
            router.refresh();
          }
        }
        if (event.event === "error") {
          const nested = data.error;
          const message =
            nested && typeof nested === "object" && "message" in nested
              ? String(nested.message)
              : "The agent run could not be started.";
          throw new Error(message);
        }
      }

      if (!runId) {
        setError("The coordinated run did not return a run identifier. Please try again.");
        setStatus(null);
      } else if (!completed) {
        // The stream ended without the terminal completion event. Open the durable
        // run so the user can inspect its final or recovery state without starting
        // a duplicate execution.
        setStatus("Execution channel ended. Opening the durable run…");
        router.push(`/agent-runs/${runId}`);
        router.refresh();
      }
    } catch (caught) {
      if (!controller.signal.aborted && runId) {
        // The durable start checkpoint exists even when the browser transport
        // disconnects. Reconnect through the owner-scoped run detail endpoint
        // instead of starting a duplicate execution or showing a dead-end error.
        setError(null);
        setStatus("Execution channel interrupted. Reconnecting to the durable run…");
        router.push(`/agent-runs/${runId}`);
        router.refresh();
      } else if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "The agent run could not be started.");
        setStatus(null);
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-agent-run-title"
      data-testid="new-agent-run-dialog"
    >
      <div className="w-full max-w-2xl rounded-2xl border border-white/10 bg-slate-950 p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[.2em] text-cyan-300">
              Coordinated execution
            </p>
            <h2 id="new-agent-run-title" className="mt-2 text-2xl font-semibold text-white">
              New Agent Run
            </h2>
            <p className="mt-2 text-sm text-slate-400">
              Describe the outcome. Cortexa will create a plan and route work directly to
              specialist agents; this workflow never falls back to ordinary chat.
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={busy}
            aria-label="Close new agent run dialog"
            className="rounded-lg px-3 py-2 text-slate-400 hover:bg-white/5 hover:text-white disabled:opacity-40"
          >
            ✕
          </button>
        </div>

        <label className="mt-6 block text-sm font-medium text-slate-200" htmlFor="agent-run-prompt">
          Objective
        </label>
        <textarea
          id="agent-run-prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          disabled={busy}
          rows={7}
          maxLength={100_000}
          placeholder="Example: Review the available knowledge, identify the main technical themes, compare implementation options, and produce a prioritized recommendation using the appropriate specialist agents."
          className="mt-2 w-full resize-y rounded-xl border border-white/10 bg-slate-900/80 px-4 py-3 text-sm text-white outline-none placeholder:text-slate-600 focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/10 disabled:opacity-60"
        />
        <div className="mt-2 flex justify-between text-xs text-slate-500">
          <span>Use a clear outcome with multiple steps for best routing.</span>
          <span>{prompt.length.toLocaleString()} / 100,000</span>
        </div>

        <fieldset className="mt-5">
          <legend className="text-sm font-medium text-slate-200">Execution mode</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {([
              ["fast", "Fast", "Target 20–60s · strict 90s cap"],
              ["balanced", "Balanced", "More time for retries · 150s cap"],
              ["deep", "Deep", "Maximum analysis depth · 240s cap"],
            ] as const).map(([value, label, detail]) => (
              <label
                key={value}
                className={`cursor-pointer rounded-xl border p-3 text-sm transition ${
                  profile === value
                    ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-50"
                    : "border-white/10 bg-slate-900/50 text-slate-300 hover:border-white/20"
                }`}
              >
                <input
                  type="radio"
                  name="execution-profile"
                  value={value}
                  checked={profile === value}
                  onChange={() => setProfile(value)}
                  disabled={busy}
                  className="sr-only"
                />
                <span className="block font-semibold">{label}</span>
                <span className="mt-1 block text-xs text-slate-400">{detail}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {status ? (
          <div className="mt-4 rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-3 text-sm text-cyan-100" role="status">
            {status}
          </div>
        ) : null}
        {error ? (
          <div className="mt-4 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-100" role="alert">
            {error}
          </div>
        ) : null}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={close}
            disabled={busy}
            className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/5 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || prompt.trim().length < MIN_PROMPT_LENGTH}
            className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Starting…" : "Run with AI Agents"}
          </button>
        </div>
      </div>
    </div>
  );
}
