import Link from "next/link";

export type OwnerMarketComparison = {
  label: "below_market" | "above_market" | "in_market";
  difference_percent?: number | null;
};

const MARKET_LABELS: ReadonlySet<string> = new Set(["below_market", "above_market", "in_market"]);

function hintText(comparison: OwnerMarketComparison) {
  if (comparison.label === "in_market") return "Цена в рынке";
  const percent = comparison.difference_percent;
  const amount = typeof percent === "number" && Number.isFinite(percent) && percent !== 0 ? ` на ${Math.abs(percent)}%` : "";
  return comparison.label === "above_market" ? `Цена выше рынка${amount}` : `Цена ниже рынка${amount}`;
}

/** Seller-facing market hint for an own active listing; renders nothing without comparison data. */
export function MarketPriceHint({ listingId, comparison }: { listingId: string; comparison?: OwnerMarketComparison | null }) {
  if (!comparison || !MARKET_LABELS.has(comparison.label)) return null;
  return <p className="listing-market-hint" data-market-hint>
    <span className={`market-badge ${comparison.label}`}>{hintText(comparison)}</span>{" "}
    <Link className="text-link" href={`/sell?listing=${encodeURIComponent(listingId)}`}>Изменить цену</Link>
  </p>;
}
