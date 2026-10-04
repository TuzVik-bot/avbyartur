import type { Money } from "@/lib/types";

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

export function listingHref(listing: { id: string; slug: string; make: { slug: string } | null; model: { slug: string } | null }) {
  const fallback = listing.slug || listing.id;
  const makeSlug = listing.make?.slug || fallback;
  const modelSlug = listing.model?.slug || fallback;
  return `/cars/${encodeURIComponent(makeSlug)}/${encodeURIComponent(modelSlug)}/${encodeURIComponent(listing.id)}`;
}
