import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Building2, Calculator, CarFront, Check, FileText, MapPin, Repeat2, ScanLine, SlidersHorizontal, UsersRound, Zap } from "lucide-react";
import { ListingCard } from "@/components/listing-card";
import { MachineIllustration } from "@/components/category-landing";
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

const buyerShortcuts = [
  { href: "/cars?category_code=cars&price_max=30000&currency=BYN", title: "До 30 000 BYN", icon: SlidersHorizontal },
  { href: "/cars?category_code=cars&fuel=electric", title: "Электромобили", icon: Zap },
  { href: "/cars/city/minsk", title: "В Минске", icon: MapPin },
  { href: "/useful-information#use-case-presets-title", title: "Семейный автомобиль", icon: UsersRound }
];

const featuredCategories = [
  { href: "/motorcycles", title: "Мототехника", caption: "Мотоциклы, скутеры и квадроциклы", art: "moto" },
  { href: "/special-equipment", title: "Спецтехника", caption: "Техника для строительства и работ", art: "special" },
  { href: "/agricultural-equipment", title: "Сельхозтехника", caption: "Машины для хозяйства и урожая", art: "agri" },
  { href: "/watercraft", title: "Водный транспорт", caption: "Лодки, моторы, гидроциклы", art: "water" },
  { href: "/tires-and-wheels", title: "Шины и диски", caption: "Шины и колёсные диски", art: "tires" }
];

const popularMakeNames = [
  "Audi", "BMW", "Buick", "Chevrolet", "Chrysler", "Citroen", "Dodge", "Fiat", "Ford", "Geely",
  "GMC", "Honda", "Hyundai", "Kia", "Lada", "Land Rover", "Lexus", "Mazda", "Mercedes-Benz", "Mitsubishi",
  "Nissan", "Opel", "Peugeot", "Renault", "Skoda", "Subaru", "Tesla", "Toyota", "Volkswagen", "Volvo"
];

function normalizeMake(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("ru").replace(/[\s_-]+/g, "").replace(/[^\p{L}\p{N}]/gu, "");
}

function getPopularMakes(makes: CatalogItem[]) {
  return popularMakeNames.map((name) => {
    const key = normalizeMake(name);
    const make = makes.find((item) => normalizeMake(item.name) === key || normalizeMake(item.slug) === key);
    return { name, href: make ? `/cars/${encodeURIComponent(make.slug)}` : `/cars?q=${encodeURIComponent(name)}` };
  });
}

export default async function HomePage() {
  const [listingResult, makeResult, regionResult, bodyTypeResult, savedListingIdsResult, dealerResult] = await Promise.allSettled([
    serverApi.listings({ page_size: "8", sort: "newest" }),
    serverApi.catalog("makes"),
    serverApi.regions(),
    serverApi.catalog("body-types"),
    getSavedListingIds(),
    serverApi.dealers(1)
  ]);
  const listings: (ListResponse<ListingSummary> & { fx?: unknown }) | null = listingResult.status === "fulfilled" ? listingResult.value : null;
  const makes: CatalogItem[] = makeResult.status === "fulfilled" ? makeResult.value.items : [];
  const popularMakes = getPopularMakes(makes);
  const regions: CatalogItem[] = regionResult.status === "fulfilled" ? regionResult.value.items : [];
  const bodyTypes: CatalogItem[] = bodyTypeResult.status === "fulfilled" ? bodyTypeResult.value.items : [];
  const savedIds = new Set(savedListingIdsResult.status === "fulfilled" ? savedListingIdsResult.value : []);
  const failed = listingResult.status === "rejected";
  const dealers: ListResponse<CompanySummary> | null = dealerResult.status === "fulfilled" ? dealerResult.value : null;
  return (
    <div className={styles.home}>
      <section className={`page-width ${styles.intro}`} aria-labelledby="home-heading">
        <div className={styles.heading}>
          <div><p className={styles.eyebrow}>Авторынок Беларуси</p><h1 id="home-heading">Найдите автомобиль по своим условиям</h1><p className={styles.lead}>Задайте бюджет, регион и важные параметры — поиск покажет опубликованные объявления.</p></div>
          <Link className={styles.catalogLink} href="/cars">Весь каталог <ArrowRight size={17} aria-hidden="true" /></Link>
        </div>
        <nav className={styles.quickScenarios} aria-label="Быстрые сценарии покупки">
          {buyerShortcuts.map(({ href, title, icon: Icon }) => <Link href={href} key={title}><Icon size={17} aria-hidden="true" />{title}</Link>)}
        </nav>
        <div className={styles.discoveryLayout}>
          <div className={styles.discoveryMain}>
            <div className={styles.searchPanel} id="home-search">
              <HomeSearch makes={makes} regions={regions} bodyTypes={bodyTypes} className={styles.search} priceOperationsAvailable={Boolean(listings?.fx)} />
            </div>
            {makeResult.status === "rejected" && <p className="notice" role="status">Справочник марок временно недоступен. Поиск по названию автомобиля остаётся доступен.</p>}
            <aside className={`${styles.adSlot} ${styles.wideAd}`} aria-label="Реклама">
              <span className={styles.adLabel}>Реклама</span>
              <div><strong>Место для вашего бренда</strong><p>Расскажите о предложении автомобилистам.</p></div>
              <Link href="/partner">Разместить рекламу <ArrowRight size={15} aria-hidden="true" /></Link>
            </aside>
            <nav className={styles.makes} aria-label="Быстрый поиск по марке">
              <div className={styles.makeHeading}><h2>Популярные марки</h2><Link href="/makes">Все марки <ArrowRight size={14} aria-hidden="true" /></Link></div>
              {popularMakes.length ? <ul>{popularMakes.map(({ name, href }) => <li key={name}><Link href={href}>{name}</Link></li>)}</ul> : <p className="muted">Справочник марок временно недоступен.</p>}
            </nav>
          </div>
          <aside className={`${styles.adSlot} ${styles.verticalAd}`} aria-label="Реклама">
            <span className={styles.adLabel}>Реклама</span>
            <div><strong>Продвижение для автомобильного бизнеса</strong><p>Расскажите о своей компании и предложении.</p></div>
            <Link href="/partner">Разместить рекламу <ArrowRight size={15} aria-hidden="true" /></Link>
          </aside>
        </div>
      </section>

      <nav className={`page-width ${styles.categories}`} aria-label="Категории объявлений">
        <h2>Разделы каталога</h2>
        <ul className={styles.featuredCategories}>{featuredCategories.map(({ href, title, caption, art }, index) => <li key={href}><Link href={href}><span className={styles.categoryArt}><MachineIllustration kind={art} index={index} /></span><span className={styles.categoryCopy}><strong>{title}</strong><small>{caption}</small></span><ArrowRight size={16} aria-hidden="true" /></Link></li>)}</ul>
        <div className={styles.otherCategories} aria-label="Другие разделы каталога">{advertisementSections.filter(({ href }) => !featuredCategories.some((category) => category.href === href)).map(({ label, href }) => <Link href={href} key={href}>{label}<ArrowRight size={13} aria-hidden="true" /></Link>)}</div>
      </nav>

      <section className={`page-width ${styles.section} ${styles.listings}`} aria-labelledby="home-listings-heading">
        <div className={styles.sectionHeading}><h2 id="home-listings-heading">Новые объявления</h2><Link className="text-link" href="/cars">Все предложения <ArrowRight size={16} aria-hidden="true" /></Link></div>
        {failed && <p className="notice" role="status">Каталог временно недоступен. Обновите страницу чуть позже.</p>}
        {listings?.items.length ? <div className={`listing-grid ${styles.listingGrid}`}>{listings.items.map((listing) => <ListingCard key={listing.id} listing={listing} saved={savedIds.has(listing.id)} />)}</div> : <div className={styles.emptyState}>
          <h3>{failed ? "Сейчас не удаётся загрузить объявления" : "Новых объявлений пока нет"}</h3>
          <p className="muted">{failed ? "Попробуйте открыть каталог позже: запрос не подтвердил, есть ли сейчас опубликованные предложения." : "В каталоге пока нет опубликованных предложений. Уточните условия поиска или выберите стартовую подборку."}</p>
          <div className={styles.emptyActions}>
            <Link className="button button-secondary" href="/cars">Открыть каталог</Link>
            <Link className="text-link" href="/useful-information#use-case-presets-title">Подборки по задаче <ArrowRight size={16} aria-hidden="true" /></Link>
          </div>
        </div>}
        {!!listings?.items.length && <div className={styles.listingFooter}><Link className="button button-secondary" href="/cars">Смотреть все объявления <ArrowRight size={16} aria-hidden="true" /></Link></div>}
        <div className={styles.collections} aria-label="Подборки автомобилей">
          <Link href="/cars?condition=new"><CarFront size={24} aria-hidden="true" /><div><strong>Новые автомобили</strong><span>Объявления с состоянием «Новый»</span></div><ArrowRight size={18} aria-hidden="true" /></Link>
          <Link href="/cars?condition=used"><CarFront size={24} aria-hidden="true" /><div><strong>Автомобили с пробегом</strong><span>Объявления с состоянием «С пробегом»</span></div><ArrowRight size={18} aria-hidden="true" /></Link>
        </div>
      </section>

      <section className={`page-width ${styles.section}`} aria-labelledby="home-partners-heading">
        <div className={styles.sectionHeading}><h2 id="home-partners-heading">Реклама</h2><Link className="text-link" href="/partner">Разместить рекламу <ArrowRight size={16} aria-hidden="true" /></Link></div>
        <div className={styles.partnerCards}>
          <article><span className={styles.adLabel}>Реклама</span><Link className={styles.partnerCategory} href="/tires-and-wheels">Шины и диски</Link><span>Место для предложения вашего бренда</span><Link className={styles.cardAction} href="/partner">Разместить рекламу <ArrowRight size={14} aria-hidden="true" /></Link></article>
          <article><span className={styles.adLabel}>Реклама</span><strong>Страхование автомобиля</strong><span>Место для предложения вашей компании</span><Link className={styles.cardAction} href="/partner">Разместить рекламу <ArrowRight size={14} aria-hidden="true" /></Link></article>
          <article><span className={styles.adLabel}>Реклама</span><Link className={styles.partnerCategory} href="/services">Автосервис и обслуживание</Link><span>Место для предложения вашего бренда</span><Link className={styles.cardAction} href="/partner">Разместить рекламу <ArrowRight size={14} aria-hidden="true" /></Link></article>
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
