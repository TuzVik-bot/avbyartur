import type { Metadata } from "next";
import { FinancingCalculator } from "@/components/financing-calculator";
import type { FinancingMode } from "@/lib/financing-calculator";

export const metadata: Metadata = {
  title: "Подбор кредита или лизинга",
  robots: { index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } }
};

type SearchParams = Record<string, string | string[] | undefined>;
type Currency = "BYN" | "USD" | "EUR";

function first(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function requestedPrice(value: string | undefined): string {
  if (!value || value.length > 20) return "";
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0 ? value : "";
}

export default async function FinancingPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const currencyValue = first(params.currency);
  const currency: Currency = currencyValue === "USD" || currencyValue === "EUR" ? currencyValue : "BYN";
  const modeValue = first(params.mode);
  const mode: FinancingMode = modeValue === "leasing" ? "leasing" : "credit";

  return <FinancingCalculator initialPrice={requestedPrice(first(params.price))} initialCurrency={currency} initialMode={mode} />;
}
