"use client";

import { use } from "react";
import { useRouter } from "next/navigation";

import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";

type Props = {
  params: Promise<{ conversationId: string }>;
};

export default function ConversationPage({ params }: Props) {
  const { conversationId } = use(params);
  const router = useRouter();

  return (
    <>
      <ConversationSidebar
        activeId={conversationId}
        onNewConversation={(id) => router.push(`/chat/${id}`)}
      />
      <main className="flex flex-1 flex-col overflow-hidden" data-testid="conversation-main">
        <ChatPanel conversationId={conversationId} />
      </main>
    </>
  );
}
