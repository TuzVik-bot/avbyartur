import Link from "next/link";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { ListingCard } from "@/components/listing-card";
import { SearchFilters } from "@/components/search-filters";
import { SearchSort } from "@/components/search-sort";
import { activeSearchKeys, searchUrl } from "@/lib/search-state";
import type { CatalogCity, CatalogItem, CatalogModification, ListingSearch, ListingSummary, ListResponse } from "@/lib/types";

const readableFilter: Record<string, string> = {
  q: "Поиск", make_id: "Марка", model_id: "Модель", generation_id: "Поколение", body_variant_id: "Вариант кузова", modification_id: "Модификация", price_min: "Цена от", price_max: "Цена до",
  year_min: "Год от", year_max: "Год до", mileage_min: "Пробег от", mileage_max: "Пробег до", fuel: "Топливо", transmission: "Коробка",
  drive: "Привод", body_type: "Кузов", damaged: "Повреждения", parts_only: "На запчасти", condition: "Состояние", region_id: "Область",
  city_id: "Город", seller_type: "Продавец", color: "Цвет", customs_status: "Таможня", technical_condition: "Техническое состояние", body_condition: "Состояние кузова",
  exchange: "Обмен", bargaining: "Торг", credit: "Кредит", leasing: "Лизинг", equipment: "Комплектация", district: "Район", call_hours: "Время звонков",
  has_vin: "VIN", has_photos: "Фотографии", engine_volume_min: "Объём двигателя от", engine_volume_max: "Объём двигателя до", power_min: "Мощность от", power_max: "Мощность до"
};

const optionLabels: Record<string, string> = {
  black: "Чёрный", white: "Белый", gray: "Серый", silver: "Серебристый", red: "Красный", blue: "Синий", green: "Зелёный", yellow: "Жёлтый", brown: "Коричневый", beige: "Бежевый", orange: "Оранжевый", purple: "Фиолетовый", other: "Другой",
  cleared_rb: "Оформлен в РБ", eaeu_import: "Ввезён из ЕАЭС", uncleared: "Не растаможен", unknown: "Не указан",
  good: "Исправен", needs_repair: "Требует ремонта", non_operational: "Не на ходу", minor_damage: "Есть небольшие повреждения", significant_damage: "Есть серьёзные повреждения", repaired: "Был в ремонте",
  abs: "ABS", esp: "ESP", airbags: "Подушки безопасности", air_conditioning: "Кондиционер", climate_control: "Климат-контроль", heated_seats: "Подогрев сидений", cruise_control: "Круиз-контроль", parking_sensors: "Парктроники", rear_camera: "Камера заднего вида", leather_seats: "Кожаный салон", carplay: "Apple CarPlay", android_auto: "Android Auto"
};

function filterValue(key: string, value: string, catalog: CatalogItem[]) {
  const item = catalog.find((entry) => entry.id === value || entry.slug === value);
  if (item) return item.name;
  if (key === "generation_id") return "Поколение выбрано";
  if (key === "body_variant_id") return "Вариант кузова выбран";
  if (key === "modification_id") return "Комплектация выбрана";
  if (key === "damaged") return "Есть повреждения";
  if (key === "parts_only") return "На запчасти";
  if (key === "seller_type") return value === "company" ? "Компания" : "Частное лицо";
  if (key === "condition") return value === "new" ? "Новый" : "С пробегом";
  if (["exchange", "bargaining", "credit", "leasing", "has_vin", "has_photos"].includes(key)) return value === "true" ? "Да" : "Нет";
  if (key === "equipment") return value.split(",").map((part) => optionLabels[part] || part).join(", ");
  if (optionLabels[value]) return optionLabels[value];
  if (key.endsWith("_min")) return `от ${value}`;
  if (key.endsWith("_max")) return `до ${value}`;
  return value;
}

export function SearchResults({ search, data, title, makes, models, generations, regions, cities, bodyTypes, bodyVariants = [], modifications = [], savedListingIds = [], failed = false, catalogsFailed = false, priceOperationsAvailable = true }: {
  search: ListingSearch;
  data: ListResponse<ListingSummary> | null;
  title: string;
  makes: CatalogItem[];
  models: CatalogItem[];
  generations?: CatalogItem[];
  regions: CatalogItem[];
  cities: CatalogCity[];
  bodyTypes: CatalogItem[];
  bodyVariants?: CatalogItem[];
  modifications?: CatalogModification[];
  savedListingIds?: string[];
  failed?: boolean;
  catalogsFailed?: boolean;
  priceOperationsAvailable?: boolean;
}) {
  const catalog = [...makes, ...models, ...(generations || []), ...regions, ...cities, ...bodyTypes, ...bodyVariants, ...modifications];
  const entries = data?.items || [];
  const page = Number(search.page || 1);
  const pages = data?.pagination?.pages || 1;
  const total = data?.pagination?.total ?? entries.length;
  const savedIds = new Set(savedListingIds);

  return (
    <>
      <div className="page-head"><h1>{title}</h1><p>{total ? `${total.toLocaleString("ru-BY")} объявлений` : "Объявления Беларуси"}</p></div>
      {failed && <p className="notice" role="status">Каталог временно недоступен. Обновите страницу чуть позже.</p>}
      {catalogsFailed && <p className="notice" role="status">Часть справочников фильтров временно недоступна. Объявления остаются доступны; повторите загрузку страницы позже.</p>}
      {!priceOperationsAvailable && <p className="notice" role="status">Фильтрация и сортировка по цене временно недоступны: нет подтверждённого курса НБРБ за последние 72 часа. Цены показаны в исходной валюте.</p>}
      <div className="results-layout">
        <SearchFilters search={search} makes={makes} initialModels={models} initialGenerations={generations} initialModifications={modifications} regions={regions} initialCities={cities} bodyTypes={bodyTypes} priceOperationsAvailable={priceOperationsAvailable} />
        <section aria-label="Результаты поиска">
          {activeSearchKeys.filter((key) => search[key]).length > 0 && (
            <div className="active-filters" aria-label="Выбранные фильтры">
              {activeSearchKeys.filter((key) => search[key]).map((key) => (
                <Link className="filter-chip" key={key} href={searchUrl(search, { [key]: undefined })}>
                  {readableFilter[key]}: {filterValue(key, Array.isArray(search[key]) ? search[key].join(",") : String(search[key]), catalog)} <X size={13} aria-hidden="true" />
                </Link>
              ))}
              <Link className="filter-chip" href="/cars">Сбросить все</Link>
            </div>
          )}
          <div className="results-toolbar">
            <strong>{total ? `${total.toLocaleString("ru-BY")} предложений` : "Подходящие предложения"}</strong>
            <SearchSort search={search} priceOperationsAvailable={priceOperationsAvailable} />
          </div>
          {entries.length ? <div className="listing-stack">{entries.map((listing) => <ListingCard key={listing.id} listing={listing} variant="row" saved={savedIds.has(listing.id)} />)}</div> : (
            <div className="empty-state">
              <h2>{failed ? "Не удалось загрузить объявления" : "По этим условиям объявлений пока нет"}</h2>
              <p className="muted">{failed ? "Проверьте соединение с каталогом." : "Измените или сбросьте часть фильтров, чтобы увидеть другие варианты."}</p>
              <Link className="button button-secondary" href="/cars">Сбросить фильтры</Link>
            </div>
          )}
          {pages > 1 && <nav className="pagination" aria-label="Страницы выдачи">
            {page > 1 && <Link className="button button-secondary button-small" href={searchUrl(search, { page: String(page - 1) })}><ChevronLeft size={16} /> Назад</Link>}
            <span>Страница {page} из {pages}</span>
            {page < pages && <Link className="button button-secondary button-small" href={searchUrl(search, { page: String(page + 1) })}>Дальше <ChevronRight size={16} /></Link>}
          </nav>}
        </section>
      </div>
    </>
  );
}
