"use client";

import { useEffect, useState } from "react";

import { ConversationSidebar } from "@/components/chat/ConversationSidebar";

type Props = {
  activeId: string | null;
  onNewConversation: (id: string) => void;
};

export function ResponsiveConversationSidebar({ activeId, onNewConversation }: Props) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(false);
  }, [activeId]);

  return (
    <>
      <div className="hidden h-full shrink-0 md:block">
        <ConversationSidebar activeId={activeId} onNewConversation={onNewConversation} />
      </div>

      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 left-4 z-30 inline-flex min-h-11 items-center justify-center rounded-xl border border-cyan-400/20 bg-[#081321]/95 px-4 text-sm font-semibold text-cyan-100 shadow-xl shadow-black/30 backdrop-blur md:hidden"
        aria-label="Open conversations"
        aria-expanded={open}
      >
        Conversations
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Conversations">
          <button
            type="button"
            aria-label="Close conversations"
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-[min(20rem,88vw)] shadow-2xl">
            <div className="relative h-full">
              <ConversationSidebar
                activeId={activeId}
                onNewConversation={(id) => {
                  setOpen(false);
                  onNewConversation(id);
                }}
              />
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="absolute right-3 top-3 rounded-lg border border-white/10 bg-slate-950/80 px-2.5 py-1.5 text-xs font-medium text-slate-300"
                aria-label="Close conversations"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
