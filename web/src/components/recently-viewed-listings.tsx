"use client";

import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { ListingCard } from "@/components/listing-card";
import { api } from "@/lib/api";
import {
  clearRecentlyViewedListings,
  readRecentlyViewedListingIds,
  recordRecentlyViewedListing,
  removeRecentlyViewedListing,
} from "@/lib/recently-viewed";
import type { ListingSummary } from "@/lib/types";
import styles from "@/components/recently-viewed-listings.module.css";

type Snapshot = { requestKey: string; items: ListingSummary[] };

export function RecentlyViewedListings({
  currentListingId,
  userId,
  shouldRecord,
}: {
  currentListingId: string;
  userId: string | null;
  shouldRecord: boolean;
}) {
  const requestKey = JSON.stringify([userId, currentListingId, shouldRecord]);
  const [snapshot, setSnapshot] = useState<Snapshot>({ requestKey: "", items: [] });

  useEffect(() => {
    let active = true;
    const ids = shouldRecord
      ? recordRecentlyViewedListing(currentListingId, userId)
      : readRecentlyViewedListingIds(userId).filter((id) => id !== currentListingId);

    setSnapshot({ requestKey, items: [] });
    if (ids.length === 0) {
      return () => { active = false; };
    }

    api.recentListings(ids).then(({ items }) => {
      if (!active) return;
      const allowedIds = new Set(ids);
      const seenIds = new Set<string>();
      const publicItems = items.filter((item) => {
        if (item.id === currentListingId || !allowedIds.has(item.id) || seenIds.has(item.id)) return false;
        seenIds.add(item.id);
        return true;
      });
      setSnapshot({ requestKey, items: publicItems });
    }).catch(() => {
      if (active) setSnapshot({ requestKey, items: [] });
    });

    return () => { active = false; };
  }, [currentListingId, requestKey, shouldRecord, userId]);

  const items = snapshot.requestKey === requestKey ? snapshot.items : [];
  if (items.length === 0) return null;

  function removeListing(id: string) {
    removeRecentlyViewedListing(userId, id);
    setSnapshot((current) => current.requestKey === requestKey
      ? { ...current, items: current.items.filter((item) => item.id !== id) }
      : current);
  }

  function clearHistory() {
    clearRecentlyViewedListings(userId);
    setSnapshot((current) => current.requestKey === requestKey ? { ...current, items: [] } : current);
  }

  return (
    <section className={`section ${styles.section}`} aria-labelledby="recent-listings-heading">
      <div className={`section-heading ${styles.heading}`}>
        <h2 id="recent-listings-heading">Недавно просмотренные</h2>
        <button
          className={`button button-secondary ${styles.clearButton}`}
          type="button"
          aria-label="Очистить историю недавно просмотренных объявлений"
          onClick={clearHistory}
        >
          <Trash2 size={15} aria-hidden="true" /> Очистить историю
        </button>
      </div>
      <div className={`listing-stack ${styles.stack}`}>
        {items.map((item) => (
          <div className={styles.item} key={item.id}>
            <ListingCard listing={item} variant="row" />
            <button
              className={`button button-secondary ${styles.removeButton}`}
              type="button"
              aria-label={`Удалить из недавно просмотренных: ${item.title}`}
              onClick={() => removeListing(item.id)}
            >
              <Trash2 size={15} aria-hidden="true" /> Удалить
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
