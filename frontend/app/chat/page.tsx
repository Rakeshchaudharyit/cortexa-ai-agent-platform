"use client";

import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { useRouter } from "next/navigation";

export default function ChatIndexPage() {
  const router = useRouter();

  return (
    <>
      <ConversationSidebar
        activeId={null}
        onNewConversation={(id) => router.push(`/chat/${id}`)}
      />
      <main
        className="flex flex-1 flex-col items-center justify-center gap-4 text-center px-8"
        data-testid="chat-index-main"
      >
        <p className="text-4xl">💬</p>
        <h1 className="text-xl font-semibold text-slate-100">Cortexa Chat</h1>
        <p className="max-w-sm text-sm text-slate-400">
          Select a conversation from the sidebar or start a new one to begin chatting with your
          documents.
        </p>
      </main>
    </>
  );
}
