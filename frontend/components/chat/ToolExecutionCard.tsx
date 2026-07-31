"use client";

import { useState } from "react";

import type { ToolActivityItem, ToolExecutionSummary } from "@/types/api";

const FRIENDLY_NAMES: Record<string, string> = {
  calculator: "Using calculator…",
  knowledge_search: "Searching your knowledge base…",
  conversation_summary: "Creating conversation summary…",
  current_datetime: "Looking up the current date and time…",
};

function labelFor(toolName: string, status: string): string {
  if (status === "succeeded") {
    return `${toolName.replaceAll("_", " ")} completed`;
  }
  if (status === "failed") {
    return `${toolName.replaceAll("_", " ")} failed`;
  }
  return FRIENDLY_NAMES[toolName] ?? `Using ${toolName.replaceAll("_", " ")}…`;
}

type CardProps = {
  activity: ToolActivityItem | ToolExecutionSummary;
};

export function ToolExecutionCard({ activity }: CardProps) {
  const [expanded, setExpanded] = useState(false);
  const toolName = "tool_name" in activity ? activity.tool_name : "tool";
  const status =
    "status" in activity
      ? String(activity.status)
      : "started";
  const errorMessage =
    "error_message" in activity ? activity.error_message : null;
  const result =
    "result" in activity
      ? activity.result
      : "result_summary" in activity
        ? activity.result_summary
        : undefined;
  const args =
    "arguments" in activity
      ? activity.arguments
      : "arguments_summary" in activity
        ? activity.arguments_summary
        : undefined;

  const isFailed = status === "failed" || status === "denied" || status === "timed_out";
  const isRunning = status === "started" || status === "running" || status === "pending";
  const label = labelFor(toolName, isRunning ? "started" : isFailed ? "failed" : "succeeded");

  return (
    <div
      className={`rounded-xl border px-3 py-2 text-xs ${
        isFailed
          ? "border-rose-500/30 bg-rose-500/10 text-rose-100"
          : isRunning
            ? "border-amber-400/30 bg-amber-400/10 text-amber-100"
            : "border-emerald-400/30 bg-emerald-400/10 text-emerald-100"
      }`}
      data-testid="tool-execution-card"
      data-tool-name={toolName}
      data-tool-status={status}
      role="status"
      aria-live="polite"
      aria-busy={isRunning}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="font-medium">{label}</p>
        {(result || args || errorMessage) && (
          <button
            type="button"
            className="text-[11px] underline-offset-2 hover:underline"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            data-testid="tool-result-toggle"
          >
            {expanded ? "Hide details" : "Show details"}
          </button>
        )}
      </div>
      {isFailed && errorMessage && (
        <p className="mt-1 text-[11px] text-rose-200/90" data-testid="tool-error-message">
          {errorMessage}
        </p>
      )}
      {expanded && (
        <pre
          className="mt-2 max-h-48 overflow-auto rounded-lg bg-black/30 p-2 text-[11px] text-slate-200"
          data-testid="tool-result-details"
        >
          {JSON.stringify(
            {
              ...(args ? { arguments: args } : {}),
              ...(result ? { result } : {}),
              ...(errorMessage ? { error: errorMessage } : {}),
            },
            null,
            2,
          )}
        </pre>
      )}
    </div>
  );
}

type ActivityProps = {
  items: Array<ToolActivityItem | ToolExecutionSummary>;
};

export function ToolActivity({ items }: ActivityProps) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="flex w-full flex-col gap-2" data-testid="tool-activity" aria-label="Tool activity">
      {items.map((item) => (
        <ToolExecutionCard
          key={`${item.id}-${item.tool_name}-${item.status}`}
          activity={item}
        />
      ))}
    </div>
  );
}
