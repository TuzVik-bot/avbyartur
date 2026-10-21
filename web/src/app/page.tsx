import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Building2, Calculator, CarFront, Check, FileText, Repeat2, ScanLine } from "lucide-react";
import { ListingCard } from "@/components/listing-card";
import { HomeSearch } from "@/components/home-search";
import { getSavedListingIds, serverApi } from "@/lib/server-api";
import { advertisementSections } from "@/lib/advertisement-sections";
import { DEFAULT_LOCALE, getMessage } from "@/lib/i18n";
import { localeMetadata } from "@/lib/site-config";
import type { CatalogItem, CompanySummary, ListingSummary, ListResponse } from "@/lib/types";
import styles from "./home.module.css";

export const metadata = {
  title: getMessage("home.metadataTitle", DEFAULT_LOCALE),
  alternates: localeMetadata("/", DEFAULT_LOCALE)
};

const tools = [
  { href: "/customs-calculator", title: "Таможенный калькулятор", description: "Пошлина, сборы и льготы", icon: Calculator },
  { href: "/currency-converter", title: "Конвертер валют", description: "Пересчёт по официальным курсам", icon: Repeat2 },
  { href: "/sale-contract", title: "Договор купли-продажи", description: "Образец для ознакомления", icon: FileText },
  { href: "/vin-check", title: "Проверка по VIN", description: "Информация о проверке истории", icon: ScanLine }
];

export default async function HomePage() {
  const [listingResult, makeResult, regionResult, bodyTypeResult, savedListingIdsResult, dealerResult, statsResult] = await Promise.allSettled([
    serverApi.listings({ page_size: "8", sort: "newest" }),
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
  const marketStats = statsResult.status === "fulfilled" ? statsResult.value : null;
  return (
    <div className={styles.home}>
      <section className={`page-width ${styles.intro}`} aria-labelledby="home-heading">
        <div className={styles.heading}>
          <div><p className={styles.eyebrow}>Авторынок Беларуси</p><h1 id="home-heading">Купить автомобиль</h1><p className={styles.lead}>Найдите тот самый. Начните с того, что важно вам.</p></div>
          <Link className={styles.catalogLink} href="/cars">Весь каталог <ArrowRight size={17} aria-hidden="true" /></Link>
        </div>
        <div className={styles.searchPanel}>
          <HomeSearch makes={makes} regions={regions} bodyTypes={bodyTypes} className={styles.search} priceOperationsAvailable={Boolean(listings?.fx)} />
        </div>
        {makeResult.status === "rejected" && <p className="notice" role="status">Справочник марок временно недоступен. Поиск по названию автомобиля остаётся доступен.</p>}
        <nav className={styles.makes} aria-label="Быстрый поиск по марке">
          <div className={styles.makeHeading}><h2>Марки автомобилей</h2><Link href="/makes">Все марки <ArrowRight size={14} aria-hidden="true" /></Link></div>
          {makes.length ? <ul>{makes.slice(0, 12).map((make) => <li key={make.id}><Link href={`/cars/${encodeURIComponent(make.slug)}`}>{make.name}</Link></li>)}</ul> : <p className="muted">Справочник марок временно недоступен.</p>}
        </nav>
        {marketStats && <div className={styles.marketStats} aria-label="Состояние авторынка">
          <p>Активных объявлений <strong>{marketStats.active_listings.toLocaleString("ru-RU")}</strong></p>
          <p>Допущенные компании <strong>{marketStats.approved_companies.toLocaleString("ru-RU")}</strong></p>
          <p>Опубликованные отзывы <strong>{marketStats.published_reviews.toLocaleString("ru-RU")}</strong></p>
          <details className={styles.moderationNote}><summary>Как проверяются объявления</summary><p>Перед отправкой проверяются обязательные поля карточки, их согласованность и минимум обработанных фото. Модератору показываются подсказки о повторах и необычно низкой цене — это не автоматическое решение.</p></details>
        </div>}
      </section>

      <nav className={`page-width ${styles.categories}`} aria-label="Категории объявлений">
        <h2>Разделы каталога</h2>
        <ul>{advertisementSections.map(({ label, href }) => <li key={href}><Link href={href}>{label}<ArrowRight size={14} aria-hidden="true" /></Link></li>)}</ul>
      </nav>

      <section className={`page-width ${styles.section} ${styles.listings}`} aria-labelledby="home-listings-heading">
        <div className={styles.sectionHeading}><h2 id="home-listings-heading">Новые объявления</h2><Link className="text-link" href="/cars">Все предложения <ArrowRight size={16} aria-hidden="true" /></Link></div>
        {failed && <p className="notice" role="status">Каталог временно недоступен. Обновите страницу чуть позже.</p>}
        {listings?.items.length ? <div className={`listing-grid ${styles.listingGrid}`}>{listings.items.map((listing) => <ListingCard key={listing.id} listing={listing} saved={savedIds.has(listing.id)} />)}</div> : <div className={styles.emptyState}>
          <h3>{failed ? "Не удалось загрузить предложения" : "Пока нет опубликованных автомобилей"}</h3>
          <p className="muted">Когда продавцы добавят объявления, они появятся здесь.</p>
          <Link className="button button-secondary" href="/cars">Перейти к поиску</Link>
        </div>}
        {!!listings?.items.length && <div className={styles.listingFooter}><Link className="button button-secondary" href="/cars">Смотреть все объявления <ArrowRight size={16} aria-hidden="true" /></Link></div>}
        <div className={styles.collections} aria-label="Подборки автомобилей">
          <Link href="/cars?condition=new"><CarFront size={24} aria-hidden="true" /><div><strong>Новые автомобили</strong><span>Объявления с состоянием «Новый»</span></div><ArrowRight size={18} aria-hidden="true" /></Link>
          <Link href="/cars?condition=used"><CarFront size={24} aria-hidden="true" /><div><strong>Автомобили с пробегом</strong><span>Объявления с состоянием «С пробегом»</span></div><ArrowRight size={18} aria-hidden="true" /></Link>
        </div>
      </section>

      <section className={`page-width ${styles.section}`} aria-labelledby="home-seller-heading">
        <div className={styles.seller}>
          <div className={styles.sellerMain}>
            <div className={styles.sellerCopy}><p className={styles.eyebrow}>Для продавцов</p><h2 id="home-seller-heading">Подача объявления — в личном кабинете</h2><p>Заполните карточку автомобиля, сохраните черновик и отправьте объявление на проверку.</p>
              <ul className={styles.benefits}><li><Check size={16} aria-hidden="true" />Черновик можно продолжить позже</li><li><Check size={16} aria-hidden="true" />Перед публикацией объявление проходит проверку</li><li><Check size={16} aria-hidden="true" />Контакты не показываются в публичной выдаче</li></ul>
              <Link className="button button-primary" href="/sell">Подать объявление <ArrowRight size={16} aria-hidden="true" /></Link>
            </div>
            <Image className={styles.sellerImage} src="/vehicles/silver-wagon.png" alt="Серебристый автомобиль" width={1448} height={1086} sizes="(max-width: 600px) 100vw, 40vw" />
          </div>
          <ol className={styles.steps} aria-label="Три шага до отправки на проверку">
            <li><span>01</span><div><h3>Заполните карточку</h3><p>Марка, характеристики, цена и местоположение.</p></div></li>
            <li><span>02</span><div><h3>Добавьте фотографии</h3><p>Загрузите снимки и сохраните черновик.</p></div></li>
            <li><span>03</span><div><h3>Отправьте на проверку</h3><p>Проверьте сведения перед отправкой модератору.</p></div></li>
          </ol>
        </div>
      </section>

      <section className={`page-width ${styles.section}`} aria-labelledby="home-tools-heading">
        <div className={styles.sectionHeading}><h2 id="home-tools-heading">Полезно при покупке</h2><Link className="text-link" href="/useful-information">Вся информация <ArrowRight size={16} aria-hidden="true" /></Link></div>
        <div className={styles.resources}>
          <div className={styles.tools}>{tools.map(({ href, title, description, icon: Icon }) => <Link key={href} href={href}><span className={styles.toolIcon}><Icon size={22} aria-hidden="true" /></span><div><h3>{title}</h3><p>{description}</p></div><ArrowRight size={16} aria-hidden="true" /></Link>)}</div>
          <div className={styles.dealers}><Building2 size={24} aria-hidden="true" /><h3>Автокомпании и дилеры</h3>
            {dealerResult.status === "rejected" ? <p role="status">Список компаний временно недоступен.</p> : dealers?.items.length ? <ul>{dealers.items.slice(0, 3).map((dealer) => <li key={dealer.id}><Link href={`/dealers/${encodeURIComponent(dealer.slug)}`}>{dealer.name}<ArrowRight size={14} aria-hidden="true" /></Link></li>)}</ul> : <p>Компании и их объявления доступны в каталоге после допуска к пилоту.</p>}
            <Link className="text-link" href="/dealers">Все компании <ArrowRight size={16} aria-hidden="true" /></Link>
          </div>
        </div>
        <aside className={styles.partner} aria-label="Сотрудничество и реклама"><div><strong>Для вашего бизнеса</strong><p>Реклама и сотрудничество с Авторынком</p></div><Link href="/partner">О сотрудничестве <ArrowRight size={16} aria-hidden="true" /></Link></aside>
      </section>
    </div>
  );
}
