import type { AdminRecentActivityItem } from "@/types/admin";

export function ActivityTimeline({ items }: { items: AdminRecentActivityItem[] }) {
  if (!items.length) {
    return <p className="text-sm text-slate-500">No recent activity.</p>;
  }
  return (
    <ol className="space-y-3" data-testid="admin-activity-timeline">
      {items.map((item, index) => (
        <li key={`${item.created_at}-${index}`} className="flex gap-3">
          <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.6)]" />
          <div>
            <p className="text-sm text-slate-100">{item.summary}</p>
            <p className="text-xs text-slate-500">
              {item.kind}
              {item.actor_email ? ` · ${item.actor_email}` : ""}
              {" · "}
              {new Date(item.created_at).toLocaleString()}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
