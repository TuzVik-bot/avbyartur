import { BadgeCheck, FileCheck2, Tag } from "lucide-react";
import { photoBadgeOptions } from "@/lib/photo-badges";
import type { PhotoBadge } from "@/lib/types";

const icons = { verified: BadgeCheck, free_history: FileCheck2, best_price: Tag };

export function ListingPhotoBadges({ badges = [] }: { badges?: PhotoBadge[] }) {
  const visible = photoBadgeOptions.filter(({ value }) => badges.includes(value));
  if (!visible.length) return null;
  return <div className="listing-photo-badges" aria-label="Метки объявления">
    {visible.map(({ value, label }) => {
      const Icon = icons[value];
      return <span key={value} className={`listing-photo-badge photo-badge-${value}`}><Icon size={15} aria-hidden="true" /><span>{label}</span></span>;
    })}
  </div>;
}
