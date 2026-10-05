import Link from "next/link";
import Image from "next/image";
import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { ArrowRight, Building2 } from "lucide-react";
import { serverApi } from "@/lib/server-api";
import { SITE_ORIGIN } from "@/lib/site-config";
import type { CompanySummary, ListResponse } from "@/lib/types";

type SearchParams = { page?: string | string[] };

function parsePage(value: string | undefined) {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const page = Number(value);
  return Number.isSafeInteger(page) ? page : null;
}

function pageUrl(page: number) {
  const query = page > 1 ? `?${new URLSearchParams({ page: String(page) })}` : "";
  return `/dealers${query}`;
}

export async function generateMetadata({ searchParams }: { searchParams: Promise<SearchParams> }): Promise<Metadata> {
  const params = await searchParams;
  const requestedPage = Array.isArray(params.page) ? 1 : parsePage(params.page) ?? 1;
  return {
    title: "Автокомпании",
    alternates: { canonical: new URL(pageUrl(requestedPage), `${SITE_ORIGIN}/`).toString() },
  };
}

export default async function DealersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const requestedPage = Array.isArray(params.page) ? 1 : parsePage(params.page) ?? 1;
  let data: ListResponse<CompanySummary> | null = null;
  try { data = await serverApi.dealers(requestedPage); } catch { /* A readable empty state is shown below. */ }
  const pageCountValue = data?.pagination?.pages;
  const pageCount = typeof pageCountValue === "number" && Number.isSafeInteger(pageCountValue) && pageCountValue > 0 ? pageCountValue : 1;
  if (data?.pagination && requestedPage > pageCount) redirect(pageUrl(pageCount));
  const page = Math.min(data?.pagination?.page ?? requestedPage, pageCount);
  return (
    <div className="page-width">
      <header className="page-head page-head-with-visual"><div><p className="eyebrow">Автокомпании</p><h1>Компании и дилеры</h1><p>Автомобили от продавцов, допущенных к пилоту.</p></div><Image src="/design/dealers.webp" alt="Автомобили у светлого автосалона" width={1200} height={800} sizes="(max-width: 640px) 100vw, 42vw" /></header>
      {!data ? <div className="notice" role="alert"><p>Список компаний временно недоступен.</p><Link className="button button-secondary button-small" href="/dealers?retry=1">Повторить загрузку</Link></div> : data.items.length ? (
        <section className="dealer-directory" aria-labelledby="dealer-directory-title"><h2 id="dealer-directory-title" className="sr-only">Компании, допущенные к пилоту</h2><div className="dealer-grid">{data.items.map((company) => <article className="dealer-card" key={company.id}>
          <div className="dealer-topline"><h2><Link href={`/dealers/${encodeURIComponent(company.slug)}`}>{company.name}</Link></h2><Building2 size={19} aria-hidden="true" /></div>
          <p>{company.address || "Адрес не указан"}</p>
          {company.status === "approved" && <span className="verified-state" role="status">Допущена к пилоту</span>}
          <p>{company.listing_count === undefined ? "Автомобили компании" : `${company.listing_count} объявлений`}</p>
          <Link className="text-link" href={`/dealers/${encodeURIComponent(company.slug)}`}>Открыть страницу <ArrowRight size={15} /></Link>
        </article>)}</div></section>
      ) : <div className="empty-state"><h2>Компании пока не добавлены</h2><p className="muted">Когда компания получит допуск, её объявления появятся здесь.</p><Link className="button button-secondary" href="/login">Войти в кабинет</Link></div>}
      {data?.pagination && pageCount > 1 && <nav className="pagination" aria-label="Страницы компаний">
        {page > 1 && <Link className="button button-secondary button-small" href={pageUrl(page - 1)} aria-label={`Предыдущая страница, страница ${page - 1}`}>Назад</Link>}
        <span aria-current="page">Страница {page} из {pageCount}</span>
        {page < pageCount && <Link className="button button-secondary button-small" href={pageUrl(page + 1)} aria-label={`Следующая страница, страница ${page + 1}`}>Дальше</Link>}
      </nav>}
    </div>
  );
}
