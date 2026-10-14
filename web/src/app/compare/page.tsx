"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CompareProvider, useCompare } from "@/components/compare-provider";
import { formatMileage, formatMoney, listingHref, vehicleLabel } from "@/lib/format";
import type { Listing } from "@/lib/types";
import styles from "./page.module.css";

type LoadedListing = { id: string; listing: Listing | null; error: boolean };

export default function ComparePage() {
  return <CompareProvider><CompareContents /></CompareProvider>;
}

function CompareContents() {
  const { ids, hydrated, storageAvailable, remove, clear } = useCompare();
  const [loaded, setLoaded] = useState<LoadedListing[]>([]);

  useEffect(() => {
    if (!hydrated) return;
    let current = true;
    Promise.all(ids.map(async (id): Promise<LoadedListing> => {
      try {
        // Do not send the signed-in session: the public comparison must not
        // reveal a paused/private listing merely because its owner is viewing it.
        const response = await fetch(`/api/v1/listings/${encodeURIComponent(id)}`, { credentials: "omit", cache: "no-store" });
        if (!response.ok) return { id, listing: null, error: false };
        const payload = await response.json() as { listing?: Listing };
        const listing = payload.listing;
        return { id, listing: listing?.status === "active" ? listing : null, error: false };
      } catch {
        return { id, listing: null, error: false };
      }
    })).then((results) => { if (current) setLoaded(results); });
    return () => { current = false; };
  }, [ids, hydrated]);

  const columns = ids.map((id) => loaded.find((item) => item.id === id) || { id, listing: null, error: true });
  const available = columns.filter((item): item is LoadedListing & { listing: Listing } => item.listing !== null);
  const rows: { label: string; value: (listing: Listing) => string }[] = [
    { label: "Цена", value: (listing) => formatMoney(listing.price) },
    { label: "Год", value: (listing) => listing.year ? `${listing.year} г.` : "Не указано" },
    { label: "Пробег", value: (listing) => listing.mileage_km == null ? "Не указано" : formatMileage(listing.mileage_km) },
    { label: "Двигатель", value: (listing) => listing.engine_volume_l || listing.power_hp != null ? [listing.engine_volume_l ? `${listing.engine_volume_l} л` : "", listing.power_hp != null ? `${listing.power_hp.toLocaleString("ru-BY")} л.с.` : ""].filter(Boolean).join(", ") : "Не указано" },
    { label: "Коробка передач", value: (listing) => vehicleLabel(listing.transmission) },
    { label: "Топливо", value: (listing) => vehicleLabel(listing.fuel) },
    { label: "Кузов", value: (listing) => listing.body_type || "Не указано" },
    { label: "Город", value: (listing) => listing.manual_city || listing.city?.name || "Не указано" }
  ];

  return <div className={`page-width ${styles.page}`}>
    <div className="page-head"><h1>Сравнение автомобилей</h1><p>{ids.length} из 4</p></div>
    {!storageAvailable && <p className="notice" role="status">Браузер не разрешил сохранить список. Сравнение останется доступным, пока открыта эта вкладка.</p>}
    {!hydrated ? <p role="status">Загружаем список сравнения…</p> : ids.length === 0 ? <div className="empty-state"><h2>Пока нет автомобилей для сравнения</h2><p>Добавьте объявления кнопкой «Сравнить».</p><Link className="button button-primary" href="/cars">Найти автомобиль</Link></div> : <>
      <div className={styles.toolbar}>
        <span className="muted">Доступных объявлений: {available.length} из {ids.length}</span>
        <button className="button button-secondary button-small" type="button" onClick={clear}>Очистить сравнение</button>
      </div>
      <div className={styles.scroll} role="region" aria-label="Таблица сравнения автомобилей" tabIndex={0}>
        <table className={styles.table}>
          <thead><tr><th scope="col">Характеристика</th>{columns.map((item) => <th scope="col" key={item.id}>{item.listing ? <>
            <Link href={listingHref(item.listing)}>{item.listing.title}</Link>
            {item.listing.cover_url && <img className={styles.photo} src={item.listing.cover_url} alt={`Фото: ${item.listing.title}`} />}
            <button className="button button-secondary button-small" type="button" aria-label={`Удалить ${item.listing.title} из сравнения`} onClick={() => remove(item.id)}>Удалить</button>
          </> : <>
            <span>{item.error ? "Проверяем объявление…" : "Объявление недоступно или больше не опубликовано."}</span>
            <button className="button button-secondary button-small" type="button" aria-label="Удалить недоступное объявление из сравнения" onClick={() => remove(item.id)}>Удалить</button>
          </>}</th>)}</tr></thead>
          <tbody>{rows.map((row) => <tr key={row.label}><th scope="row">{row.label}</th>{columns.map((item) => <td key={item.id}>{item.listing ? row.value(item.listing) : "Не указано"}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </>}
  </div>;
}
