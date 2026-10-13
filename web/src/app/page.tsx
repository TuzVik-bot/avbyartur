import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ListingCard } from "@/components/listing-card";
import { HomeSearch } from "@/components/home-search";
import { getSavedListingIds, serverApi } from "@/lib/server-api";
import { DEFAULT_LOCALE, getMessage } from "@/lib/i18n";
import { localeMetadata } from "@/lib/site-config";
import type { CatalogItem, ListingSummary, ListResponse } from "@/lib/types";
import styles from "./home.module.css";

export const metadata = {
  title: getMessage("home.metadataTitle", DEFAULT_LOCALE),
  alternates: localeMetadata("/", DEFAULT_LOCALE)
};

export default async function HomePage() {
  const [listingResult, makeResult, regionResult, bodyTypeResult, savedListingIdsResult] = await Promise.allSettled([
    serverApi.listings({ page_size: "9", sort: "newest" }),
    serverApi.catalog("makes"),
    serverApi.regions(),
    serverApi.catalog("body-types"),
    getSavedListingIds()
  ]);
  const listings: ListResponse<ListingSummary> | null = listingResult.status === "fulfilled" ? listingResult.value : null;
  const makes: CatalogItem[] = makeResult.status === "fulfilled" ? makeResult.value.items : [];
  const regions: CatalogItem[] = regionResult.status === "fulfilled" ? regionResult.value.items : [];
  const bodyTypes: CatalogItem[] = bodyTypeResult.status === "fulfilled" ? bodyTypeResult.value.items : [];
  const savedIds = new Set(savedListingIdsResult.status === "fulfilled" ? savedListingIdsResult.value : []);
  const failed = listingResult.status === "rejected";
  const makesFailed = makeResult.status === "rejected";
  return (
    <div className={styles.home}>
      <section className={`page-width ${styles.intro}`} aria-labelledby="home-heading">
        <div className={styles.searchColumn}>
          <p className={styles.eyebrow}>Автомобили · Беларусь</p>
          <div className={styles.heading}>
            <div><h1 id="home-heading">Купить автомобиль</h1><p>Найдите тот самый. Начните с того, что важно вам.</p></div>
            <Link className={styles.catalogLink} href="/cars">Весь каталог <ArrowRight size={16} aria-hidden="true" /></Link>
          </div>
          <HomeSearch makes={makes} regions={regions} bodyTypes={bodyTypes} className={styles.search} />
          {makesFailed && <p className="notice" role="status">Справочник марок временно недоступен. Поиск по названию автомобиля остаётся доступен.</p>}
          {!!makes.length && <nav className={styles.makes} aria-label="Быстрый поиск по марке"><span>По маркам</span><div>{makes.slice(0, 12).map((make) => <Link key={make.id} href={`/cars/${encodeURIComponent(make.slug)}`}>{make.name}</Link>)}<Link className={styles.allMakes} href="/cars">Все марки <ArrowRight size={14} aria-hidden="true" /></Link></div></nav>}
        </div>
        <aside className={styles.adSide} aria-label="Место под рекламу">
          <span className={styles.adLabel}>Рекламное место</span>
          <div className={styles.adContent}><span className={styles.adSymbol} aria-hidden="true">↗</span><h2>Здесь может быть<br /> ваша реклама</h2><p>Место для вашего бренда<br />на главной странице</p><Link href="/partner">О сотрудничестве <ArrowRight size={16} aria-hidden="true" /></Link></div>
          <span className={styles.adFootnote}>Баннер партнёра</span>
        </aside>
      </section>
      <div className="page-width"><aside className={styles.adWide} aria-label="Горизонтальное место под рекламу"><div><span className={styles.adLabel}>Рекламное место</span><p>Ваш бренд на пути к новому автомобилю</p></div><Link href="/partner">О сотрудничестве <ArrowRight size={16} aria-hidden="true" /></Link></aside></div>
      <section className={`page-width section ${styles.listings}`}>
        <div className="section-heading"><h2>Новые объявления</h2><Link className="text-link" href="/cars">Все предложения <ArrowRight size={16} /></Link></div>
        {failed && <p className="notice" role="status">Каталог временно недоступен. Обновите страницу чуть позже.</p>}
        {listings?.items.length ? <div className="listing-grid">{listings.items.map((listing) => <ListingCard key={listing.id} listing={listing} saved={savedIds.has(listing.id)} />)}</div> : (
          <div className="empty-state">
            <h2>{failed ? "Не удалось загрузить предложения" : "Пока нет опубликованных автомобилей"}</h2>
            <p className="muted">Когда продавцы добавят объявления, они появятся здесь.</p>
            <Link className="button button-secondary" href="/cars">Перейти к поиску</Link>
          </div>
        )}
      </section>
    </div>
  );
}
