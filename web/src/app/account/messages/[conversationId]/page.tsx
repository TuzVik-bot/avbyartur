import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { ConversationThreadView } from "@/components/conversation-thread";
import { requireSession } from "@/lib/server";

type Params = { conversationId: string };
export const metadata: Metadata = { title: "Переписка" };

export default async function ConversationPage({ params }: { params: Promise<Params> }) {
  const { conversationId } = await params;
  await requireSession(`/account/messages/${encodeURIComponent(conversationId)}`);
  return <div className="page-width">
    <AccountNav current="/account/messages" />
    <ConversationThreadView conversationId={conversationId} />
  </div>;
}
