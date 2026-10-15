import { CategoryNavigation } from "@/components/category-navigation";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ListingCard } from "@/components/listing-card";
import { HomeSearch } from "@/components/home-search";
import { getSavedListingIds, serverApi } from "@/lib/server-api";
import { DEFAULT_LOCALE, getMessage } from "@/lib/i18n";
import { localeMetadata } from "@/lib/site-config";
import type { CatalogItem, CompanySummary, ListingSummary, ListResponse } from "@/lib/types";
import styles from "./home.module.css";

export const metadata = {
  title: getMessage("home.metadataTitle", DEFAULT_LOCALE),
  alternates: localeMetadata("/", DEFAULT_LOCALE)
};

export default async function HomePage() {
  const [listingResult, makeResult, regionResult, bodyTypeResult, savedListingIdsResult, dealerResult, statsResult] = await Promise.allSettled([
    serverApi.listings({ page_size: "9", sort: "newest" }),
    serverApi.catalog("makes"),
    serverApi.regions(),
    serverApi.catalog("body-types"),
    getSavedListingIds(),
    serverApi.dealers(1),
    serverApi.publicStats()
  ]);
  const listings: (ListResponse<ListingSummary> & { fx?: unknown }) | null = listingResult.status === "fulfilled" ? listingResult.value : null;
  const makes: CatalogItem[] = makeResult.status === "fulfilled" ? makeResult.value.items : [];
  const regions: CatalogItem[] = regionResult.status === "fulfilled" ? regionResult.value.items : [];
  const bodyTypes: CatalogItem[] = bodyTypeResult.status === "fulfilled" ? bodyTypeResult.value.items : [];
  const savedIds = new Set(savedListingIdsResult.status === "fulfilled" ? savedListingIdsResult.value : []);
  const failed = listingResult.status === "rejected";
  const dealers: ListResponse<CompanySummary> | null = dealerResult.status === "fulfilled" ? dealerResult.value : null;
  const dealersFailed = dealerResult.status === "rejected";
  const marketStats = statsResult.status === "fulfilled" ? statsResult.value : null;
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
          <HomeSearch makes={makes} regions={regions} bodyTypes={bodyTypes} className={styles.search} priceOperationsAvailable={Boolean(listings?.fx)} />
          {makesFailed && <p className="notice" role="status">Справочник марок временно недоступен. Поиск по названию автомобиля остаётся доступен.</p>}
          {!!makes.length && <nav className={styles.makes} aria-label="Быстрый поиск по марке"><span>По маркам</span><div>{makes.slice(0, 12).map((make) => <Link key={make.id} href={`/cars/${encodeURIComponent(make.slug)}`}>{make.name}</Link>)}<Link className={styles.allMakes} href="/makes">Все марки <ArrowRight size={14} aria-hidden="true" /></Link></div></nav>}
        </div>
        <aside className={styles.adSide} aria-label="Место под рекламу">
          <span className={styles.adLabel}>Рекламное место</span>
          <div className={styles.adContent}><span className={styles.adSymbol} aria-hidden="true">↗</span><h2>Здесь может быть<br /> ваша реклама</h2><p>Место для вашего бренда<br />на главной странице</p><Link href="/partner">О сотрудничестве <ArrowRight size={16} aria-hidden="true" /></Link></div>
          <span className={styles.adFootnote}>Баннер партнёра</span>
        </aside>
      </section>
      <section className={`page-width ${styles.marketStats}`} aria-label="Состояние авторынка">
        {marketStats ? <>
          <p>Активных объявлений: <strong>{marketStats.active_listings.toLocaleString("ru-RU")}</strong></p>
          <p>Допущенные компании: <strong>{marketStats.approved_companies.toLocaleString("ru-RU")}</strong></p>
          <p className={styles.moderationNote}>Модерация проверяет сведения перед публикацией.</p>
        </> : <p className="notice" role="status">Статистика временно недоступна.</p>}
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
      <CategoryNavigation />
      <section className="page-width section home-discovery" aria-labelledby="home-discovery-heading">
        <div className="section-heading"><div><p className="eyebrow">Подборки</p><h2 id="home-discovery-heading">Выберите подходящий автомобиль</h2></div><Link className="text-link" href="/cars">Открыть каталог <ArrowRight size={16} /></Link></div>
        <div className="home-collection-grid">
          <Link className="home-collection-card home-collection-new" href="/cars?condition=new"><span className="collection-kicker">Каталог</span><strong>Новые автомобили</strong><span>Объявления с состоянием «Новый»</span><ArrowRight size={19} aria-hidden="true" /></Link>
          <Link className="home-collection-card home-collection-used" href="/cars?condition=used"><span className="collection-kicker">Каталог</span><strong>Автомобили с пробегом</strong><span>Объявления с состоянием «С пробегом»</span><ArrowRight size={19} aria-hidden="true" /></Link>
        </div>
        <div className="home-makes">
          <div className="section-heading"><h3>Марки автомобилей</h3><Link className="text-link" href="/makes">Все марки <ArrowRight size={15} /></Link></div>
          {makes.length ? <ul>{makes.slice(0, 12).map((make) => <li key={make.id}><Link href={`/cars?${new URLSearchParams({ make_id: make.id })}`}>{make.name}</Link></li>)}</ul> : <p className="muted">Справочник марок временно недоступен.</p>}
        </div>
      </section>

      <section className="home-seller-section" aria-labelledby="home-seller-heading">
        <div className="page-width home-seller-grid">
          <div className="home-seller-copy">
            <p className="eyebrow">Для продавцов</p>
            <h2 id="home-seller-heading">Подача объявления — в личном кабинете</h2>
            <p>Заполните карточку автомобиля, сохраните черновик и отправьте объявление на проверку.</p>
            <ul className="home-benefit-list">
              <li><span aria-hidden="true">✓</span> Черновик можно продолжить позже</li>
              <li><span aria-hidden="true">✓</span> Перед публикацией объявление проходит проверку</li>
              <li><span aria-hidden="true">✓</span> Контакты не показываются в публичной выдаче</li>
            </ul>
            <Link className="button button-primary" href="/sell">Подать объявление <ArrowRight size={16} /></Link>
          </div>
          <div className="home-seller-visual"><Image src="/design/sell.webp" alt="Ключи от автомобиля на фоне серебристого седана" width={1200} height={800} sizes="(max-width: 800px) 100vw, 50vw" /></div>
        </div>
      </section>

      <section className="page-width section home-steps" aria-labelledby="home-steps-heading">
        <div className="section-heading"><div><p className="eyebrow">Подача объявления</p><h2 id="home-steps-heading">Три шага до отправки на проверку</h2></div></div>
        <ol className="home-step-list">
          <li><span>01</span><h3>Заполните карточку</h3><p>Укажите марку, характеристики, стоимость и местоположение автомобиля.</p></li>
          <li><span>02</span><h3>Добавьте фотографии</h3><p>Загрузите подходящие снимки и при необходимости вернитесь к черновику позже.</p></li>
          <li><span>03</span><h3>Отправьте на проверку</h3><p>Проверьте введённые сведения и отправьте объявление модератору пилота.</p></li>
        </ol>
      </section>

      <section className="page-width section home-dealers" aria-labelledby="home-dealers-heading">
        <div className="section-heading"><div><p className="eyebrow">Компании</p><h2 id="home-dealers-heading">Автокомпании и дилеры</h2></div><Link className="text-link" href="/dealers">Все компании <ArrowRight size={16} /></Link></div>
        {dealersFailed ? <p className="notice" role="status">Список компаний временно недоступен.</p> : dealers?.items.length ? <div className="home-dealer-grid">{dealers.items.slice(0, 3).map((dealer) => <article className="home-dealer-card" key={dealer.id}><h3><Link href={`/dealers/${encodeURIComponent(dealer.slug)}`}>{dealer.name}</Link></h3><p>{dealer.address || "Адрес не указан"}</p>{dealer.status === "approved" && <span className="verified-state">Допущена к пилоту</span>}<Link className="text-link" href={`/dealers/${encodeURIComponent(dealer.slug)}`}>Открыть страницу <ArrowRight size={15} /></Link></article>)}</div> : <div className="home-dealers-empty"><p className="muted">Компании и их объявления доступны в каталоге после допуска к пилоту.</p><Link className="button button-secondary" href="/dealers">О компаниях</Link></div>}
      </section>

      <section className="page-width section home-customs" aria-labelledby="home-customs-heading">
        <div className="home-customs-card">
          <div><p className="eyebrow">Справочная информация</p><h2 id="home-customs-heading">Таможенный калькулятор</h2><p>Расчёт доступен только при наличии подтверждённых правил и официальных курсов.</p><Link className="button button-secondary" href="/customs-calculator">Открыть калькулятор <ArrowRight size={16} /></Link></div>
          <Image src="/design/customs.webp" alt="Модель автомобиля, маршрут и документы" width={1200} height={800} sizes="(max-width: 800px) 100vw, 45vw" />
        </div>
      </section>
    </div>
  );
}
