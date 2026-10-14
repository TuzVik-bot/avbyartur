"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useCompare } from "@/components/compare-provider";
import { formatMileage, formatMoney, listingHref, vehicleLabel } from "@/lib/format";
import type { Listing } from "@/lib/types";
import styles from "./page.module.css";

type LoadedListing = { id: string; listing: Listing | null; state: "loading" | "available" | "unavailable" | "error" };

export default function ComparePage() {
  return <CompareContents />;
}

function CompareContents() {
  const { ids, hydrated, storageAvailable, remove, clear } = useCompare();
  const [loaded, setLoaded] = useState<LoadedListing[]>([]);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!hydrated) return;
    let current = true;
    setLoaded(ids.map((id) => ({ id, listing: null, state: "loading" })));
    Promise.all(ids.map(async (id): Promise<LoadedListing> => {
      try {
        // Do not send the signed-in session: the public comparison must not
        // reveal a paused/private listing merely because its owner is viewing it.
        const response = await fetch(`/api/v1/listings/${encodeURIComponent(id)}`, { credentials: "omit", cache: "no-store" });
        if (response.status >= 500 || response.status === 408 || response.status === 429) return { id, listing: null, state: "error" };
        if (!response.ok) return { id, listing: null, state: "unavailable" };
        const payload = await response.json() as { listing?: Listing };
        const listing = payload.listing;
        if (!listing || typeof listing.status !== "string") return { id, listing: null, state: "error" };
        return listing.status === "active"
          ? { id, listing, state: "available" }
          : { id, listing: null, state: "unavailable" };
      } catch {
        return { id, listing: null, state: "error" };
      }
    })).then((results) => { if (current) setLoaded(results); });
    return () => { current = false; };
  }, [ids, hydrated, retryKey]);

  const columns = ids.map((id) => loaded.find((item) => item.id === id) || { id, listing: null, state: "loading" as const });
  const available = columns.filter((item): item is LoadedListing & { listing: Listing } => item.listing !== null);
  const rows: { label: string; value: (listing: Listing) => string }[] = [
    { label: "Цена", value: (listing) => {
      const price = listing.price;
      const amount = price?.display_amount?.trim() || price?.display_byn?.trim() || price?.amount?.trim();
      return price && amount ? formatMoney(price) : "Не указано";
    } },
    { label: "Год", value: (listing) => listing.year ? `${listing.year} г.` : "Не указано" },
    { label: "Пробег", value: (listing) => listing.mileage_km == null ? "Не указано" : formatMileage(listing.mileage_km) },
    { label: "Двигатель", value: (listing) => {
      const volume = listing.engine_volume_l?.trim();
      const specs = [volume ? `${volume} л` : "", listing.power_hp != null ? `${listing.power_hp.toLocaleString("ru-BY")} л.с.` : ""].filter(Boolean);
      return specs.length ? specs.join(", ") : "Не указано";
    } },
    { label: "Коробка передач", value: (listing) => listing.transmission?.trim() ? vehicleLabel(listing.transmission) : "Не указано" },
    { label: "Топливо", value: (listing) => listing.fuel?.trim() ? vehicleLabel(listing.fuel) : "Не указано" },
    { label: "Кузов", value: (listing) => listing.body_type?.trim() || "Не указано" },
    { label: "Город", value: (listing) => listing.manual_city?.trim() || listing.city?.name?.trim() || "Не указано" }
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
            {item.state === "loading" ? <span role="status">Проверяем объявление…</span> : item.state === "error" ? <span role="alert">Не удалось проверить объявление. Проверьте соединение и повторите попытку.</span> : <span>Объявление недоступно или больше не опубликовано.</span>}
            <button className="button button-secondary button-small" type="button" aria-label="Удалить недоступное объявление из сравнения" onClick={() => remove(item.id)}>Удалить</button>
          </>}</th>)}</tr></thead>
          <tbody>{rows.map((row) => <tr key={row.label}><th scope="row">{row.label}</th>{columns.map((item) => <td key={item.id}>{item.listing ? row.value(item.listing) : "Не указано"}</td>)}</tr>)}</tbody>
        </table>
      </div>
      {columns.some((item) => item.state === "error") && <button className="button button-secondary" type="button" onClick={() => setRetryKey((key) => key + 1)}>Повторить проверку</button>}
    </>}
  </div>;
}
