"use client";

import Link from "next/link";
import { useState } from "react";
import type { CatalogItem } from "@/lib/types";

const COUNTRIES: Record<string, string[]> = {
  Германия: ["audi", "bmw", "mercedes-benz", "mercedes", "volkswagen", "opel", "porsche", "smart", "maybach", "alpina", "borgward", "trabant", "wartburg", "man"],
  Франция: ["renault", "peugeot", "citroen", "ds", "alpine", "bugatti", "simca", "talbot", "matra"],
  Япония: ["toyota", "lexus", "nissan", "infiniti", "mazda", "honda", "acura", "mitsubishi", "subaru", "suzuki", "daihatsu", "isuzu", "datsun", "scion", "mitsuoka"],
  США: ["ford", "chevrolet", "buick", "cadillac", "chrysler", "dodge", "jeep", "gmc", "lincoln", "tesla", "hummer", "pontiac", "plymouth", "oldsmobile", "ram", "saturn", "mercury", "fisker", "rivian", "lucid"],
  Корея: ["hyundai", "kia", "genesis", "ssangyong", "kgm", "daewoo"],
  Китай: ["geely", "belgee", "chery", "changan", "haval", "byd", "zeekr", "exeed", "omoda", "jaecoo", "jac", "faw", "gac", "great-wall", "dongfeng", "lifan", "brilliance", "baic", "foton", "nio", "xpeng", "tank", "wey", "lynk-co", "voyah", "li-auto", "aito", "avatr", "jetour", "jetta", "mg", "roewe", "hongqi", "zotye", "ora", "wuling", "baw", "jmc", "maxus", "haima", "saic", "tenet", "kaiyi", "xiaomi"],
  Швеция: ["volvo", "saab", "koenigsegg", "polestar"],
  Россия: ["lada", "lada-vaz", "vaz", "uaz", "gaz", "moskvich", "izh", "aurus", "zil", "kamaz"],
  Чехия: ["skoda", "tatra"],
  Великобритания: ["land-rover", "jaguar", "mini", "bentley", "rolls-royce", "aston-martin", "mclaren", "lotus", "rover", "morgan", "vauxhall"],
  Италия: ["fiat", "alfa-romeo", "ferrari", "lamborghini", "maserati", "lancia", "abarth", "iveco", "pagani"],
  Испания: ["seat", "cupra"],
  Румыния: ["dacia"],
  Украина: ["zaz", "bogdan"],
  Индия: ["tata", "mahindra"]
};
const COUNTRY_ORDER = ["Германия", "Франция", "Япония", "США", "Корея", "Китай", "Швеция", "Россия", "Чехия", "Великобритания", "Италия", "Испания", "Румыния", "Украина", "Индия"];
const OTHER = "Другие";
const norm = (value: string) => value.toLowerCase().replace(/š/g, "s").replace(/[^a-z0-9а-я]+/g, "-").replace(/^-|-$/g, "");
const countryKeys = (make: CatalogItem) => [make.slug, make.name, ...(make.aliases ?? [])].map(norm);
const inCountry = (make: CatalogItem, country: string) => countryKeys(make).some((key) => COUNTRIES[country]?.includes(key));
const hasCountry = (make: CatalogItem) => COUNTRY_ORDER.some((country) => inCountry(make, country));
const POPULAR_LIMIT = 30;

const byName = (a: CatalogItem, b: CatalogItem) => a.name.localeCompare(b.name, "ru", { sensitivity: "base" });

function MakeList({ makes }: { makes: CatalogItem[] }) {
  return (
    <ul className="makes-list">
      {makes.map((make) => (
        <li key={make.id}>
          <Link href={`/cars/${encodeURIComponent(make.slug)}`}>{make.name}</Link>
          {make.listing_count ? <span className="makes-count">{make.listing_count}</span> : null}
        </li>
      ))}
    </ul>
  );
}

export function MakesDirectory({ makes }: { makes: CatalogItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const [country, setCountry] = useState<string | null>(null);
  if (!makes.length) return null;
  const popular = [...makes].sort((a, b) => (b.listing_count ?? 0) - (a.listing_count ?? 0)).slice(0, POPULAR_LIMIT).sort(byName);
  const countries = [...COUNTRY_ORDER.filter((name) => makes.some((make) => inCountry(make, name))), ...(makes.some((make) => !hasCountry(make)) ? [OTHER] : [])];
  const visible = [...makes].filter((make) => !country || (country === OTHER ? !hasCountry(make) : inCountry(make, country))).sort(byName);
  return (
    <section className="page-width section makes-directory" aria-labelledby="makes-heading">
      <h2 id="makes-heading">Авто с пробегом по маркам</h2>
      {expanded && (
        <div className="makes-countries" role="group" aria-label="Страна производителя">
          <button type="button" className={country === null ? "is-active" : undefined} aria-pressed={country === null} onClick={() => setCountry(null)}>Все</button>
          {countries.map((name) => <button key={name} type="button" className={country === name ? "is-active" : undefined} aria-pressed={country === name} onClick={() => setCountry(name)}>{name}</button>)}
        </div>
      )}
      <MakeList makes={expanded ? visible : popular} />
      {!expanded && makes.length > popular.length && <button type="button" className="makes-toggle" onClick={() => setExpanded(true)}>Все марки</button>}
      {expanded && <button type="button" className="makes-toggle" onClick={() => { setExpanded(false); setCountry(null); }}>Свернуть</button>}
    </section>
  );
}
