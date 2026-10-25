import type { Metadata } from "next";
import { CurrencyConverter } from "@/components/currency-converter";
import { serverApi } from "@/lib/server-api";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Пересчёт цен автомобилей между BYN, USD и EUR по официальному курсу Нацбанка Беларуси с историей курсов.";
export const metadata: Metadata = {
  title: "Конвертер валют НБРБ",
  description,
  alternates: { canonical: siteUrl("/currency-converter") },
  openGraph: buildOpenGraph({ title: "Конвертер валют НБРБ", description, path: "/currency-converter" }),
};

export default async function CurrencyConverterPage() {
  const [ratesResult, historyResult] = await Promise.allSettled([
    serverApi.customsRates(),
    serverApi.customsRateHistory("USD", "90d")
  ]);
  const rates = ratesResult.status === "fulfilled" ? ratesResult.value : null;
  const history = historyResult.status === "fulfilled" ? historyResult.value : null;

  return (
    <div className="page-width">
      <header className="page-head">
        <p className="eyebrow">Сервисы</p>
        <h1>Конвертер валют</h1>
        <p>Пересчёт по официальным курсам Национального банка Республики Беларусь.</p>
      </header>
      {rates
        ? <CurrencyConverter rates={rates} initialHistory={history} />
        : <p className="notice" role="status">Курсы НБРБ сейчас недоступны. Попробуйте открыть страницу позже.</p>}
    </div>
  );
}
