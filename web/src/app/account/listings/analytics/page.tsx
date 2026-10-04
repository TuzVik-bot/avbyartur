import type { Metadata } from "next";
import Link from "next/link";
import { AccountNav } from "@/components/account-nav";
import { requireSession } from "@/lib/server";
import { serverApi } from "@/lib/server-api";

export const metadata: Metadata = { title: "Статистика объявления" };
type SearchParams = { listing_id?: string | string[]; date_from?: string | string[]; date_to?: string | string[] };
function first(value: string | string[] | undefined) { return Array.isArray(value) ? value[0] : value; }
function safeDate(value: string | undefined) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value ? value : undefined;
}

export default async function ListingAnalyticsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireSession("/account/listings/analytics");
  const params = await searchParams;
  const listingId = first(params.listing_id)?.trim() || "";
  const dateFrom = safeDate(first(params.date_from));
  const dateTo = safeDate(first(params.date_to));
  let analytics: Awaited<ReturnType<typeof serverApi.listingAnalytics>> | null = null;
  let failed = false;
  if (/^[0-9a-f-]{36}$/i.test(listingId)) {
    try { analytics = await serverApi.listingAnalytics(listingId, { dateFrom, dateTo }); }
    catch { failed = true; }
  }
  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Статистика объявления</h1><p>Показы, обращения и диалоги за выбранный период.</p></header>
    <AccountNav current="/account/listings" />
    {!listingId ? <p className="notice" role="alert">Выберите объявление в разделе «Мои объявления».</p> : failed ? <div className="notice" role="alert"><p>Не удалось загрузить статистику. Убедитесь, что объявление принадлежит вашему аккаунту или компании.</p><Link href="/account/listings">К моим объявлениям</Link></div> : !analytics ? <p className="notice" role="alert">Укажите корректное объявление, чтобы посмотреть статистику.</p> : <>
      <form className="dealer-analytics-period" method="get" aria-label="Период статистики"><input type="hidden" name="listing_id" value={listingId} /><label className="field"><span>С</span><input type="date" name="date_from" defaultValue={dateFrom || analytics.period.start} /></label><label className="field"><span>По</span><input type="date" name="date_to" defaultValue={dateTo || analytics.period.end} /></label><button className="button button-secondary button-small" type="submit">Применить</button></form>
      <p className="muted">Период: {analytics.period.start} — {analytics.period.end}</p>
      <div className="dealer-analytics-totals" aria-label="Показатели объявления"><article><span>Просмотры</span><strong>{analytics.views}</strong></article><article><span>Показы телефона</span><strong>{analytics.contact_reveals}</strong></article><article><span>Диалоги</span><strong>{analytics.chats}</strong></article></div>
    </>}
  </div>;
}
