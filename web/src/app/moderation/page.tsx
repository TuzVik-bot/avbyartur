import Link from "next/link";
import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { CompanyModerationActions, ListingModerationActions, ReportResolution } from "@/components/moderation-actions";
import { ModerationListingPreview } from "@/components/moderation-listing-preview";
import { ModerationRiskSignals, type ModerationRiskSignal } from "@/components/moderation-risk-signals";
import { serverApi } from "@/lib/server-api";
import { requireSession } from "@/lib/server";
import { companyStatusBadge, listingStatusBadge, reportStatusBadge } from "@/lib/status-presentation";
import type { ListResponse, Listing } from "@/lib/types";

type Queue = "listings" | "active" | "companies" | "reports";
type ModerationQueueListing = Listing & { risk_signals?: ModerationRiskSignal[] };
type SearchParams = { queue?: string | string[]; page?: string | string[] };
export const metadata: Metadata = { title: "Модерация" };

function parsePage(value: string | undefined) {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : null;
}

function pageUrl(queue: Queue, page: number) {
  const params = new URLSearchParams({ queue });
  if (page > 1) params.set("page", String(page));
  return `/moderation?${params.toString()}`;
}

export default async function ModerationPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const session = await requireSession("/moderation");
  const params = await searchParams;
  const requested = Array.isArray(params.queue) ? params.queue[0] : params.queue;
  const queue: Queue = requested === "active" || requested === "companies" || requested === "reports" ? requested : "listings";
  const rawPage = Array.isArray(params.page) ? params.page[0] : params.page;
  const parsedPage = parsePage(rawPage);
  const requestedPage = parsedPage ?? 1;
  const showingListings = queue === "listings" || queue === "active";
  if (session.user.role === "user") return <div className="page-width"><div className="page-head"><h1>Нет доступа к модерации</h1><p>Эта очередь доступна только модераторам пилота.</p></div><Link className="button button-secondary" href="/account">В кабинет</Link></div>;
  if (showingListings && rawPage !== undefined && parsedPage === null) redirect(pageUrl(queue, 1));

  const emptyListings: ListResponse<Listing> = { items: [] };
  const [listingsResult, companiesResult, reportsResult] = await Promise.allSettled([
    showingListings ? serverApi.moderationListings(queue === "active" ? "active" : "pending_review", requestedPage) : Promise.resolve(emptyListings),
    queue === "companies" ? serverApi.moderationCompanies() : Promise.resolve({ items: [] }),
    queue === "reports" ? serverApi.moderationReports() : Promise.resolve({ items: [] })
  ]);
  const listingsData = listingsResult.status === "fulfilled" ? listingsResult.value : null;
  const pageCountValue = listingsData?.pagination?.pages;
  const pageCount = pageCountValue === undefined
    ? Math.max(1, requestedPage)
    : Number.isSafeInteger(pageCountValue) && pageCountValue > 0 ? pageCountValue : 1;
  if (showingListings && listingsData?.pagination && requestedPage > pageCount) redirect(pageUrl(queue, pageCount));
  const page = Math.min(requestedPage, pageCount);
  const failed = showingListings ? listingsResult.status === "rejected" : queue === "companies" ? companiesResult.status === "rejected" : reportsResult.status === "rejected";

  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Рабочая очередь</p><h1>Модерация</h1><p>Решения применяются к текущей версии объявления.</p></header>
      <AccountNav current="/moderation" />
      <nav className="account-nav queue-nav" aria-label="Очередь модерации">
        <Link href="/moderation?queue=listings" aria-current={queue === "listings" ? "page" : undefined}>На проверке</Link>
        <Link href="/moderation?queue=active" aria-current={queue === "active" ? "page" : undefined}>Активные</Link>
        <Link href="/moderation?queue=companies" aria-current={queue === "companies" ? "page" : undefined}>Компании</Link>
        <Link href="/moderation?queue=reports" aria-current={queue === "reports" ? "page" : undefined}>Жалобы</Link>
      </nav>
      {failed && <p className="notice" role="alert">Не удалось загрузить эту очередь. Проверьте доступ и повторите попытку.</p>}
      {showingListings && listingsResult.status === "fulfilled" && <div className="account-list">{listingsResult.value.items.length ? listingsResult.value.items.map((listing) => {
        const moderatedListing = listing as ModerationQueueListing;
        const status = listingStatusBadge(listing.status);
        return <article className="account-list-item moderation-item" key={listing.id}><div><h2>{listing.title}</h2><p className="muted">{listing.seller.name} · ревизия {listing.revision} · <span className={status.className}>{status.label}</span></p><ModerationRiskSignals signals={moderatedListing.risk_signals} /><ModerationListingPreview listing={listing} /></div><ListingModerationActions listing={listing} /></article>;
      }) : <div className="empty-state"><h2>{queue === "active" ? "Активных объявлений нет" : "Очередь объявлений пуста"}</h2></div>}</div>}
      {showingListings && listingsData?.pagination && pageCount > 1 && <nav className="pagination" aria-label="Страницы очереди">
        {page > 1 && <Link className="button button-secondary button-small" href={pageUrl(queue, page - 1)}>Назад</Link>}
        <span>Страница {page} из {pageCount}</span>
        {page < pageCount && <Link className="button button-secondary button-small" href={pageUrl(queue, page + 1)}>Дальше</Link>}
      </nav>}
      {queue === "companies" && companiesResult.status === "fulfilled" && <div className="account-list">{companiesResult.value.items.length ? companiesResult.value.items.map((company) => { const status = companyStatusBadge(company.status); return <article className="account-list-item moderation-item" key={company.id}><div><h2>{company.name}</h2><p className="muted">УНП {company.unp} · {company.address} · {company.phone}</p><span className={status.className}>{status.label}</span></div><CompanyModerationActions company={company} /></article>; }) : <div className="empty-state"><h2>Заявок компаний нет</h2></div>}</div>}
      {queue === "reports" && reportsResult.status === "fulfilled" && <div className="account-list">{reportsResult.value.items.length ? reportsResult.value.items.map((report) => { const status = reportStatusBadge(report.status); return <article className="account-list-item moderation-item" key={report.id}><div><h2>Жалоба: {report.category}</h2><p>{report.comment || "Комментарий не добавлен."}</p><p className="muted">Объявление: {report.listing_id || "не указано"} · <span className={status.className}>{status.label}</span></p></div><ReportResolution report={report} /></article>; }) : <div className="empty-state"><h2>Нерассмотренных жалоб нет</h2></div>}</div>}
    </div>
  );
}
