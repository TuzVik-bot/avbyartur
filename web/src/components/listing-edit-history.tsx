"use client";

import { useState } from "react";
import { apiRequest } from "@/lib/api";
import type { components } from "@/lib/types.generated";

type HistoryItem = components["schemas"]["ListingChangeHistoryItemOut"];
const labels: Record<string, string> = { price: "Цена", contact_phone: "Телефон", vin: "VIN", city_id: "Город", region_id: "Регион", seller_type: "Продавец", photos: "Фотографии", description: "Описание", make_id: "Марка", model_id: "Модель", generation_id: "Поколение", modification_id: "Модификация", title: "Название", year: "Год", mileage_km: "Пробег" };

function valueText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(valueText).join(", ");
  if (typeof value !== "object") return "—";
  const object = value as Record<string, unknown>;
  if (typeof object.name === "string") return object.name;
  if (typeof object.amount === "string" && typeof object.currency === "string") return `${object.amount} ${object.currency}`;
  if (typeof object.count === "number") return `${object.count} фото`;
  if (typeof object.length === "number") return `${object.length} символов`;
  return "Значение изменено";
}

export function ListingEditHistory({ listingId }: { listingId: string }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function load() {
    setBusy(true); setError(false);
    try {
      const result = await apiRequest<{ items: HistoryItem[] }>(`moderation/listings/${encodeURIComponent(listingId)}/history`);
      setItems(result.items);
    } catch { setError(true); }
    finally { setBusy(false); }
  }
  return <section className="listing-edit-history" aria-label="История правок объявления">
    <button className="button button-secondary button-small" type="button" onClick={() => void load()} disabled={busy}>{busy ? "Загружаем…" : error ? "Повторить загрузку истории" : "История правок"}</button>
    {error && <p role="alert" className="inline-error">Не удалось загрузить историю правок.</p>}
    {items?.length === 0 && <p className="muted">Правки пока не зафиксированы.</p>}
    {items?.map((item, index) => <article className="notice" key={`${item.revision}-${index}`}><h3>Ревизия {item.revision}</h3><p><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString("ru-RU")}</time> · {item.from_status || "—"} → {item.to_status || "—"}</p><dl>{item.changes.map((change) => <div key={change.field}><dt>{labels[change.field] || change.field}</dt><dd>До: {valueText(change.before)} · После: {valueText(change.after)}</dd></div>)}</dl></article>)}
  </section>;
}
