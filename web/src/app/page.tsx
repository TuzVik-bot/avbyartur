import { CategoryNavigation } from "@/components/category-navigation";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Search } from "lucide-react";
import { ListingCard } from "@/components/listing-card";
import { getSavedListingIds, serverApi } from "@/lib/server-api";
import { DEFAULT_LOCALE, getMessage } from "@/lib/i18n";
import { localeMetadata } from "@/lib/site-config";
import type { CatalogItem, ListingSummary, ListResponse } from "@/lib/types";

export const metadata = {
  title: getMessage("home.metadataTitle", DEFAULT_LOCALE),
  alternates: localeMetadata("/", DEFAULT_LOCALE)
};

export default async function HomePage() {
  const [listingResult, makeResult, savedListingIdsResult] = await Promise.allSettled([
    serverApi.listings({ category_code: "cars", page_size: "9", sort: "newest" }),
    serverApi.catalog("makes"),
    getSavedListingIds()
  ]);
  const listings: ListResponse<ListingSummary> | null = listingResult.status === "fulfilled" ? listingResult.value : null;
  const makes: CatalogItem[] = makeResult.status === "fulfilled" ? makeResult.value.items : [];
  const savedIds = new Set(savedListingIdsResult.status === "fulfilled" ? savedListingIdsResult.value : []);
  const failed = listingResult.status === "rejected";
  const makesFailed = makeResult.status === "rejected";
  return (
    <>
      <section className="home-intro" aria-labelledby="home-heading">
        <div className="home-visual" aria-hidden="true"><Image src="/vehicles/silver-wagon.png" alt="" fill sizes="100vw" priority /></div>
        <div className="page-width home-content">
          <p className="eyebrow">Автомобили Беларуси</p>
          <h1 id="home-heading" className="home-title">Ваш автомобиль <span>уже ждёт вас</span></h1>
          <form className="search-strip" action="/cars" method="get" role="search">
            <label className="input-wrap"><Search size={19} aria-hidden="true" /><span className="sr-only">Марка, модель или запрос</span><input name="q" type="search" placeholder="Марка, модель или запрос" /></label>
            <label><span className="sr-only">Марка</span><select name="make_id" defaultValue=""><option value="">Все марки</option>{makes.map((make) => <option key={make.id} value={make.id}>{make.name}</option>)}</select></label>
            <button className="button home-search-button" type="submit"><Search size={17} /> Найти</button>
          </form>
          {makesFailed && <p className="notice" role="status">Справочник марок временно недоступен. Поиск по названию автомобиля остаётся доступен.</p>}
          <div className="quick-links"><span>Часто ищут:</span>{makes.slice(0, 7).map((make) => <Link key={make.id} href={`/cars/${encodeURIComponent(make.slug)}`}>{make.name}</Link>)}<Link className="text-link" href="/cars">Все автомобили <ArrowRight size={15} /></Link></div>
          <span className="home-image-note">Иллюстрация автомобиля</span>
        </div>
      </section>
      <CategoryNavigation />
      <section className="page-width section home-listings">
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
    </>
  );
}
