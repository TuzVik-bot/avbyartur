import type { Metadata } from "next";
import Link from "next/link";
import { AccountNav } from "@/components/account-nav";
import { ConversationStartForm } from "@/components/conversation-start-form";
import { requireSession } from "@/lib/server";
import { serverApi } from "@/lib/server-api";

type SearchParams = { listing_id?: string | string[]; intent?: string | string[] };
export const metadata: Metadata = { title: "Новое сообщение" };

export default async function NewMessagePage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const rawListingId = Array.isArray(params.listing_id) ? params.listing_id[0] : params.listing_id;
  const listingId = rawListingId?.trim() && rawListingId.length <= 128 ? rawListingId.trim() : "";
  const exchangeIntent = (Array.isArray(params.intent) ? params.intent[0] : params.intent) === "exchange";
  const nextPath = listingId ? `/account/messages/new?listing_id=${encodeURIComponent(listingId)}${exchangeIntent ? "&intent=exchange" : ""}` : "/account/messages/new";
  await requireSession(nextPath);

  let listingTitle: string | null = null;
  let listingAvailable = false;
  let exchange = false;
  if (listingId) {
    try {
      const result = await serverApi.listing(listingId);
      if (result.listing.status === "active") {
        listingTitle = result.listing.title;
        listingAvailable = true;
        exchange = exchangeIntent && result.listing.exchange === true;
      }
    } catch { /* Keep the unavailable state separate from the empty inbox. */ }
  }

  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Новое сообщение</h1><p>Начните переписку по объявлению.</p></header>
    <AccountNav current="/account/messages" />
    {listingAvailable && listingTitle ? <ConversationStartForm listingId={listingId} listingTitle={listingTitle} exchange={exchange} /> : <div className="empty-state conversation-start-error">
      <h2>{listingId ? "Объявление недоступно для переписки" : "Выберите объявление"}</h2>
      <p className="muted">{listingId ? "Откройте активное объявление продавца и попробуйте начать переписку оттуда." : "Чтобы написать продавцу, сначала откройте объявление."}</p>
      <Link className="button button-secondary" href={listingId ? "/cars" : "/account/messages"}>{listingId ? "Найти автомобили" : "К перепискам"}</Link>
    </div>}
  </div>;
}
