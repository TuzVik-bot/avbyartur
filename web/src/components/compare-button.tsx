"use client";

import Link from "next/link";
import { Check, GitCompareArrows } from "lucide-react";
import { useState } from "react";
import { MAX_COMPARE_LISTINGS, useCompare } from "@/components/compare-provider";

export function CompareButton({ listingId }: { listingId: string }) {
  const { ids, add, remove } = useCompare();
  const [message, setMessage] = useState("");
  const selected = ids.includes(listingId);

  function toggle() {
    if (selected) {
      remove(listingId);
      setMessage("Автомобиль удалён из сравнения.");
      return;
    }
    if (ids.length >= MAX_COMPARE_LISTINGS) {
      setMessage("Можно сравнить не больше четырёх автомобилей. Удалите один автомобиль в сравнении.");
      return;
    }
    add(listingId);
    setMessage("Автомобиль добавлен к сравнению.");
  }

  return <span className="compare-action">
    <button className="button button-secondary button-small" type="button" aria-pressed={selected} onClick={toggle}>
      {selected ? <Check size={16} aria-hidden="true" /> : <GitCompareArrows size={16} aria-hidden="true" />}
      {selected ? "В сравнении" : "Сравнить"}
    </button>
    <Link href="/compare" aria-label={`Открыть сравнение, автомобилей: ${ids.length}`}>Сравнение ({ids.length})</Link>
    <span className="sr-only" role="status" aria-live="polite">{message}</span>
  </span>;
}
