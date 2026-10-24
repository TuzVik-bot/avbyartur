import Link from "next/link";
import Image from "next/image";
import { ArrowRight, Plus } from "lucide-react";
import { SearchRoute } from "@/components/search-route";
import { getListingSubcategories, type ListingCategoryCode } from "@/lib/listing-subcategories";
import styles from "./category-landing.module.css";

const configs: Record<string, { code: ListingCategoryCode; title: string; intro: string; art: string }> = {
  motorcycles: { code: "motorcycles", title: "Мототехника", intro: "Мотоциклы, скутеры и другая мототехника", art: "moto" },
  "special-equipment": { code: "special_equipment", title: "Спецтехника", intro: "Машины и оборудование для строительства и работ", art: "special" },
  "agricultural-equipment": { code: "agricultural_equipment", title: "Сельхозтехника", intro: "Техника для хозяйства, посева и уборки урожая", art: "agri" },
  watercraft: { code: "watercraft", title: "Водный транспорт", intro: "Лодки, моторы и техника для воды", art: "water" },
  tires: { code: "tires", title: "Шины и диски", intro: "Шины для разных видов транспорта и колёсные диски", art: "tires" }
};

const generatedArt = new Set([
  ...["concrete", "crane", "excavator", "forestry", "lift", "loader", "municipal", "other", "road-construction", "tow-truck"].map((name) => `special-equipment/${name}`),
  ...["livestock", "mini", "soil-preparation", "sowing", "post-harvest", "other-harvest", "grain-harvest", "forage-harvest", "vegetable-harvest", "tractor", "crop-care", "other"].map((name) => `agricultural-equipment/${name}`),
  ...["motorcycle", "scooter", "atv", "snowmobile"].map((name) => `motorcycles/${name}`),
  ...["jetski", "boat", "outboard-motor", "other-watercraft"].map((name) => `watercraft/${name}`),
  ...["passenger-tire", "truck-tire", "motorcycle-tire"].map((name) => `tires/${name}`),
  "wheels/alloy-wheel"
]);

const heroArt: Record<string, string> = {
  moto: "motorcycles/motorcycle",
  special: "special-equipment/excavator",
  agri: "agricultural-equipment/tractor",
  water: "watercraft/boat",
  tires: "tires/passenger-tire"
};

function artForSubcategory(categoryCode: ListingCategoryCode, value: string) {
  if (categoryCode === "wheels") return "wheels/alloy-wheel";
  if (categoryCode === "tires") return `tires/${value}-tire`;
  if (categoryCode === "watercraft") {
    const watercraft = { jet_ski: "jetski", boat: "boat", motor: "outboard-motor", other: "other-watercraft" };
    return `watercraft/${watercraft[value as keyof typeof watercraft] || value.replace(/_/g, "-")}`;
  }
  const folder = categoryCode === "special_equipment" ? "special-equipment" : categoryCode.replace(/_/g, "-");
  return `${folder}/${value.replace(/_/g, "-")}`;
}

export function MachineIllustration({
  kind,
  categoryCode,
  subcategory
}: {
  kind: string;
  index?: number;
  categoryCode?: ListingCategoryCode;
  subcategory?: string;
}) {
  const preferred = categoryCode && subcategory ? artForSubcategory(categoryCode, subcategory) : heroArt[kind];
  if (!preferred || !generatedArt.has(preferred)) return null;
  const isSubcategory = Boolean(categoryCode && subcategory);
  return <Image
    className={`${styles.machine} ${isSubcategory ? styles.categoryIcon : ""}`}
    src={`/category-art/${preferred}.webp`}
    width={512}
    height={512}
    sizes={isSubcategory ? "96px" : "(max-width: 600px) 42vw, 300px"}
    alt=""
    aria-hidden="true"
    unoptimized
  />;
}

export function CategoryLanding({ slug }: { slug: string }) {
  const config = configs[slug];
  if (!config) return null;
  const subcategories = getListingSubcategories(config.code);
  const isTires = config.code === "tires";
  return <main className={`page-width ${styles.page}`}>
    <header className={styles.hero}>
      <div><p className={styles.eyebrow}>Каталог объявлений</p><h1>{config.title}</h1><p className={styles.intro}>{config.intro}</p><Link className={styles.sell} href={`/sell?category_code=${config.code}`}><Plus size={17} aria-hidden="true" /> Подать объявление</Link></div>
      <div className={styles.heroArt}><MachineIllustration kind={config.art} /></div>
    </header>
    <section className={styles.subcategories} aria-labelledby="subcategory-title">
      <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Выберите направление</p><h2 id="subcategory-title">{isTires ? "Шины и колёса" : "Подкатегории"}</h2></div><Link href={`/cars?category_code=${config.code}`}>Все объявления <ArrowRight size={15} aria-hidden="true" /></Link></div>
      <ul>{subcategories.map(({ value, label }) => <li key={value}><Link href={`/cars?category_code=${config.code}&subcategory=${encodeURIComponent(value)}`}><span className={styles.illustration}><MachineIllustration kind={config.art} categoryCode={config.code} subcategory={value} /></span><span>{label}</span><ArrowRight size={17} aria-hidden="true" /></Link></li>)}
        {isTires && <li><Link href="/cars?category_code=wheels"><span className={styles.illustration}><MachineIllustration kind="tires" categoryCode="wheels" subcategory="alloy-wheel" /></span><span>Колёсные диски</span><ArrowRight size={17} aria-hidden="true" /></Link></li>}
      </ul>
    </section>
    <section className={styles.results}><SearchRouteWrapper categoryCode={config.code} title={config.title} /></section>
  </main>;
}

function SearchRouteWrapper({ categoryCode, title }: { categoryCode: ListingCategoryCode; title: string }) {
  return <SearchRoute search={{ category_code: categoryCode, page_size: "8", sort: "newest" }} title={title} />;
}
