import { ListingCard } from "@/components/listing-card";
import type { ListingSummary } from "@/lib/types";

export type PublicSellerListing = ListingSummary & { status: "active" };

export function SellerListings({ listingId, sellerId, items }: { listingId: string; sellerId: string; items: PublicSellerListing[] }) {
  const unique = new Map<string, PublicSellerListing>();
  for (const item of items) {
    if (item.id !== listingId && item.seller.id === sellerId && item.status === "active" && !unique.has(item.id)) unique.set(item.id, item);
  }
  const visible = [...unique.values()].sort((a, b) => b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id)).slice(0, 8);
  if (!visible.length) return null;
  return <section className="related-listings section" aria-labelledby="seller-listings-heading">
    <div className="section-heading"><h2 id="seller-listings-heading">Другие объявления продавца</h2></div>
    <div className="listing-stack">{visible.map((item) => <ListingCard key={item.id} listing={item} variant="row" />)}</div>
  </section>;
}
