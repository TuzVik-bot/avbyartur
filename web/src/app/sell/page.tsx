import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Camera, CheckCircle2, ClipboardCheck, MessageCircle, ShieldCheck } from "lucide-react";
import { notFound } from "next/navigation";
import { SellForm } from "@/components/sell-form";
import styles from "./sell.module.css";
import { ApiClientError } from "@/lib/api";
import { getSessionServer, serverApi } from "@/lib/server-api";
import type { CatalogItem, Company, Listing, ListingPhoto } from "@/lib/types";
import { getListingSubcategories, isListingSubcategory, type ListingCategoryCode } from "@/lib/listing-subcategories";

type SearchParams = { listing?: string | string[]; category_code?: string | string[]; subcategory?: string | string[] };
export const metadata: Metadata = { title: "Подать объявление", robots: { index: false, follow: false } };

const sellableCategories: readonly ListingCategoryCode[] = ["cars", "motorcycles", "special_equipment", "agricultural_equipment", "watercraft", "tires", "wheels"];
const categoryLabels: Partial<Record<ListingCategoryCode, string>> = {
  cars: "автомобиля", motorcycles: "мототехники", special_equipment: "спецтехники",
  agricultural_equipment: "сельхозтехники", watercraft: "водного транспорта", tires: "шин", wheels: "колёсных дисков"
};

function SellLanding({ nextPath, categoryCode, subcategory }: { nextPath: string; categoryCode: ListingCategoryCode; subcategory: string }) {
  const loginHref = `/login?${new URLSearchParams({ next: nextPath })}`;
  const vehicle = categoryCode === "cars";
  const categoryLabel = categoryLabels[categoryCode] || "техники";
  const selectedSubcategory = getListingSubcategories(categoryCode).find((item) => item.value === subcategory)?.label;

  return (
    <div className={styles.page}>
      <section className={styles.intro} aria-labelledby="sell-heading">
        <div className={styles.introCopy}>
          <p className={styles.eyebrow}>Для продавцов</p>
          <h1 id="sell-heading">{vehicle ? "От черновика до объявления в каталоге" : `Новое объявление ${categoryLabel}`}</h1>
          <p className={styles.lead}>{vehicle ? "Заполните сведения об автомобиле, добавьте фотографии и отправьте карточку на проверку." : `Укажите характеристики ${categoryLabel}, добавьте фотографии и отправьте карточку на проверку.`} После одобрения объявление появится в каталоге, а покупатели смогут связаться с вами.</p>
          {selectedSubcategory && <p className={styles.accountNote}>Вы выбрали: {selectedSubcategory}. Выбор сохранится после входа.</p>}
          <div className={styles.actions}>
            <Link className="button button-primary" href={loginHref}>Войти и начать <ArrowRight size={17} aria-hidden="true" /></Link>
            <a className={styles.stepsLink} href="#sell-steps">Посмотреть этапы</a>
          </div>
          <p className={styles.accountNote}>Для подачи нужен аккаунт. После входа вы вернётесь к форме объявления.</p>
        </div>
      </section>

      <section className={styles.stepsSection} id="sell-steps" aria-labelledby="sell-steps-heading">
        <div className={styles.sectionHeading}>
          <div><p className={styles.eyebrow}>Путь продавца</p><h2 id="sell-steps-heading">Три этапа до публикации</h2></div>
          <p>Черновик можно продолжить позже в личном кабинете.</p>
        </div>
        <ol className={styles.steps}>
          <li><span className={styles.stepNumber}>01</span><h3>Опишите {vehicle ? "автомобиль" : "технику"}</h3><p>Укажите категорию, характеристики, цену и расположение. Неизвестные марку или модель можно вписать вручную.</p></li>
          <li><span className={styles.stepNumber}>02</span><h3>Добавьте фотографии</h3><p>Загрузите снимки автомобиля и выберите главное фото. Форма подскажет допустимые форматы и количество.</p></li>
          <li><span className={styles.stepNumber}>03</span><h3>Проверьте и отправьте</h3><p>Посмотрите карточку целиком и отправьте её модератору. В каталоге она появится после одобрения.</p></li>
        </ol>
      </section>

      <section className={styles.trustStrip} aria-label="Как устроена подача объявления">
        <div className={styles.trustItem}><ShieldCheck size={21} aria-hidden="true" /><p><strong>Вы выбираете способ связи</strong><span>Можно оставить только переписку или указать телефон.</span></p></div>
        <div className={styles.trustItem}><ClipboardCheck size={21} aria-hidden="true" /><p><strong>Проверка перед публикацией</strong><span>Перед отправкой форма покажет обязательные поля и фото.</span></p></div>
        <div className={styles.trustItem}><MessageCircle size={21} aria-hidden="true" /><p><strong>Объявление под контролем</strong><span>Статус, правки и статистика доступны в кабинете.</span></p></div>
      </section>

      {vehicle && <figure className={styles.vehicleFigure}>
        <Image src="/vehicles/silver-wagon.png" alt="Пример автомобиля для объявления" width={1448} height={1086} sizes="(max-width: 600px) calc(100vw - 48px), 480px" />
        <figcaption>После проверки карточка автомобиля появится в каталоге.</figcaption>
      </figure>}

      <section className={styles.photoGuide} aria-labelledby="sell-photo-heading">
        <div className={styles.photoIcon}><Camera size={22} aria-hidden="true" /></div>
        <div><h2 id="sell-photo-heading">Что подготовить для хорошей карточки</h2><p>{vehicle ? "Снимите автомобиль снаружи и внутри, добавьте приборную панель и важные детали. " : "Снимите технику с нескольких сторон и покажите основные узлы и комплектность. "}Подойдут JPEG, PNG и WebP; размер одного файла — до 20 MiB. Обязательное количество отображается в форме.</p></div>
        <div className={styles.photoChecklist}><span><CheckCircle2 size={16} aria-hidden="true" /> Честное описание</span><span><CheckCircle2 size={16} aria-hidden="true" /> Цена и расположение</span><span><CheckCircle2 size={16} aria-hidden="true" /> Обработанные фото</span></div>
      </section>

      <div className={styles.bottomAction}>
        <div><h2>Начните с черновика</h2><p>Сохраните данные и вернитесь к объявлению, когда будете готовы.</p></div>
        <Link className="button button-primary" href={loginHref}>Войти и начать <ArrowRight size={17} aria-hidden="true" /></Link>
      </div>
    </div>
  );
}

export default async function SellPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const id = Array.isArray(params.listing) ? params.listing[0] : params.listing;
  const requestedCategory = Array.isArray(params.category_code) ? params.category_code[0] : params.category_code;
  const categoryCode = sellableCategories.includes(requestedCategory as ListingCategoryCode) ? requestedCategory as ListingCategoryCode : "cars";
  const requestedSubcategory = Array.isArray(params.subcategory) ? params.subcategory[0] : params.subcategory;
  const subcategory = requestedSubcategory && isListingSubcategory(categoryCode, requestedSubcategory) ? requestedSubcategory : "";
  const session = await getSessionServer();
  const search = new URLSearchParams();
  if (id) search.set("listing", id);
  else if (categoryCode !== "cars") search.set("category_code", categoryCode);
  if (!id && subcategory) search.set("subcategory", subcategory);
  const requestedPath = search.size ? `/sell?${search.toString()}` : "/sell";
  if (!session) return <SellLanding nextPath={requestedPath} categoryCode={categoryCode} subcategory={subcategory} />;

  const [regionsResult, typesResult, companyResult, listingResult] = await Promise.allSettled([
    serverApi.regions(),
    serverApi.catalog("body-types"),
    serverApi.company(),
    id ? serverApi.listing(id) : Promise.resolve({ listing: null as Listing | null })
  ]);
  const regions: CatalogItem[] = regionsResult.status === "fulfilled" ? regionsResult.value.items : [];
  const bodyTypes: CatalogItem[] = typesResult.status === "fulfilled" ? typesResult.value.items : [];
  const company: Company | null = companyResult.status === "fulfilled" ? companyResult.value.company : null;
  const initialListing = id && listingResult.status === "fulfilled" ? listingResult.value.listing : null;
  if (id && listingResult.status === "rejected") {
    const status = listingResult.reason instanceof ApiClientError ? listingResult.reason.status : undefined;
    if (status === 404 || status === 410) notFound();
    return <div className="page-width"><p className="notice" role="alert">Не удалось загрузить объявление для редактирования. Повторите попытку позже.</p><Link className="button button-secondary" href={`/sell?listing=${encodeURIComponent(id)}`}>Повторить загрузку</Link></div>;
  }
  if (id && (!initialListing || ["sold", "archived", "blocked"].includes(initialListing.status))) notFound();
  const catalogCategoryCode = (initialListing as (Listing & { category_code?: ListingCategoryCode }) | null)?.category_code || categoryCode;
  const makesResult = await Promise.allSettled([serverApi.catalog("makes", { category_code: catalogCategoryCode })]).then(([result]) => result);
  const makes: CatalogItem[] = makesResult.status === "fulfilled" ? makesResult.value.items : [];
  const makeId = initialListing?.make?.id;
  const modelId = initialListing?.model?.id;
  const regionId = initialListing?.region?.id;
  const [modelsResult, generationsResult, citiesResult, photosResult] = await Promise.allSettled([
    makeId ? serverApi.catalog("models", { make_id: makeId, category_code: catalogCategoryCode }) : Promise.resolve({ items: [] as CatalogItem[] }),
    modelId ? serverApi.catalog("generations", { model_id: modelId }) : Promise.resolve({ items: [] as CatalogItem[] }),
    regionId ? serverApi.cities(regionId) : Promise.resolve({ items: [] as CatalogItem[] }),
    id ? serverApi.photos(id) : Promise.resolve({ items: [] as ListingPhoto[] })
  ]);
  const models = modelsResult.status === "fulfilled" ? modelsResult.value.items : initialListing?.model ? [initialListing.model] : [];
  const generations = generationsResult.status === "fulfilled" ? generationsResult.value.items : initialListing?.generation ? [initialListing.generation] : [];
  const cities = citiesResult.status === "fulfilled" ? citiesResult.value.items : initialListing?.city ? [initialListing.city] : [];
  if (id && photosResult.status === "rejected") return <div className="page-width"><p className="notice" role="alert">Не удалось загрузить фотографии объявления. Чтобы не потерять их при редактировании, повторите попытку позже.</p><Link className="button button-secondary" href={`/sell?listing=${encodeURIComponent(id)}`}>Повторить загрузку</Link></div>;
  const listingWithPhotos = initialListing && photosResult.status === "fulfilled" ? { ...initialListing, photos: photosResult.value.items } : initialListing;
  const makeCatalogUnavailable = makesResult.status === "rejected" || !makes.length;
  const regionCatalogUnavailable = regionsResult.status === "rejected" || !regions.length;
  const retryHref = id ? `/sell?listing=${encodeURIComponent(id)}` : requestedPath;
  return (
    <div className="page-width">
      {makeCatalogUnavailable && <p className="notice" role="status">Справочник марок недоступен. Марку можно указать вручную в форме. <Link href={retryHref}>Повторить загрузку</Link></p>}
      {regionCatalogUnavailable && <p className="notice" role="alert">Справочник областей недоступен. Объявление можно сохранить как черновик, но отправить его на проверку получится после загрузки справочника. <Link href={retryHref}>Повторить загрузку</Link></p>}
      {companyResult.status === "rejected" && <p className="notice" role="status">Не удалось загрузить профиль компании. Сейчас доступна подача от частного лица.</p>}
      {initialListing && (modelsResult.status === "rejected" || generationsResult.status === "rejected" || citiesResult.status === "rejected") && <p className="notice" role="status">Не удалось загрузить часть справочников редактирования. Текущие значения сохранены; повторите загрузку перед изменением каталожных данных.</p>}
      <SellForm initialListing={listingWithPhotos} initialCategoryCode={categoryCode} initialSubcategory={subcategory} makes={makes} models={models} generations={generations} bodyTypes={bodyTypes} regions={regions} cities={cities} company={company} />
    </div>
  );
}
