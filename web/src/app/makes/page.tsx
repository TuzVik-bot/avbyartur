import Link from "next/link";
import { serverApi } from "@/lib/server-api";
import { DEFAULT_LOCALE } from "@/lib/i18n";
import { localeMetadata } from "@/lib/site-config";
import type { CatalogItem } from "@/lib/types";
import styles from "./page.module.css";

export const metadata = {
  title: "Все марки автомобилей",
  alternates: localeMetadata("/makes", DEFAULT_LOCALE)
};

export default async function MakesPage() {
  let makes: CatalogItem[] = [];
  let failed = false;
  try {
    const catalog = await serverApi.catalog("makes");
    makes = [...catalog.items].sort((a, b) => a.name.localeCompare(b.name, "ru", { numeric: true }));
  } catch {
    failed = true;
  }

  return (
    <section className="page-width section" aria-labelledby="makes-heading">
      <Link className="text-link" href="/">На главную</Link>
      <div className="section-heading"><h1 id="makes-heading">Все марки автомобилей</h1></div>
      <p className="muted">Выберите марку, чтобы посмотреть её объявления.</p>
      {failed ? (
        <div className="notice" role="status">
          <p>Справочник марок временно недоступен.</p>
          <Link className="text-link" href="/makes">Попробовать снова</Link>
        </div>
      ) : makes.length ? (
        <ul className={styles.list} aria-label="Марки автомобилей">
          {makes.map((make) => <li key={make.id}><Link href={`/cars/${encodeURIComponent(make.slug)}`}>{make.name}</Link></li>)}
        </ul>
      ) : <p className="muted" role="status">В справочнике пока нет марок.</p>}
    </section>
  );
}
