"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { CatalogItem } from "@/lib/types";

type ValuationResult = {
  status: "none" | "unsupported_rate" | "low" | "high";
  median_byn: string | null;
  p25_byn: string | null;
  p75_byn: string | null;
  sample_size: number;
  seller_count: number;
  as_of: string;
  rate_date: string | null;
};

const fuelOptions: [string, string][] = [["petrol", "Бензин"], ["diesel", "Дизель"], ["hybrid", "Гибрид"], ["electric", "Электро"], ["lpg", "Газ"], ["other", "Другое"]];
const transmissionOptions: [string, string][] = [["manual", "Механика"], ["automatic", "Автомат"], ["robot", "Робот"], ["cvt", "Вариатор"], ["other", "Другое"]];

function russianCount(value: number, one: string, few: string, many: string) {
  const plural = new Intl.PluralRules("ru").select(value);
  const noun = plural === "one" ? one : plural === "few" ? few : many;
  return `${value} ${noun}`;
}

function estimateDate(asOf: string) {
  const parsed = new Date(/^\d{4}-\d{2}-\d{2}$/.test(asOf) ? `${asOf}T12:00:00+03:00` : asOf);
  return Number.isFinite(parsed.getTime())
    ? new Intl.DateTimeFormat("ru-BY", { timeZone: "Europe/Minsk", day: "2-digit", month: "2-digit", year: "numeric" }).format(parsed)
    : asOf;
}

export function MarketValuation({ makes, bodyTypes, catalogUnavailable }: { makes: CatalogItem[]; bodyTypes: CatalogItem[]; catalogUnavailable: boolean }) {
  const [fields, setFields] = useState({ make_id: "", model_id: "", generation_id: "", body_type_id: "", year: "", mileage_km: "", condition: "used", fuel: "petrol", transmission: "manual" });
  const [models, setModels] = useState<CatalogItem[]>([]);
  const [generations, setGenerations] = useState<CatalogItem[]>([]);
  const [result, setResult] = useState<ValuationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const modelsRequestId = useRef(0);
  const generationsRequestId = useRef(0);

  useEffect(() => {
    const requestId = ++modelsRequestId.current;
    if (!fields.make_id) { setModels([]); return; }
    api.catalog("models", { make_id: fields.make_id })
      .then((response) => { if (modelsRequestId.current === requestId) setModels(response.items); })
      .catch(() => { if (modelsRequestId.current === requestId) setModels([]); });
  }, [fields.make_id]);

  useEffect(() => {
    const requestId = ++generationsRequestId.current;
    if (!fields.model_id) { setGenerations([]); return; }
    api.catalog("generations", { model_id: fields.model_id })
      .then((response) => { if (generationsRequestId.current === requestId) setGenerations(response.items); })
      .catch(() => { if (generationsRequestId.current === requestId) setGenerations([]); });
  }, [fields.model_id]);

  function update(key: keyof typeof fields, value: string) {
    setFields((current) => {
      const next = { ...current, [key]: value };
      if (key === "make_id") { next.model_id = ""; next.generation_id = ""; }
      if (key === "model_id") next.generation_id = "";
      return next;
    });
    setResult(null);
    setError("");
  }

  const mileage = Number(fields.mileage_km);
  const formComplete = Boolean(
    fields.make_id && fields.model_id && fields.body_type_id && fields.year.trim()
    && Number.isInteger(Number(fields.year)) && Number(fields.year) >= 1886 && Number(fields.year) <= 2100
    && fields.mileage_km.trim() !== "" && Number.isInteger(mileage) && mileage >= 0 && mileage <= 5_000_000
  );

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !formComplete) return;
    setBusy(true);
    setError("");
    try {
      const estimate = await api.marketValuation({
        make_id: fields.make_id,
        model_id: fields.model_id,
        generation_id: fields.generation_id || null,
        body_type_id: fields.body_type_id,
        year: Number(fields.year),
        mileage_km: mileage,
        condition: fields.condition as "new" | "used",
        fuel: fields.fuel,
        transmission: fields.transmission,
      });
      setResult(estimate);
    } catch {
      setError("Оценка временно недоступна. Повторите попытку позже.");
    } finally {
      setBusy(false);
    }
  }

  const rangeLabel = result?.status === "high" ? "Надёжная оценка" : result?.status === "low" ? "Предварительная оценка" : "";

  return <div className="page-width">
    <section className="section" aria-labelledby="valuation-form-heading">
      <div className="section-heading"><h2 id="valuation-form-heading">Данные автомобиля</h2></div>
      {catalogUnavailable && <p className="notice" role="alert">Справочник марок временно недоступен — обновите страницу позже.</p>}
      <form onSubmit={submit} className="valuation-form">
        <div className="valuation-grid">
          <label className="field"><span>Марка</span>
            <select value={fields.make_id} onChange={(event) => update("make_id", event.target.value)} aria-label="Марка">
              <option value="">Не выбрано</option>
              {makes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Модель</span>
            <select value={fields.model_id} onChange={(event) => update("model_id", event.target.value)} disabled={!fields.make_id} aria-label="Модель">
              <option value="">Не выбрано</option>
              {models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Поколение (необязательно)</span>
            <select value={fields.generation_id} onChange={(event) => update("generation_id", event.target.value)} disabled={!fields.model_id} aria-label="Поколение">
              <option value="">Не выбрано</option>
              {generations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Тип кузова</span>
            <select value={fields.body_type_id} onChange={(event) => update("body_type_id", event.target.value)} aria-label="Тип кузова">
              <option value="">Не выбрано</option>
              {bodyTypes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="field"><span>Год выпуска</span>
            <input type="number" inputMode="numeric" min={1886} max={2100} value={fields.year} onChange={(event) => update("year", event.target.value)} placeholder="2016" />
          </label>
          <label className="field"><span>Пробег, км</span>
            <input type="number" inputMode="numeric" min={0} max={5_000_000} value={fields.mileage_km} onChange={(event) => update("mileage_km", event.target.value)} placeholder="150000" />
          </label>
          <label className="field"><span>Состояние</span>
            <select value={fields.condition} onChange={(event) => update("condition", event.target.value)} aria-label="Состояние">
              <option value="used">С пробегом</option>
              <option value="new">Новое</option>
            </select>
          </label>
          <label className="field"><span>Топливо</span>
            <select value={fields.fuel} onChange={(event) => update("fuel", event.target.value)} aria-label="Топливо">
              {fuelOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="field"><span>Коробка передач</span>
            <select value={fields.transmission} onChange={(event) => update("transmission", event.target.value)} aria-label="Коробка передач">
              {transmissionOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
        </div>
        <div className="form-actions">
          <button className="button" type="submit" disabled={busy || !formComplete}>{busy ? "Считаем…" : "Узнать стоимость"}</button>
        </div>
        {!formComplete && <p className="muted">Заполните марку, модель, тип кузова, год и пробег — оценка строится по объявлениям той же модели с похожим пробегом.</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
      </form>
    </section>
    {result && <section className="section" aria-labelledby="valuation-result-heading" data-valuation-result>
      <div className="section-heading"><h2 id="valuation-result-heading">Результат</h2></div>
      {result.status === "high" || result.status === "low" ? <div>
        {rangeLabel && <p><span className={`market-badge ${result.status === "high" ? "below_market" : "above_market"}`}>{rangeLabel}</span></p>}
        <p className="valuation-range">{result.p25_byn && result.p75_byn ? <><strong>{formatMoney({ amount: result.p25_byn, currency: "BYN" })} – {formatMoney({ amount: result.p75_byn, currency: "BYN" })}</strong></> : "—"} <span className="muted">— диапазон типичных цен</span></p>
        {result.median_byn && <p>Медиана: <strong>{formatMoney({ amount: result.median_byn, currency: "BYN" })}</strong></p>}
        <p className="muted">По {russianCount(result.sample_size, "активному объявлению", "активным объявлениям", "активным объявлениям")} от {russianCount(result.seller_count, "продавца", "продавцов", "продавцов")} · расчёт от {estimateDate(result.as_of)}</p>
        {result.status === "low" && <p className="notice" role="status">Объявлений в этой группе мало, поэтому оценка предварительная. После подачи объявления рядом с ценой появится сравнение с рынком.</p>}
        <div className="form-actions">
          <Link className="button" href="/sell">Подать объявление</Link>
          <Link className="button button-secondary" href="/cars">Посмотреть предложения</Link>
        </div>
      </div>
      : result.status === "unsupported_rate" ? <p className="notice" role="status">В выборке есть цены в долларах, но курс НБРБ сейчас недоступен. Повторите попытку позже.</p>
      : <p className="notice" role="status">Пока мало похожих объявлений для честной оценки. Загляните позже — база растёт, или подайте объявление первым.</p>}
    </section>}
  </div>;
}
