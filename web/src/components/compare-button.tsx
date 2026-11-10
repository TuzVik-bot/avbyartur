"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeftRight } from "lucide-react";
import { useMeasurementView } from "@/components/measurement-provider";
import { addComparisonId, removeComparisonId, useComparisonIds, MAX_COMPARISON_ITEMS } from "@/lib/comparison-state";
import styles from "./compare-button.module.css";

export function CompareButton({ listingId }: { listingId: string }) {
  const ids = useComparisonIds();
  const selected = ids.includes(listingId);
  const full = ids.length >= MAX_COMPARISON_ITEMS && !selected;
  return <button className={styles.toggle} type="button" aria-label={selected ? "Убрать из сравнения" : "Добавить к сравнению"} aria-pressed={selected} disabled={full} title={full ? "Можно выбрать не больше четырёх автомобилей" : undefined} onClick={() => selected ? removeComparisonId(listingId) : addComparisonId(listingId)}><ArrowLeftRight size={20} aria-hidden="true" /></button>;
}

export function CompareTray() {
  const ids = useComparisonIds();
  if (!ids.length) return null;
  return <aside className={styles.tray} aria-label="Выбранные для сравнения автомобили"><span>Сравнение ({ids.length}) · выбрано {ids.length} из 4{ids.length === MAX_COMPARISON_ITEMS && ". Можно выбрать не больше четырёх автомобилей."}</span><Link className="button button-primary" href="/compare">Сравнить автомобили</Link></aside>;
}

export function GlobalCompareTray() {
  const pathname = usePathname();
  return pathname === "/compare" ? null : <CompareTray />;
}

export function ResultsViewed({ count, viewKey }: { count: number; viewKey: string }) {
  useMeasurementView("search_results_viewed", { result_count: Math.max(0, Math.min(100000, Math.floor(count))) }, viewKey);
  return null;
}
