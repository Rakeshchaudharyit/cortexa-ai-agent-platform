"use client";

import { ResponsiveConversationSidebar } from "@/components/chat/ResponsiveConversationSidebar";
import { useRouter } from "next/navigation";

export default function ChatIndexPage() {
  const router = useRouter();

  return (
    <>
      <ResponsiveConversationSidebar
        activeId={null}
        onNewConversation={(id) => router.push(`/chat/${id}`)}
      />
      <main
        id="main-content"
        tabIndex={-1}
        className="relative flex flex-1 items-center justify-center overflow-hidden px-6 py-10 text-center sm:px-10"
        data-testid="chat-index-main"
      >
        <div className="pointer-events-none absolute left-1/2 top-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-cyan-400/[0.055] blur-3xl" />
        <div className="relative max-w-xl">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10 text-lg font-bold text-cyan-200 shadow-lg shadow-cyan-950/20">
            C
          </div>
          <p className="cx-eyebrow mt-6">Grounded enterprise assistant</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Ask your knowledge with confidence.
          </h1>
          <p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-slate-400 sm:text-base">
            Start a conversation for general assistance, or switch to Document Knowledge to answer from active sources with citations and feedback controls.
          </p>
          <div className="mt-7 grid gap-3 text-left sm:grid-cols-3">
            {[
              ["Grounded answers", "Use governed document versions as the source of truth."],
              ["Traceable sources", "Review citations alongside every supported answer."],
              ["Quality feedback", "Mark responses helpful or send issues for review."],
            ].map(([title, body]) => (
              <div key={title} className="cx-panel-soft p-4">
                <p className="text-sm font-medium text-slate-100">{title}</p>
                <p className="mt-1.5 text-xs leading-5 text-slate-500">{body}</p>
              </div>
            ))}
          </div>
          <p className="mt-6 text-xs text-slate-600">Select a conversation or choose <span className="text-slate-400">+ New Chat</span> to begin.</p>
        </div>
      </main>
    </>
  );
}
