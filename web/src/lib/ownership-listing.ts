import type { OwnershipInput } from "@/lib/ownership-calculator";
import type { components } from "@/lib/types.generated";
import type { Listing } from "@/lib/types";
import { SITE_ORIGIN } from "@/lib/site-config";

export type OwnershipListingSeed = {
  id: string;
  title: string;
  listingHref: string;
  input: Partial<OwnershipInput>;
  provenance: string[];
};

export type OwnershipCustomsRates = components["schemas"]["CustomsRatesResponse"];

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** Accepts a listing UUID or this site's canonical listing path; never resolves arbitrary URLs. */
export function parseOwnershipListingId(value: string, siteOrigin: string = SITE_ORIGIN): string | null {
  const candidate = value.trim();
  if (UUID_PATTERN.test(candidate)) return candidate;

  let pathname = candidate;
  if (/^https?:\/\//i.test(candidate)) {
    try {
      const url = new URL(candidate);
      if (url.origin !== new URL(siteOrigin).origin) return null;
      pathname = url.pathname;
    } catch {
      return null;
    }
  }
  const parts = pathname.split("?")[0].split("#")[0].split("/").filter(Boolean);
  const id = parts.at(-1);
  return parts[0] === "cars" && parts.length >= 4 && id && UUID_PATTERN.test(id) ? id : null;
}

function numeric(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function roundMoney(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function isValidRateDate(value: string | null | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function isOldRateDate(value: string) {
  const ageInDays = (Date.now() - new Date(`${value}T00:00:00Z`).getTime()) / 86_400_000;
  return ageInDays > 7;
}

export function ownershipNeedsCurrentRate(listing: Listing) {
  if (listing.price?.currency !== "USD") return false;
  return !(numeric(listing.price.display_byn) && isValidRateDate(listing.price.rate_date));
}

function listingPriceByn(listing: Listing, rates?: OwnershipCustomsRates | null) {
  const price = listing.price;
  if (!price) return { amount: null, provenance: "Цена в объявлении не указана" };
  if (price.currency === "BYN") {
    const amount = numeric(price.amount);
    return { amount: amount === null ? null : roundMoney(amount), provenance: amount ? "Цена BYN из объявления" : "Цена BYN в объявлении не распознана" };
  }
  const displayed = numeric(price.display_byn);
  if (displayed && isValidRateDate(price.rate_date)) {
    const freshness = isOldRateDate(price.rate_date) ? "; курс объявления может быть устаревшим" : "";
    return { amount: roundMoney(displayed), provenance: `Сохранённый BYN-эквивалент объявления по курсу на ${price.rate_date}${freshness}` };
  }
  const usdRate = rates?.rates.find((rate) => rate.currency === "USD");
  const rate = numeric(usdRate?.byn_per_unit);
  const amount = numeric(price.amount);
  if (amount && rate && isValidRateDate(rates?.rate_date)) {
    const freshness = isOldRateDate(rates.rate_date) ? "; дата курса устарела" : "";
    return { amount: roundMoney(amount * rate), provenance: `Цена USD из объявления × курс ${usdRate?.byn_per_unit} BYN за USD на ${rates.rate_date}${freshness}` };
  }
  return { amount: null, provenance: "Цена USD известна, но BYN-эквивалент и текущий курс недоступны" };
}

function energyType(fuel: string | null): OwnershipInput["energyType"] {
  const normalized = (fuel || "").trim().toLocaleLowerCase("ru");
  if (["plugin_hybrid", "plug-in hybrid", "phev", "подключаемый гибрид"].includes(normalized)) return "plugin_hybrid";
  return normalized === "electric" || /электр/.test(normalized) ? "electric" : "fuel";
}

export function ownershipSeedFromListing(listing: Listing, rates?: OwnershipCustomsRates | null): OwnershipListingSeed {
  const { amount, provenance } = listingPriceByn(listing, rates);
  const type = energyType(listing.fuel);
  const input: Partial<OwnershipInput> = { energyType: type };
  const sources = ["Название и характеристики автомобиля из публичного объявления", provenance];
  if (amount !== null) {
    input.priceByn = amount;
    // A clearly illustrative residual value assumption; it is not a market estimate.
    input.resaleByn = roundMoney(amount * 0.6);
    sources.push("Стоимость перепродажи рассчитана как иллюстративное допущение: 60% цены через 3 года; это не факт объявления");
  }
  if (listing.fuel) sources.push(`Тип энергии определён по полю топлива «${listing.fuel}»; расход, тарифы и содержание не указаны в объявлении, предварительные значения калькулятора — изменяемый пример`);
  else sources.push("Тип топлива не указан; расход, тарифы и содержание не указаны в объявлении, предварительные значения калькулятора — изменяемый пример");
  return { id: listing.id, title: listing.title, listingHref: `/cars/${encodeURIComponent(listing.make?.slug || listing.slug)}/${encodeURIComponent(listing.model?.slug || listing.slug)}/${encodeURIComponent(listing.id)}`, input, provenance: sources };
}
