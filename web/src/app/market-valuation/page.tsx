import type { Metadata } from "next";
import { MarketValuation } from "@/components/market-valuation";
import { buildOpenGraph } from "@/lib/seo";
import { serverApi } from "@/lib/server-api";
import { siteUrl } from "@/lib/site-config";
import type { CatalogItem } from "@/lib/types";

const description = "Узнайте, сколько стоит ваш автомобиль: мгновенная оценка по актуальным объявлениям Авторынка — медиана и диапазон типичных цен для вашей модели, года и пробега.";
export const metadata: Metadata = {
  title: "Сколько стоит моя машина? Оценка по рынку",
  description,
  alternates: { canonical: siteUrl("/market-valuation") },
  openGraph: buildOpenGraph({ title: "Сколько стоит моя машина? Оценка по рынку", description, path: "/market-valuation" }),
};

export default async function MarketValuationPage() {
  const [makesResult, typesResult] = await Promise.allSettled([
    serverApi.catalog("makes"),
    serverApi.catalog("body-types"),
  ]);
  const makes: CatalogItem[] = makesResult.status === "fulfilled" ? makesResult.value.items : [];
  const bodyTypes: CatalogItem[] = typesResult.status === "fulfilled" ? typesResult.value.items : [];
  return <div>
    <header className="page-head"><p className="eyebrow">Авторынок.бел</p><h1>Сколько стоит моя машина?</h1><p>Оценка по активным объявлениям той же модели с похожим пробегом. Без регистрации — результат сразу на странице.</p></header>
    <MarketValuation makes={makes} bodyTypes={bodyTypes} catalogUnavailable={!makes.length || !bodyTypes.length} />
  </div>;
}
