import { formatMoney } from "@/lib/format";

export type MarketComparison = {
  label: "below_market" | "above_market";
  median_byn: string;
  sample_size: number;
  seller_count: number;
  as_of: string;
  rate_date: string | null;
};

function russianCount(value: number, one: string, few: string, many: string) {
  const plural = new Intl.PluralRules("ru").select(value);
  const noun = plural === "one" ? one : plural === "few" ? few : many;
  return `${value} ${noun}`;
}

export function marketTooltip(comparison: MarketComparison) {
  const asOf = new Date(/^\d{4}-\d{2}-\d{2}$/.test(comparison.as_of) ? `${comparison.as_of}T12:00:00+03:00` : comparison.as_of);
  const date = Number.isFinite(asOf.getTime())
    ? new Intl.DateTimeFormat("ru-BY", { timeZone: "Europe/Minsk", day: "2-digit", month: "2-digit", year: "numeric" }).format(asOf)
    : comparison.as_of;
  const sample = russianCount(comparison.sample_size, "объявлению", "объявлениям", "объявлениям");
  const sellers = russianCount(comparison.seller_count, "продавца", "продавцов", "продавцов");
  const median = formatMoney({ amount: comparison.median_byn, currency: "BYN" });
  return `По предложениям Авторынка: медианная цена по ${sample} (от ${sellers}): ${median}. Дата расчёта: ${date}.`;
}

export function MarketBadge({ comparison }: { comparison: MarketComparison }) {
  const label = comparison.label === "below_market" ? "Цена ниже рынка" : "Цена выше рынка";
  return (
    <span className={`market-badge ${comparison.label}`} data-market-comparison title={marketTooltip(comparison)} tabIndex={0} aria-label={`${label}. ${marketTooltip(comparison)}`}>{label}</span>
  );
}
