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
function daysBetween(start: string, end: string) {
  return (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000;
}

export default async function ListingAnalyticsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireSession("/account/listings/analytics");
  const params = await searchParams;
  const listingId = first(params.listing_id)?.trim() || "";
  const dateFromInput = first(params.date_from)?.trim() || "";
  const dateToInput = first(params.date_to)?.trim() || "";
  const dateFrom = safeDate(dateFromInput);
  const dateTo = safeDate(dateToInput);
  const invalidDate = Boolean((dateFromInput && !dateFrom) || (dateToInput && !dateTo));
  const reversedPeriod = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  const periodTooWide = Boolean(dateFrom && dateTo && daysBetween(dateFrom, dateTo) > 366);
  const periodError = invalidDate || reversedPeriod || periodTooWide
    ? "Проверьте даты периода: укажите существующие даты от начала к концу, не более 367 дней включительно."
    : null;
  const validListingId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(listingId);
  let analytics: Awaited<ReturnType<typeof serverApi.listingAnalytics>> | null = null;
  let failed = false;
  if (validListingId && !periodError) {
    try { analytics = await serverApi.listingAnalytics(listingId, { dateFrom, dateTo }); }
    catch { failed = true; }
  }
  const formDateFrom = dateFrom || analytics?.period.start || "";
  const formDateTo = dateTo || analytics?.period.end || "";
  const retryParams = new URLSearchParams({ listing_id: listingId });
  if (dateFrom) retryParams.set("date_from", dateFrom);
  if (dateTo) retryParams.set("date_to", dateTo);
  const retryHref = `/account/listings/analytics?${retryParams.toString()}`;
  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Статистика объявления</h1><p>События объявления за выбранный период.</p></header>
    <AccountNav current="/account/listings" />
    {!listingId ? <p className="notice" role="alert">Выберите объявление в разделе «Мои объявления».</p> : !validListingId ? <p className="notice" role="alert">Укажите корректное объявление, чтобы посмотреть статистику.</p> : <>
      <form className="dealer-analytics-period" method="get" aria-label="Период статистики">
        <input type="hidden" name="listing_id" value={listingId} />
        <label className="field"><span>С</span><input type="date" name="date_from" defaultValue={formDateFrom} aria-describedby="listing-analytics-period-help" /></label>
        <label className="field"><span>По</span><input type="date" name="date_to" defaultValue={formDateTo} aria-describedby="listing-analytics-period-help" /></label>
        <button className="button button-secondary button-small" type="submit">Применить</button>
      </form>
      <p id="listing-analytics-period-help" className="muted">Границы периода включены; максимальная длина — 367 календарных дней.</p>
      {periodError ? <p className="notice" role="alert">{periodError}</p> : failed ? <div className="notice" role="alert"><p>Не удалось загрузить статистику. Проверьте доступ к объявлению и повторите попытку.</p><Link href={retryHref}>Повторить загрузку</Link></div> : !analytics ? <p className="notice" role="alert">Статистика пока недоступна.</p> : <>
        <p className="muted">Период: {analytics.period.start} — {analytics.period.end}</p>
        <div className="dealer-analytics-totals" aria-label="Показатели объявления">
          <article><span>Просмотры</span><strong>{analytics.views}</strong><small>Количество запросов страницы; это не число уникальных людей.</small></article>
          <article><span>Показы телефона</span><strong>{analytics.contact_reveals}</strong><small>Раскрытие номера не означает звонок или продажу.</small></article>
          <article><span>Диалоги</span><strong>{analytics.chats}</strong><small>Чаты не подтверждают сделку.</small></article>
        </div>
      </>}
    </>}
  </div>;
}
