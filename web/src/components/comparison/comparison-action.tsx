"use client";

import Link from "next/link";
import { addComparisonId, MAX_COMPARISON_ITEMS, removeComparisonId, useComparisonIds } from "@/lib/comparison-state";
import styles from "./comparison-action.module.css";

export function ComparisonAction({ listingId }: { listingId: string }) {
  const selectedIds = useComparisonIds();
  const isSelected = selectedIds.includes(listingId);
  const isFull = selectedIds.length >= MAX_COMPARISON_ITEMS && !isSelected;

  function toggleSelection() {
    if (isSelected) removeComparisonId(listingId);
    else addComparisonId(listingId);
  }

  return (
    <div className={styles.actions}>
      <button
        className={styles.toggle}
        type="button"
        aria-pressed={isSelected}
        disabled={isFull}
        onClick={toggleSelection}
      >
        {isSelected ? "Убрать из сравнения" : "Добавить к сравнению"}
      </button>
      <Link
        className={styles.listLink}
        href="/compare"
        aria-label={`Открыть сравнение выбранных автомобилей${selectedIds.length ? `, ${selectedIds.length}` : ""}`}
      >
        Сравнение{selectedIds.length ? ` (${selectedIds.length})` : ""}
      </Link>
      {isFull && <span className={styles.limitNotice} role="status">Можно выбрать не больше 4 объявлений. Удалите одно в сравнении.</span>}
    </div>
  );
}
