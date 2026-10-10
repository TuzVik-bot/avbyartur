"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import type { CatalogItem, ListingSearch } from "@/lib/types";

type HomeSearchProps = {
  makes: CatalogItem[];
  regions: CatalogItem[];
  bodyTypes: CatalogItem[];
  priceOperationsAvailable?: boolean;
};

const fields: (keyof ListingSearch)[] = [
  "q", "make_id", "model_id", "price_min", "price_max", "year_min", "year_max",
  "mileage_min", "mileage_max", "transmission", "fuel", "body_type", "region_id"
];

function offerLabel(count: number) {
  const plural = new Intl.PluralRules("ru").select(count);
  const noun = plural === "one" ? "предложение" : plural === "few" ? "предложения" : "предложений";
  return `${count.toLocaleString("ru-BY")} ${noun}`;
}

function searchFromForm(form: HTMLFormElement): ListingSearch {
  const data = new FormData(form);
  const search: ListingSearch = {};
  for (const key of fields) {
    const value = String(data.get(key) || "").trim();
    if (value) search[key] = value as never;
  }
  if (search.price_min || search.price_max) search.currency = "BYN";
  return search;
}

export function HomeSearch({ makes, regions, bodyTypes, priceOperationsAvailable = true }: HomeSearchProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const requestId = useRef(0);
  const modelRequestId = useRef(0);
  const [models, setModels] = useState<CatalogItem[]>([]);
  const [makeId, setMakeId] = useState("");
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState(false);
  const [hasPrice, setHasPrice] = useState(false);
  const [count, setCount] = useState<number | null>(null);
  const [countLoading, setCountLoading] = useState(false);

  const modelOptions = useMemo(() => models, [models]);

  useEffect(() => {
    const form = formRef.current;
    if (!form) return;
    let active = true;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const updateCount = () => {
      if (timeout) clearTimeout(timeout);
      const search = searchFromForm(form);
      const currentId = ++requestId.current;
      setHasPrice(Boolean(search.price_min || search.price_max));
      setCount(null);
      setCountLoading(false);
      if (!Object.keys(search).length) {
        setCount(null);
        setCountLoading(false);
        return;
      }
      timeout = setTimeout(async () => {
        setCountLoading(true);
        try {
          const response = await api.listingCount(search);
          if (active && requestId.current === currentId) setCount(response.total);
        } catch {
          if (active && requestId.current === currentId) setCount(null);
        } finally {
          if (active && requestId.current === currentId) setCountLoading(false);
        }
      }, 300);
    };
    form.addEventListener("input", updateCount);
    form.addEventListener("change", updateCount);
    return () => {
      active = false;
      if (timeout) clearTimeout(timeout);
      form.removeEventListener("input", updateCount);
      form.removeEventListener("change", updateCount);
    };
  }, []);

  async function loadModels(makeId: string) {
    const currentRequest = ++modelRequestId.current;
    setModels([]);
    setModelsError(false);
    if (!makeId) {
      setModelsLoading(false);
      return;
    }
    setModelsLoading(true);
    try {
      const response = await api.catalog("models", { make_id: makeId });
      if (currentRequest === modelRequestId.current) setModels(response.items);
    } catch {
      if (currentRequest === modelRequestId.current) {
        setModels([]);
        setModelsError(true);
      }
    } finally {
      if (currentRequest === modelRequestId.current) setModelsLoading(false);
    }
  }

  return (
    <form ref={formRef} className="search-strip home-search" action="/cars" method="get" role="search">
      <label className="input-wrap search-query">
        <Search size={19} aria-hidden="true" />
        <span className="sr-only">Марка, модель или запрос</span>
        <input name="q" type="search" placeholder="Марка, модель или запрос" autoComplete="off" />
      </label>
      <label className="field search-make"><span>Марка</span>
        <select name="make_id" defaultValue="" onChange={(event) => {
          setMakeId(event.target.value);
          const modelSelect = formRef.current?.elements.namedItem("model_id");
          if (modelSelect instanceof HTMLSelectElement) modelSelect.value = "";
          void loadModels(event.target.value);
        }}>
          <option value="">Все марки</option>{makes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <label className="field search-model"><span>Модель</span>
        <select name="model_id" defaultValue="" disabled={!makeId || !modelOptions.length || modelsLoading} aria-busy={modelsLoading} aria-describedby={modelsError ? "home-model-error" : undefined}>
          <option value="">{modelsLoading ? "Загрузка моделей…" : modelsError ? "Модели временно недоступны" : modelOptions.length ? "Все модели" : "Сначала выберите марку"}</option>
          {modelOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      {modelsError && <span className="home-search-count" id="home-model-error" role="status">Список моделей временно недоступен. Поиск по марке и названию продолжает работать.</span>}
      <label className="field search-range"><span>Цена, BYN</span><span className="range-fields">
        <input name="price_min" type="number" min="1" inputMode="numeric" placeholder="От" aria-label="Цена от, BYN" disabled={!priceOperationsAvailable} aria-describedby={!priceOperationsAvailable ? "home-price-status" : undefined} />
        <input name="price_max" type="number" min="1" inputMode="numeric" placeholder="До" aria-label="Цена до, BYN" disabled={!priceOperationsAvailable} aria-describedby={!priceOperationsAvailable ? "home-price-status" : undefined} />
      </span></label>
      <input type="hidden" name="currency" value="BYN" disabled={!hasPrice} />
      {!priceOperationsAvailable && <span className="home-search-count" id="home-price-status" role="status">Фильтр по цене временно недоступен: нет подтверждённого курса НБРБ за последние 72 часа.</span>}
      <label className="field search-range"><span>Год выпуска</span><span className="range-fields">
        <input name="year_min" type="number" min="1886" inputMode="numeric" placeholder="От" aria-label="Год от" />
        <input name="year_max" type="number" min="1886" inputMode="numeric" placeholder="До" aria-label="Год до" />
      </span></label>
      <label className="field search-range"><span>Пробег, км</span><span className="range-fields">
        <input name="mileage_min" type="number" min="0" inputMode="numeric" placeholder="От" aria-label="Пробег от, км" />
        <input name="mileage_max" type="number" min="0" inputMode="numeric" placeholder="До" aria-label="Пробег до, км" />
      </span></label>
      <label className="field"><span>Коробка</span><select name="transmission" defaultValue=""><option value="">Любая</option><option value="manual">Механическая</option><option value="automatic">Автоматическая</option><option value="robot">Робот</option><option value="cvt">Вариатор</option></select></label>
      <label className="field"><span>Топливо</span><select name="fuel" defaultValue=""><option value="">Любое</option><option value="petrol">Бензин</option><option value="diesel">Дизель</option><option value="hybrid">Гибрид</option><option value="electric">Электро</option><option value="lpg">Газ</option></select></label>
      <label className="field"><span>Кузов</span><select name="body_type" defaultValue=""><option value="">Любой</option>{bodyTypes.map((item) => <option key={item.id} value={item.slug}>{item.name}</option>)}</select></label>
      <label className="field"><span>Область</span><select name="region_id" defaultValue=""><option value="">Вся Беларусь</option>{regions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <button className="button home-search-button" type="submit"><Search size={17} /> {countLoading ? "Подбираем…" : count === null ? "Показать предложения" : `Показать ${offerLabel(count)}`}</button>
      <span className="home-search-count" aria-live="polite" data-count-state={count === null ? "generic" : "count"}>
        {countLoading ? "Подбираем подходящие предложения" : count === null ? "Поиск по опубликованным объявлениям Беларуси" : `${offerLabel(count)} по выбранным условиям`}
      </span>
    </form>
  );
}
