import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { ConversationInbox } from "@/components/conversation-inbox";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Сообщения" };

export default async function MessagesPage() {
  await requireSession("/account/messages");
  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Сообщения</h1><p>Общайтесь с продавцами по объявлениям в одном месте.</p></header>
    <AccountNav current="/account/messages" />
    <ConversationInbox />
  </div>;
}
