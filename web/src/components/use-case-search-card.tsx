"use client";

import { useState } from "react";
import Link from "next/link";
import { buildUseCaseSearchHref, type UseCasePreset } from "@/lib/use-case-presets";
import styles from "./use-case-search-card.module.css";

const categoryOptions = [
  { value: "", label: "Все категории" },
  { value: "cars", label: "Легковые автомобили" },
  { value: "trucks", label: "Грузовики" },
  { value: "buses", label: "Автобусы" },
  { value: "motorcycles", label: "Мототехника" },
  { value: "special_equipment", label: "Спецтехника" },
  { value: "agricultural_equipment", label: "Сельхозтехника" },
  { value: "trailers", label: "Прицепы" },
  { value: "watercraft", label: "Водный транспорт" },
  { value: "parts", label: "Запчасти" },
  { value: "wheels", label: "Диски" },
  { value: "tires", label: "Шины" },
] as const;

export function UseCaseSearchCard({ preset }: { preset: UseCasePreset }) {
  const [categoryCode, setCategoryCode] = useState(preset.defaults.category_code || "");
  const [condition, setCondition] = useState(preset.defaults.condition || "");
  const [fuel, setFuel] = useState(preset.defaults.fuel || "");
  const [hasPhotos, setHasPhotos] = useState(preset.defaults.has_photos === "true");
  const [yearFrom, setYearFrom] = useState("");
  const [priceTo, setPriceTo] = useState("");
  const href = buildUseCaseSearchHref(preset, { categoryCode, condition, fuel, hasPhotos, yearFrom, priceTo });

  return (
    <article className={`info-card ${styles.card}`}>
      <div className={styles.cardHeading}>
        <h3>{preset.title}</h3>
        <p>{preset.description}</p>
      </div>

      <fieldset className={styles.filters}>
        <legend className={styles.srOnly}>Стартовые фильтры: {preset.title}</legend>
        <label className={styles.field}>
          <span>Категория</span>
          <select value={categoryCode} onChange={(event) => setCategoryCode(event.target.value)}>
            {categoryOptions.map((option) => <option key={option.value || "all"} value={option.value}>{option.label}</option>)}
          </select>
        </label>

        {preset.editor === "condition" && <label className={styles.field}>
          <span>Состояние</span>
          <select value={condition} onChange={(event) => setCondition(event.target.value)}>
            <option value="">Любое</option>
            <option value="used">С пробегом</option>
            <option value="new">Новый</option>
          </select>
        </label>}

        {preset.editor === "fuel" && <label className={styles.field}>
          <span>Топливо</span>
          <select value={fuel} onChange={(event) => setFuel(event.target.value)}>
            <option value="">Любое</option>
            <option value="petrol">Бензин</option>
            <option value="diesel">Дизель</option>
            <option value="hybrid">Гибрид</option>
            <option value="electric">Электро</option>
            <option value="lpg">Газ</option>
            <option value="other">Другое</option>
          </select>
        </label>}

        {preset.editor === "photos" && <label className={styles.checkField}>
          <input type="checkbox" checked={hasPhotos} onChange={(event) => setHasPhotos(event.target.checked)} />
          <span>Есть фотографии</span>
        </label>}

        <label className={styles.field}>
          <span>Год выпуска от</span>
          <input type="number" inputMode="numeric" min="1886" step="1" value={yearFrom} onChange={(event) => setYearFrom(event.target.value)} placeholder="Любой" />
        </label>
        <label className={styles.field}>
          <span>Цена до, BYN</span>
          <input type="number" inputMode="numeric" min="1" step="1" value={priceTo} onChange={(event) => setPriceTo(event.target.value)} placeholder="Без лимита" />
        </label>
      </fieldset>

      <p className={styles.note}>{preset.note}</p>
      <div className={styles.actions}>
        <Link className="button button-primary" href={href} aria-label={`Показать объявления: ${preset.title}`}>
          Показать объявления
        </Link>
        <span>Параметры можно изменить перед переходом.</span>
      </div>
    </article>
  );
}
