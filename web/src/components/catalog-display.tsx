"use client";

import { useEffect, useState, type ReactNode } from "react";
import { LayoutGrid, List } from "lucide-react";
import { ListingCard } from "./listing-card";
import type { ListingSummary } from "@/lib/types";
import styles from "./catalog-display.module.css";

const storageKey = "avtorinok:catalog-view";

export function CatalogDisplay({ entries, savedListingIds, count, controls, emptyState }: {
  entries: ListingSummary[];
  savedListingIds: string[];
  count: ReactNode;
  controls: ReactNode;
  emptyState: ReactNode;
}) {
  const [view, setView] = useState<"row" | "grid">("row");
  useEffect(() => {
    try {
      if (localStorage.getItem(storageKey) === "grid") setView("grid");
    } catch { /* Storage may be disabled; switching still works. */ }
  }, []);

  function selectView(next: "row" | "grid") {
    setView(next);
    try { localStorage.setItem(storageKey, next); } catch { /* Keep the session choice. */ }
  }

  const savedIds = new Set(savedListingIds);
  return <div className={styles.display}>
    <div className={`results-toolbar ${styles.toolbar}`}>
      {count}
      <div className="results-toolbar-actions">
        {controls}
        <div className={styles.switcher} role="group" aria-label="Вид объявлений">
          <button type="button" aria-label="Список" aria-pressed={view === "row"} onClick={() => selectView("row")}><List size={18} aria-hidden="true" /><span>Список</span></button>
          <button type="button" aria-label="Сетка" aria-pressed={view === "grid"} onClick={() => selectView("grid")}><LayoutGrid size={18} aria-hidden="true" /><span>Сетка</span></button>
        </div>
      </div>
    </div>
    {entries.length ? <div className={view === "grid" ? styles.grid : "listing-stack"}>
      {entries.map((listing) => <ListingCard key={listing.id} listing={listing} variant={view} saved={savedIds.has(listing.id)} />)}
    </div> : emptyState}
  </div>;
}
