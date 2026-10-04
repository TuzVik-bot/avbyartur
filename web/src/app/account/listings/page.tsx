import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AccountNav } from "@/components/account-nav";
import { ListingStatusActions } from "@/components/listing-status-actions";
import { serverApi } from "@/lib/server-api";
import { formatMoney } from "@/lib/format";
import { requireSession } from "@/lib/server";
import type { ListResponse, Listing } from "@/lib/types";

export const metadata: Metadata = { title: "Мои объявления" };

const statusLabels: Record<string, string> = { draft: "Черновик", pending_review: "На проверке", rejected: "Нужно исправить", active: "Опубликовано", paused: "Снято с публикации", sold: "Продано", archived: "В архиве", blocked: "Заблокировано" };

type SearchParams = { page?: string | string[]; retry?: string | string[] };

function parsePage(value: string | undefined) {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : null;
}

function pageUrl(page: number) {
  const query = page > 1 ? `?${new URLSearchParams({ page: String(page) })}` : "";
  return `/account/listings${query}`;
}

function retryUrl(page: number, currentAttempt: string | string[] | undefined) {
  const attempt = Array.isArray(currentAttempt) ? currentAttempt[0] : currentAttempt;
  const query = new URLSearchParams();
  if (page > 1) query.set("page", String(page));
  query.set("retry", attempt === "1" ? "2" : "1");
  return `/account/listings?${query}`;
}

export default async function AccountListingsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireSession("/account/listings");
  const params = await searchParams;
  const requestedPage = Array.isArray(params.page) ? 1 : parsePage(params.page) ?? 1;
  let data: ListResponse<Listing> | null = null;
  try { data = await serverApi.meListings(requestedPage); } catch { /* A readable empty state is shown below. */ }
  const pageCountValue = data?.pagination?.pages;
  const pageCount = typeof pageCountValue === "number" && Number.isSafeInteger(pageCountValue) && pageCountValue > 0 ? pageCountValue : 1;
  if (data?.pagination && requestedPage > pageCount) redirect(pageUrl(pageCount));
  const page = Math.min(data?.pagination?.page ?? requestedPage, pageCount);
  const listings = data?.items ?? null;
  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Мои объявления</h1></header>
      <AccountNav current="/account/listings" />
      {listings === null ? <div className="notice" role="alert"><p>Не удалось загрузить объявления.</p><Link className="button button-secondary button-small" href={retryUrl(requestedPage, params.retry)}>Повторить загрузку</Link></div> : listings.length ? <div className="account-list">
        {listings.map((listing) => {
          const catalogTitle = [listing.make?.name, listing.model?.name, listing.year].filter(Boolean).join(" ");
          const title = listing.title?.trim() || catalogTitle || "Черновик без выбранного автомобиля";
          return <article className="account-list-item" key={listing.id}>
          <div><h2><Link href={`/sell?listing=${encodeURIComponent(listing.id)}`}>{title}</Link></h2><p className="muted">{formatMoney(listing.price)} · ревизия {listing.revision}</p><span className={`status-pill status-${listing.status}`}>{statusLabels[listing.status] || listing.status}</span>{listing.status === "rejected" && <><p className="inline-error">Исправьте замечания и отправьте объявление повторно.</p>{listing.moderation_reason?.trim() && <p className="inline-error" role="alert">Причина отклонения: {listing.moderation_reason}</p>}</>}<div className="form-actions listing-owner-links"><Link className="button button-secondary button-small" href={`/account/listings/analytics?listing_id=${encodeURIComponent(listing.id)}`}>Статистика</Link>{listing.status === "active" && <Link className="button button-secondary button-small" href={`/account/billing?listing_id=${encodeURIComponent(listing.id)}`}>Услуги продвижения</Link>}</div></div>
          <ListingStatusActions listing={listing} />
        </article>;
        })}
      </div> : <div className="empty-state"><h2>Объявлений пока нет</h2><p className="muted">Начните с черновика и добавьте фотографии автомобиля.</p><Link className="button button-primary" href="/sell">Создать объявление</Link></div>}
      {data?.pagination && pageCount > 1 && <nav className="pagination" aria-label="Страницы объявлений">
        {page > 1 && <Link className="button button-secondary button-small" href={pageUrl(page - 1)} aria-label={`Предыдущая страница, страница ${page - 1}`}>Назад</Link>}
        <span aria-current="page">Страница {page} из {pageCount}</span>
        {page < pageCount && <Link className="button button-secondary button-small" href={pageUrl(page + 1)} aria-label={`Следующая страница, страница ${page + 1}`}>Дальше</Link>}
      </nav>}
    </div>
  );
}
