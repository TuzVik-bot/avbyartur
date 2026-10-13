import type { Money } from "@/lib/types";

export type CurrencyExchangeRate = { currency: string; byn_per_unit: string };

function decimalFraction(value: string) {
  const normalized = value.trim();
  if (!/^\d{1,32}(?:\.\d{1,24})?$/.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  const denominator = BigInt(10) ** BigInt(fraction.length);
  return { numerator: BigInt(whole) * denominator + BigInt(fraction || "0"), denominator };
}

export function convertCurrencyAmount(
  amount: string,
  from: string,
  to: string,
  rates: readonly CurrencyExchangeRate[]
): string | null {
  const amountText = amount.trim().replace(",", ".");
  if (!/^\d{1,19}(?:\.\d{1,8})?$/.test(amountText)) return null;
  const [whole, fraction = ""] = amountText.split(".");
  const amountDenominator = BigInt(10) ** BigInt(fraction.length);
  const amountNumerator = BigInt(whole) * amountDenominator + BigInt(fraction || "0");
  const maximumAmount = BigInt("1000000000000000000");
  if (amountNumerator > maximumAmount * amountDenominator) return null;

  const sourceText = rates.find((rate) => rate.currency === from)?.byn_per_unit;
  const targetText = rates.find((rate) => rate.currency === to)?.byn_per_unit;
  if (!sourceText || !targetText) return null;
  const source = decimalFraction(sourceText);
  const target = decimalFraction(targetText);
  if (!source || !target || source.numerator <= BigInt(0) || target.numerator <= BigInt(0)) return null;

  const numerator = amountNumerator * source.numerator * target.denominator;
  const denominator = amountDenominator * source.denominator * target.numerator;
  const hundred = BigInt(100);
  const minorUnits = (numerator * hundred + denominator / BigInt(2)) / denominator;
  return `${minorUnits / hundred}.${(minorUnits % hundred).toString().padStart(2, "0")}`;
}

export function formatMoney(price: Money | null) {
  if (!price) return "Цена не указана";
  const displayAmount = price.display_amount?.trim();
  const displayCurrency = price.display_currency;
  let value = price.amount;
  let currency = price.currency;
  if (displayAmount && displayCurrency) {
    value = displayAmount;
    currency = displayCurrency;
  } else if (price.currency === "USD" && price.display_byn) {
    value = price.display_byn;
    currency = "BYN";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) return `${value} ${currency}`;
  return `${new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 0 }).format(number)} ${currency}`;
}

export function formatMileage(km: number | null) {
  if (km === null) return "Пробег не указан";
  return `${new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 0 }).format(km)} км`;
}

export function formatDate(date: string) {
  const parsed = new Date(date);
  return Number.isNaN(parsed.getTime()) ? date : new Intl.DateTimeFormat("ru-BY", { dateStyle: "medium" }).format(parsed);
}

const vehicleLabels: Record<string, string> = {
  petrol: "Бензин", diesel: "Дизель", hybrid: "Гибрид", electric: "Электро", lpg: "Газ", other: "Другое",
  manual: "Механика", automatic: "Автомат", robot: "Робот", cvt: "Вариатор",
  front: "Передний", rear: "Задний", all: "Полный"
};

export function vehicleLabel(value: string | null | undefined) {
  return value ? vehicleLabels[value] || value : "Не указан";
}

export function listingHref(listing: { id: string; slug: string; category_code?: string | null; make: { slug: string } | null; model: { slug: string } | null }) {
  const fallback = listing.slug || listing.id;
  if (listing.category_code && listing.category_code !== "cars") {
    const categoryPath = listing.category_code.replaceAll("_", "-");
    return `/${categoryPath}/${encodeURIComponent(fallback)}/${encodeURIComponent(listing.id)}`;
  }
  const makeSlug = listing.make?.slug || fallback;
  const modelSlug = listing.model?.slug || fallback;
  return `/cars/${encodeURIComponent(makeSlug)}/${encodeURIComponent(modelSlug)}/${encodeURIComponent(listing.id)}`;
}
