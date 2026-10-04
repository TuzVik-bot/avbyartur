import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { redirect } from "next/navigation";
import Link from "next/link";
import { ListingCard } from "@/components/listing-card";
import { ApiClientError } from "@/lib/api";
import { getSavedListingIds, serverApi } from "@/lib/server-api";
import { SITE_ORIGIN } from "@/lib/site-config";

export const dynamic = "force-dynamic";

type SearchParams = { page?: string | string[] };
const businessDays = [
  { key: "mon", label: "Понедельник" }, { key: "tue", label: "Вторник" }, { key: "wed", label: "Среда" },
  { key: "thu", label: "Четверг" }, { key: "fri", label: "Пятница" }, { key: "sat", label: "Суббота" },
  { key: "sun", label: "Воскресенье" }
] as const;

function parsePage(value: string | undefined) {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : null;
}

function pageUrl(slug: string, page: number) {
  const query = page > 1 ? `?${new URLSearchParams({ page: String(page) })}` : "";
  return `/dealers/${encodeURIComponent(slug)}${query}`;
}

export async function generateMetadata({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<SearchParams> }): Promise<Metadata> {
  const { slug } = await params;
  const paramsQuery = await searchParams;
  const page = Array.isArray(paramsQuery.page) ? 1 : parsePage(paramsQuery.page) ?? 1;
  try {
    const result = await serverApi.dealer(slug);
    return {
      title: result.company.name,
      alternates: { canonical: new URL(pageUrl(slug, page), `${SITE_ORIGIN}/`).toString() },
    };
  } catch {
    return { title: "Компания" };
  }
}

export default async function DealerPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams?: Promise<SearchParams> }) {
  const { slug } = await params;
  const paramsQuery = searchParams ? await searchParams : {};
  const requestedPage = Array.isArray(paramsQuery.page) ? 1 : parsePage(paramsQuery.page) ?? 1;
  const savedListingIdsPromise = getSavedListingIds();
  let result;
  try { result = await serverApi.dealer(slug, requestedPage); } catch (error) {
    if (error instanceof ApiClientError && (error.status === 404 || error.status === 410)) notFound();
    return <div className="page-width"><div className="notice" role="alert"><p>Страница компании временно недоступна. Проверьте соединение и повторите попытку.</p><div className="company-links"><Link className="button button-secondary button-small" href={`/dealers/${encodeURIComponent(slug)}?retry=1`}>Повторить загрузку</Link><Link className="button button-secondary button-small" href="/dealers">К списку компаний</Link></div></div></div>;
  }
  const savedIds = new Set(await savedListingIdsPromise);
  const { company, listings } = result;
  const pageCountValue = listings.pagination?.pages;
  const pageCount = typeof pageCountValue === "number" && Number.isSafeInteger(pageCountValue) && pageCountValue > 0 ? pageCountValue : 1;
  if (listings.pagination && requestedPage > pageCount) redirect(pageUrl(slug, pageCount));
  const page = Math.min(listings.pagination?.page ?? requestedPage, pageCount);
  return (
    <div className="page-width">
      <nav className="breadcrumb" aria-label="Хлебные крошки"><Link href="/">Главная</Link><span aria-hidden="true">›</span><Link href="/dealers">Компании</Link><span aria-hidden="true">›</span><span>{company.name}</span></nav>
      <header className="page-head">
        <p className="eyebrow">Автокомпания</p>
        <h1>{company.name}</h1>
        {company.status === "approved" && <p className="verified-state" role="status">Допущена к пилоту</p>}
        <address className="dealer-address">{company.address || "Адрес не указан"}</address>
      </header>
      <section className="section" aria-labelledby="dealer-business-hours-title">
        <div className="section-heading"><h2 id="dealer-business-hours-title">Режим работы</h2></div>
        {company.business_hours ? <div>
          <table className="info-table company-hours-table">
            <thead><tr><th scope="col">День недели</th><th scope="col">Часы</th></tr></thead>
            <tbody>{businessDays.map(({ key, label }) => {
              const hours = company.business_hours![key];
              return <tr key={key}><th scope="row">{label}</th><td>{"closed" in hours ? "Закрыто" : `${hours.open}–${hours.close}`}</td></tr>;
            })}</tbody>
          </table>
        </div> : <p className="muted" role="status">Режим работы не указан.</p>}
      </section>
      <section className="section dealer-listings" aria-labelledby="dealer-listings-title">
        <div className="section-heading"><h2 id="dealer-listings-title">Автомобили компании</h2><span className="muted">{listings.pagination?.total ?? listings.items.length} объявлений</span></div>
        {listings.items.length ? <div className="listing-grid">{listings.items.map((listing) => <ListingCard key={listing.id} listing={listing} saved={savedIds.has(listing.id)} />)}</div> : <div className="empty-state"><h2>Активных автомобилей пока нет</h2><p className="muted">Новые объявления компании появятся после проверки.</p></div>}
        {!listings.items.length && <Link className="button button-secondary button-small dealer-empty-link" href="/cars?seller_type=company">Смотреть объявления компаний</Link>}
        {listings.pagination && pageCount > 1 && <nav className="pagination" aria-label="Страницы объявлений компании">
          {page > 1 && <Link className="button button-secondary button-small" href={pageUrl(slug, page - 1)} aria-label={`Предыдущая страница, страница ${page - 1}`}>Назад</Link>}
          <span aria-current="page">Страница {page} из {pageCount}</span>
          {page < pageCount && <Link className="button button-secondary button-small" href={pageUrl(slug, page + 1)} aria-label={`Следующая страница, страница ${page + 1}`}>Дальше</Link>}
        </nav>}
      </section>
    </div>
  );
}
