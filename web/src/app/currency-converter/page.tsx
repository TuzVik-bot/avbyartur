import type { Metadata } from "next";
import { CurrencyConverter } from "@/components/currency-converter";
import { serverApi } from "@/lib/server-api";

export const metadata: Metadata = { title: "Конвертер валют" };

export default async function CurrencyConverterPage() {
  let rates: Awaited<ReturnType<typeof serverApi.customsRates>> | null = null;
  try {
    rates = await serverApi.customsRates();
  } catch {
    rates = null;
  }

  return <div className="page-width currency-converter-page">
    <header className="page-head">
      <p className="eyebrow">Сервисы</p>
      <h1>Конвертер валют</h1>
      <p className="currency-converter-lead">Пересчитайте сумму по официальным курсам Национального банка Республики Беларусь.</p>
    </header>
    {rates ? <CurrencyConverter rates={rates} /> : <p className="notice" role="status">Курсы НБРБ сейчас недоступны. Попробуйте открыть страницу позже.</p>}
  </div>;
}
