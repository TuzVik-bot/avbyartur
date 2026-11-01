import Link from "next/link";
import { serverApi } from "@/lib/server-api";
import { DEFAULT_LOCALE } from "@/lib/i18n";
import { localeMetadata } from "@/lib/site-config";
import { buildOpenGraph } from "@/lib/seo";
import type { CatalogItem } from "@/lib/types";
import type { ListingCategoryCode } from "@/lib/listing-subcategories";
import styles from "./page.module.css";

export const metadata = {
  title: "Каталог марок транспорта",
  description: "Каталог марок транспорта на Авторынке: автомобили, мототехника и водный транспорт.",
  alternates: localeMetadata("/makes", DEFAULT_LOCALE),
  openGraph: buildOpenGraph({
    title: "Каталог марок транспорта",
    description: "Каталог марок транспорта на Авторынке: автомобили, мототехника и водный транспорт.",
    path: "/makes",
  }),
};

const makeCategories: { code: ListingCategoryCode; name: string }[] = [
  { code: "cars", name: "Автомобили" },
  { code: "trucks", name: "Грузовые автомобили" },
  { code: "buses", name: "Автобусы" },
  { code: "motorcycles", name: "Мотоциклы и ATV" },
  { code: "special_equipment", name: "Спецтехника" },
  { code: "agricultural_equipment", name: "Сельхозтехника" },
  { code: "trailers", name: "Прицепы" },
  { code: "watercraft", name: "Водный транспорт" },
];

export default async function MakesPage({ searchParams }: { searchParams?: Promise<{ category_code?: string | string[] }> } = {}) {
  const params = searchParams ? await searchParams : {};
  const requestedCategory = Array.isArray(params.category_code) ? params.category_code[0] : params.category_code;
  const categoryCode = makeCategories.find(({ code }) => code === requestedCategory)?.code || "cars";
  const selectedCategory = makeCategories.find(({ code }) => code === categoryCode)!;
  let makes: CatalogItem[] = [];
  let failed = false;
  try {
    const catalog = await serverApi.catalog("makes", { category_code: categoryCode });
    makes = [...catalog.items].sort((a, b) => a.name.localeCompare(b.name, "ru", { numeric: true }));
  } catch {
    failed = true;
  }

  return (
    <section className="page-width section" aria-labelledby="makes-heading">
      <Link className="text-link" href="/">На главную</Link>
      <div className="section-heading"><h1 id="makes-heading">Марки: {selectedCategory.name.toLocaleLowerCase("ru")}</h1></div>
      <nav aria-label="Категория транспорта" className={styles.categories}>
        {makeCategories.map(({ code, name }) => <Link key={code} aria-current={code === categoryCode ? "page" : undefined} href={code === "cars" ? "/makes" : `/makes?category_code=${code}`}>{name}</Link>)}
      </nav>
      <p className="muted">Выберите марку, чтобы посмотреть объявления в категории «{selectedCategory.name.toLocaleLowerCase("ru")}».</p>
      {failed ? (
        <div className="notice" role="status">
          <p>Справочник марок временно недоступен.</p>
          <Link className="text-link" href={categoryCode === "cars" ? "/makes" : `/makes?category_code=${categoryCode}`}>Попробовать снова</Link>
        </div>
      ) : makes.length ? (
        <ul className={styles.list} aria-label={`Марки: ${selectedCategory.name}`}>
          {makes.map((make) => <li key={make.id}><Link href={categoryCode === "cars" ? `/cars/${encodeURIComponent(make.slug)}` : `/cars?${new URLSearchParams({ category_code: categoryCode, make_id: make.id })}`}>{make.name}</Link></li>)}
        </ul>
      ) : <p className="muted" role="status">В справочнике пока нет марок.</p>}
    </section>
  );
}
