"use client";

import Link from "next/link";

export type MemoryActivityState = {
  retrieving?: boolean;
  count?: number;
  references?: Array<{ title: string; category: string }>;
  proposed?: { title: string; category: string; reason?: string } | null;
  savedMessage?: string | null;
  forgottenMessage?: string | null;
  failedMessage?: string | null;
  enabled?: boolean;
};

type Props = {
  activity: MemoryActivityState;
};

export function MemoryActivity({ activity }: Props) {
  if (activity.enabled === false) {
    return (
      <div
        className="rounded-lg border border-slate-500/20 bg-slate-500/10 px-3 py-2 text-xs text-slate-400"
        data-testid="memory-activity-disabled"
      >
        Memory off for this conversation ·{" "}
        <Link href="/memories" className="text-cyan-300 hover:text-cyan-200">
          Manage memories
        </Link>
      </div>
    );
  }

  const lines: string[] = [];
  if (activity.retrieving) lines.push("Using relevant memory…");
  if (typeof activity.count === "number" && activity.count > 0) {
    lines.push(
      activity.count === 1
        ? "1 approved memory applied"
        : `${activity.count} approved memories applied`,
    );
  }
  if (activity.proposed) lines.push("Memory suggestion available");
  if (activity.savedMessage) lines.push(activity.savedMessage);
  if (activity.forgottenMessage) lines.push(activity.forgottenMessage);
  if (activity.failedMessage) lines.push(activity.failedMessage);

  if (lines.length === 0 && !activity.references?.length && !activity.proposed) {
    return null;
  }

  return (
    <div
      className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2 text-xs text-cyan-100/90"
      data-testid="memory-activity"
    >
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
      {activity.references && activity.references.length > 0 ? (
        <details className="mt-1" data-testid="memory-references">
          <summary className="cursor-pointer text-cyan-200/80">Memory references</summary>
          <ul className="mt-1 list-disc pl-4 text-slate-300">
            {activity.references.map((ref) => (
              <li key={`${ref.category}-${ref.title}`}>
                [{ref.category}] {ref.title}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {activity.proposed ? (
        <div
          className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-amber-50"
          data-testid="memory-proposal-card"
        >
          <p className="font-medium">Suggested memory: {activity.proposed.title}</p>
          <p className="text-amber-100/80">{activity.proposed.category}</p>
          {activity.proposed.reason ? (
            <p className="mt-1 text-amber-100/70">{activity.proposed.reason}</p>
          ) : null}
          <Link href="/memories" className="mt-2 inline-block text-cyan-200 hover:text-cyan-100">
            Review on Memories page
          </Link>
        </div>
      ) : null}
      <Link href="/memories" className="mt-2 inline-block text-cyan-300 hover:text-cyan-200">
        Manage memories
      </Link>
    </div>
  );
}
