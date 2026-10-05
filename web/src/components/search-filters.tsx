"use client";

import { CategoryFields } from "@/components/category-fields";
import { categoryPath, detailPayload, isGoods, hasMileage } from "@/lib/listing-categories";
import { useEffect, useRef, useState } from "react";
import { Filter, SlidersHorizontal, X } from "lucide-react";
import { api } from "@/lib/api";
import type { CatalogCity, CatalogItem, CatalogModification, ListingSearch } from "@/lib/types";

const emptyCatalogItems: CatalogItem[] = [];
const emptyModifications: CatalogModification[] = [];

function citiesForRegion(cities: CatalogCity[], regionId: string) {
  return regionId ? cities.filter((city) => city.region_id === regionId) : cities;
}

function searchDetails(search: ListingSearch) {
  const category = search.category_code || "cars";
    let values: Record<string, string> = {};
    try { values = Object.fromEntries(Object.entries(JSON.parse(search.details || "{}") as Record<string, unknown>).map(([key, value]) => [key, String(value)])); } catch { /* Invalid input remains visible in the server search error. */ }
    for (const key of ["diameter_in", "width_mm", "season"] as const) if (search[key]) values[key] = search[key];
    const subtypeKey = ({ trucks: "vehicle_type", buses: "vehicle_type", motorcycles: "vehicle_type", special_equipment: "equipment_type", agricultural_equipment: "equipment_type", trailers: "trailer_type", watercraft: "watercraft_type", parts: "part_group" } as Record<string, string>)[category];
    if (subtypeKey && search.subtype) values[subtypeKey] = search.subtype;
    return values;
}

export function SearchFilters({ search, makes, initialModels, initialGenerations, initialModifications = emptyModifications, regions, initialCities, bodyTypes, priceOperationsAvailable = true }: {
  search: ListingSearch;
  makes: CatalogItem[];
  initialModels: CatalogItem[];
  initialGenerations?: CatalogItem[];
  initialModifications?: CatalogModification[];
  regions: CatalogItem[];
  initialCities: CatalogCity[];
  bodyTypes: CatalogItem[];
  priceOperationsAvailable?: boolean;
}) {
  const category = search.category_code || "cars";
  const [details, setDetails] = useState<Record<string, string>>(() => searchDetails(search));
  useEffect(() => { setDetails(searchDetails(search)); }, [search.details, search.category_code, search.subtype, search.diameter_in, search.width_mm, search.season]);
  const initialRegionId = search.region_id || initialCities.find((city) => city.id === search.city_id)?.region_id || "";
  const [open, setOpen] = useState(false);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const [makeId, setMakeId] = useState(search.make_id || "");
  const [modelId, setModelId] = useState(search.model_id || "");
  const [generationId, setGenerationId] = useState(search.generation_id || "");
  const [bodyVariantId, setBodyVariantId] = useState(search.body_variant_id || "");
  const [modificationId, setModificationId] = useState(search.modification_id || "");
  const [regionId, setRegionId] = useState(initialRegionId);
  const [cityId, setCityId] = useState(search.city_id || "");
  const [models, setModels] = useState(initialModels);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState(false);
  const [modelsRetry, setModelsRetry] = useState(0);
  const [generations, setGenerations] = useState<CatalogItem[]>(initialGenerations || emptyCatalogItems);
  const [generationsLoading, setGenerationsLoading] = useState(false);
  const [generationsError, setGenerationsError] = useState(false);
  const [generationsRetry, setGenerationsRetry] = useState(0);
  const [bodyVariants, setBodyVariants] = useState<CatalogItem[]>(emptyCatalogItems);
  const [bodyVariantsLoading, setBodyVariantsLoading] = useState(false);
  const [bodyVariantsError, setBodyVariantsError] = useState(false);
  const [modifications, setModifications] = useState(initialModifications);
  const [modificationsLoading, setModificationsLoading] = useState(false);
  const [modificationsError, setModificationsError] = useState(false);
  const [cities, setCities] = useState(() => citiesForRegion(initialCities, initialRegionId));
  const [citiesLoading, setCitiesLoading] = useState(false);
  const [citiesError, setCitiesError] = useState(false);
  const [citiesRetry, setCitiesRetry] = useState(0);
  const firstMakeId = useRef<string | undefined>(search.model_id && !initialModels.some((item) => item.id === search.model_id) ? undefined : search.make_id || "");
  const firstGenerationModelId = useRef<string | undefined>(initialGenerations !== undefined && (!search.generation_id || initialGenerations.some((item) => item.id === search.generation_id)) ? search.model_id || "" : undefined);
  const firstRegionId = useRef<string | undefined>(initialRegionId && initialCities.some((city) => city.region_id === initialRegionId) ? initialRegionId : undefined);
  const firstGenerationId = useRef<string | undefined>(search.generation_id || "");
  const filterTriggerRef = useRef<HTMLButtonElement>(null);
  const filterPanelRef = useRef<HTMLDivElement>(null);
  const filterCloseRef = useRef<HTMLButtonElement>(null);
  const mobileDialogWasOpen = useRef(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 800px)");
    const updateViewport = () => {
      setIsMobileViewport(media.matches);
      if (!media.matches) setOpen(false);
    };
    updateViewport();
    media.addEventListener?.("change", updateViewport);
    return () => media.removeEventListener?.("change", updateViewport);
  }, []);

  useEffect(() => {
    if (!isMobileViewport || !open) {
      if (mobileDialogWasOpen.current) {
        mobileDialogWasOpen.current = false;
        filterTriggerRef.current?.focus();
      }
      return;
    }
    mobileDialogWasOpen.current = true;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    filterCloseRef.current?.focus();
    return () => { document.body.style.overflow = previousOverflow; };
  }, [isMobileViewport, open]);

  useEffect(() => {
    if (!isMobileViewport || !open) return;
    function onDialogKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = filterPanelRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
      else if (!filterPanelRef.current?.contains(active)) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onDialogKeyDown);
    return () => document.removeEventListener("keydown", onDialogKeyDown);
  }, [isMobileViewport, open]);

  useEffect(() => {
    firstMakeId.current = search.model_id && !initialModels.some((item) => item.id === search.model_id) ? undefined : search.make_id || "";
    firstGenerationId.current = search.generation_id || "";
    firstGenerationModelId.current = initialGenerations !== undefined && (!search.generation_id || initialGenerations.some((item) => item.id === search.generation_id)) ? search.model_id || "" : undefined;
    firstRegionId.current = initialRegionId && initialCities.some((city) => city.region_id === initialRegionId) ? initialRegionId : undefined;
    setModels(initialModels);
    setModelsLoading(false);
    setModelsError(false);
    setMakeId(search.make_id || "");
    setModelId(search.model_id || "");
    setGenerationId(search.generation_id || "");
    setGenerations(initialGenerations || emptyCatalogItems);
    setGenerationsLoading(false);
    setGenerationsError(false);
    setBodyVariantId(search.body_variant_id || "");
    setModificationId(search.modification_id || "");
    setModifications(initialModifications);
    setModificationsLoading(false);
    setModificationsError(false);
    setRegionId(initialRegionId);
    setCityId(search.city_id || "");
    setCities(citiesForRegion(initialCities, initialRegionId));
    setCitiesLoading(false);
    setCitiesError(false);
  }, [search.make_id, search.model_id, search.generation_id, search.body_variant_id, search.modification_id, search.region_id, search.city_id, initialRegionId, initialGenerations, initialModifications, initialModels, initialCities]);

  useEffect(() => {
    setCities(citiesForRegion(initialCities, regionId));
  }, [initialCities, regionId]);

  useEffect(() => {
    if (firstMakeId.current === makeId) {
      firstMakeId.current = undefined;
      return;
    }
    let active = true;
    if (!makeId) {
      setModels([]);
      setModelsLoading(false);
      setModelsError(false);
      return () => { active = false; };
    }
    setModels([]);
    setModelsLoading(true);
    setModelsError(false);
    api.catalog("models", { make_id: makeId })
      .then((res) => { if (active) setModels(res.items); })
      .catch(() => { if (active) { setModels([]); setModelsError(true); } })
      .finally(() => { if (active) setModelsLoading(false); });
    return () => { active = false; };
  }, [makeId, modelsRetry]);

  useEffect(() => {
    if (firstRegionId.current === regionId) {
      firstRegionId.current = undefined;
      return;
    }
    let active = true;
    if (!regionId) {
      setCities([]);
      setCitiesLoading(false);
      setCitiesError(false);
      return () => { active = false; };
    }
    if (initialCities.some((city) => city.region_id === regionId)) {
      setCitiesLoading(false);
      setCitiesError(false);
      return;
    }
    setCities([]);
    setCitiesLoading(true);
    setCitiesError(false);
    api.cities(regionId)
      .then((res) => { if (active) setCities(res.items.map((city) => ({ ...city, region_id: regionId }))); })
      .catch(() => { if (active) { setCities([]); setCitiesError(true); } })
      .finally(() => { if (active) setCitiesLoading(false); });
    return () => { active = false; };
  }, [regionId, initialCities, citiesRetry]);

  useEffect(() => {
    if (firstGenerationModelId.current === modelId) {
      firstGenerationModelId.current = undefined;
      return;
    }
    let active = true;
    if (!modelId) {
      setGenerations([]);
      setGenerationsLoading(false);
      setGenerationsError(false);
      return () => { active = false; };
    }
    setGenerations([]);
    setGenerationsLoading(true);
    setGenerationsError(false);
    api.catalog("generations", { model_id: modelId })
      .then((res) => {
        if (!active) return;
        setGenerations(res.items);
        setGenerationId((current) => current && !res.items.some((item) => item.id === current) ? "" : current);
      })
      .catch(() => {
        if (!active) return;
        setGenerations([]);
        setGenerationsError(true);
      })
      .finally(() => { if (active) setGenerationsLoading(false); });
    return () => { active = false; };
  }, [modelId, generationsRetry]);

  useEffect(() => {
    if (firstGenerationId.current === generationId) {
      firstGenerationId.current = undefined;
      return;
    }

    let active = true;
    if (!generationId) {
      setModifications([]);
      setModificationsLoading(false);
      setModificationsError(false);
      setModificationId("");
      return () => { active = false; };
    }

    setModifications([]);
    setModificationsLoading(true);
    setModificationsError(false);
    api.catalog("modifications", { generation_id: generationId })
      .then((res) => {
        if (!active) return;
        setModifications(res.items);
        setModificationId((current) => current && !res.items.some((item) => item.id === current) ? "" : current);
      })
      .catch(() => {
        if (!active) return;
        setModifications([]);
        setModificationsError(true);
      })
      .finally(() => { if (active) setModificationsLoading(false); });
    return () => { active = false; };
  }, [generationId]);

  useEffect(() => {
    let active = true;
    if (!generationId) {
      setBodyVariants([]);
      setBodyVariantsLoading(false);
      setBodyVariantsError(false);
      setBodyVariantId("");
      return () => { active = false; };
    }

    setBodyVariants([]);
    setBodyVariantsLoading(true);
    setBodyVariantsError(false);
    api.catalog("body-variants", { generation_id: generationId })
      .then((res) => {
        if (!active) return;
        setBodyVariants(res.items);
        setBodyVariantId((current) => current && !res.items.some((item) => item.id === current) ? "" : current);
      })
      .catch(() => {
        if (!active) return;
        setBodyVariants([]);
        setBodyVariantsError(true);
      })
      .finally(() => { if (active) setBodyVariantsLoading(false); });
    return () => { active = false; };
  }, [generationId]);

  function changeGeneration(nextGenerationId: string) {
    setGenerationId(nextGenerationId);
    setBodyVariantId("");
    setBodyVariants([]);
    setBodyVariantsError(false);
    setBodyVariantsLoading(Boolean(nextGenerationId));
    setModificationId("");
    setModifications([]);
    setModificationsError(false);
    setModificationsLoading(Boolean(nextGenerationId));
  }

  return (
    <aside className="search-filter-area" aria-label="Фильтры поиска">
      <button ref={filterTriggerRef} className="button button-secondary filter-toggle" type="button" aria-expanded={open} aria-controls="search-filter-panel" onClick={() => setOpen(!open)}>
        <SlidersHorizontal size={17} /> Фильтры <Filter size={15} />
      </button>
      {isMobileViewport && open && <button className="filter-backdrop" type="button" aria-label="Закрыть фильтры" tabIndex={-1} onClick={() => setOpen(false)} />}
      <div ref={filterPanelRef} id="search-filter-panel" className={`filter-panel ${open ? "is-open" : ""}`}
        role={isMobileViewport ? "dialog" : "region"} aria-label="Параметры поиска"
        aria-modal={isMobileViewport && open ? "true" : undefined} aria-hidden={isMobileViewport && !open ? "true" : undefined}
        hidden={isMobileViewport && !open}>
        <header className="filter-panel-header">
          <div><p className="eyebrow">Подберите транспорт</p><h2>Параметры поиска</h2></div>
          <button ref={filterCloseRef} className="icon-button filter-close" type="button" aria-label="Закрыть фильтры" onClick={() => setOpen(false)}><X size={20} /></button>
        </header>
        <form key={JSON.stringify(search)} action={categoryPath(category)} method="get" className="filter-grid">
          <input type="hidden" name="category_code" value={category} />
          {category !== "cars" && <>
            <label className="field"><span>Поиск по названию</span><input type="search" name="q" defaultValue={search.q || ""} /></label>
            <CategoryFields code={category} values={details} onChange={(key, value) => setDetails(previous => ({ ...previous, [key]: value }))} search />
            <input type="hidden" name="details" value={JSON.stringify(detailPayload(category, details))} />
            {!isGoods(category) && <fieldset className="filter-wide"><legend>Год выпуска</legend><div className="range-fields"><input name="year_min" type="number" aria-label="Год от" min="1886" defaultValue={search.year_min || ""} /><input name="year_max" type="number" aria-label="Год до" min="1886" defaultValue={search.year_max || ""} /></div></fieldset>}
            {hasMileage(category) && <fieldset className="filter-wide"><legend>Пробег, км</legend><div className="range-fields"><input name="mileage_min" type="number" min="0" aria-label="Пробег от, км" defaultValue={search.mileage_min || ""} /><input name="mileage_max" type="number" min="0" aria-label="Пробег до, км" defaultValue={search.mileage_max || ""} /></div></fieldset>}
          </>}
          {category === "cars" && <>
          <label className="field filter-wide">
            <span>Марка</span>
            <select name="make_id" value={makeId} onChange={(event) => {
              setMakeId(event.target.value);
              setModelId("");
              changeGeneration("");
              setModels([]);
              setGenerations([]);
            }}>
              <option value="">Любая марка</option>
              {makeId && !makes.some((item) => item.id === makeId) && <option value={makeId}>Марка выбрана</option>}
              {makes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <div className="filter-wide">
            <label className="field">
              <span>Модель</span>
              <select name="model_id" value={modelId} onChange={(event) => {
                setModelId(event.target.value);
                changeGeneration("");
                setGenerations([]);
              }} disabled={(modelsLoading && !modelId) || (!models.length && !modelId)} aria-busy={modelsLoading} aria-describedby={modelsError ? "model-catalog-status" : undefined}>
                <option value="">{!makeId ? "Любая модель" : modelsLoading ? "Загрузка моделей…" : modelsError ? "Модели временно недоступны" : models.length ? "Любая модель" : "Нет доступных моделей"}</option>
                {modelId && !models.some((item) => item.id === modelId) && <option value={modelId}>Модель выбрана</option>}
                {models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            {modelsError && <p className="catalog-error muted" id="model-catalog-status" role="status">Не удалось загрузить модели. <button className="button button-secondary button-small" type="button" onClick={() => setModelsRetry((attempt) => attempt + 1)}>Повторить</button></p>}
          </div>
          <div className="filter-wide">
            <label className="field">
              <span>Поколение</span>
              <select name="generation_id" value={generationId} onChange={(event) => changeGeneration(event.target.value)} disabled={(generationsLoading && !generationId) || (!generations.length && !generationId)} aria-busy={generationsLoading} aria-describedby={generationsError ? "generation-catalog-status" : undefined}>
                <option value="">{!modelId ? "Любое поколение" : generationsLoading ? "Загрузка поколений…" : generationsError ? "Поколения временно недоступны" : generations.length ? "Любое поколение" : "Нет доступных поколений"}</option>
                {generationId && !generations.some((item) => item.id === generationId) && <option value={generationId}>Поколение выбрано</option>}
                {generations.map((item) => <option key={item.id} value={item.id}>{item.name}{item.year_from ? ` · ${item.year_from}${item.year_to ? `–${item.year_to}` : ""}` : ""}</option>)}
              </select>
            </label>
            {generationsError && <p className="catalog-error muted" id="generation-catalog-status" role="status">Не удалось загрузить поколения. <button className="button button-secondary button-small" type="button" onClick={() => setGenerationsRetry((attempt) => attempt + 1)}>Повторить</button></p>}
          </div>
          <label className="field filter-wide">
            <span>Вариант кузова</span>
            <select name="body_variant_id" value={bodyVariantId} onChange={(event) => setBodyVariantId(event.target.value)} disabled={!generationId || (bodyVariantsLoading && !bodyVariantId) || (!bodyVariants.length && !bodyVariantId && !bodyVariantsLoading && !bodyVariantsError)} aria-busy={bodyVariantsLoading} aria-describedby={bodyVariantsError ? "body-variant-catalog-status" : undefined}>
              <option value="">{!generationId ? "Сначала выберите поколение" : bodyVariantsLoading ? "Загрузка вариантов кузова…" : bodyVariantsError ? "Варианты кузова временно недоступны" : bodyVariants.length ? "Любой вариант кузова" : "Нет доступных вариантов кузова"}</option>
              {bodyVariantId && !bodyVariants.some((item) => item.id === bodyVariantId) && <option value={bodyVariantId}>Вариант кузова выбран</option>}
              {bodyVariants.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            {bodyVariantsError && <span className="muted" id="body-variant-catalog-status" role="status">Не удалось загрузить варианты кузова каталога. Попробуйте позже.</span>}
          </label>
          <label className="field filter-wide">
            <span>Модификация</span>
            <select name="modification_id" value={modificationId} onChange={(event) => setModificationId(event.target.value)} disabled={!generationId || modificationsLoading || (!modifications.length && !modificationId)} aria-busy={modificationsLoading} aria-describedby={modificationsError ? "modification-catalog-status" : undefined}>
              <option value="">{!generationId ? "Сначала выберите поколение" : modificationsLoading ? "Загрузка модификаций…" : modificationsError ? "Модификации временно недоступны" : modifications.length ? "Любая модификация" : "Нет доступных модификаций"}</option>
              {modificationId && !modifications.some((item) => item.id === modificationId) && <option value={modificationId}>Комплектация выбрана</option>}
              {modifications.map((item) => <option key={item.id} value={item.id}>{item.name}{item.specs?.production_period_raw?.trim() ? ` · ${item.specs.production_period_raw.trim()}` : ""}</option>)}
            </select>
            {modificationsError && <span className="muted" id="modification-catalog-status" role="status">Не удалось загрузить модификации каталога. Попробуйте позже.</span>}
          </label>
          <label className="field filter-wide">
            <span>Тип кузова</span>
            <select name="body_type" defaultValue={search.body_type || ""}><option value="">Любой кузов</option>{search.body_type && !bodyTypes.some((item) => item.slug === search.body_type || item.id === search.body_type) && <option value={search.body_type}>Кузов выбран</option>}{bodyTypes.map((item) => <option key={item.id} value={item.slug}>{item.name}</option>)}</select>
          </label>
          <label className="field"><span>Цвет</span><select name="color" defaultValue={search.color || ""}><option value="">Любой</option><option value="black">Чёрный</option><option value="white">Белый</option><option value="gray">Серый</option><option value="silver">Серебристый</option><option value="red">Красный</option><option value="blue">Синий</option><option value="green">Зелёный</option><option value="yellow">Жёлтый</option><option value="brown">Коричневый</option><option value="beige">Бежевый</option><option value="orange">Оранжевый</option><option value="purple">Фиолетовый</option><option value="other">Другой</option></select></label>
          <label className="field"><span>Таможенный статус</span><select name="customs_status" defaultValue={search.customs_status || ""}><option value="">Любой</option><option value="cleared_rb">Оформлен в РБ</option><option value="eaeu_import">Ввезён из ЕАЭС</option><option value="uncleared">Не растаможен</option><option value="unknown">Не указан</option></select></label>
          <label className="field"><span>Техническое состояние</span><select name="technical_condition" defaultValue={search.technical_condition || ""}><option value="">Любое</option><option value="good">Исправен</option><option value="needs_repair">Требует ремонта</option><option value="non_operational">Не на ходу</option></select></label>
          <label className="field"><span>Состояние кузова</span><select name="body_condition" defaultValue={search.body_condition || ""}><option value="">Любое</option><option value="good">Без заметных повреждений</option><option value="minor_damage">Есть небольшие повреждения</option><option value="significant_damage">Есть серьёзные повреждения</option><option value="repaired">Был в ремонте</option></select></label>
          </>}
          <fieldset className="filter-wide" disabled={!priceOperationsAvailable}>
            <legend className="field-label">Цена, BYN</legend>
            <div className="range-fields">
              <input name="price_min" inputMode="numeric" type="number" min="1" aria-label="Цена от, BYN" placeholder="От" defaultValue={search.price_min || ""} />
              <input name="price_max" inputMode="numeric" type="number" min="1" aria-label="Цена до, BYN" placeholder="До" defaultValue={search.price_max || ""} />
            </div>
          </fieldset>
          <input type="hidden" name="currency" value={search.currency || "BYN"} />
          {category === "cars" && search.q && <input type="hidden" name="q" value={search.q} />}
          {search.sort && <input type="hidden" name="sort" value={search.sort} />}
          {category === "cars" && <>
          <fieldset className="filter-wide">
            <legend className="field-label">Год выпуска</legend>
            <div className="range-fields">
              <input name="year_min" inputMode="numeric" type="number" min="1886" aria-label="Год от" placeholder="От" defaultValue={search.year_min || ""} />
              <input name="year_max" inputMode="numeric" type="number" min="1886" aria-label="Год до" placeholder="До" defaultValue={search.year_max || ""} />
            </div>
          </fieldset>
          <fieldset className="filter-wide">
            <legend className="field-label">Пробег, км</legend>
            <div className="range-fields">
              <input name="mileage_min" inputMode="numeric" type="number" min="0" aria-label="Пробег от, км" placeholder="От" defaultValue={search.mileage_min || ""} />
              <input name="mileage_max" inputMode="numeric" type="number" min="0" aria-label="Пробег до, км" placeholder="До" defaultValue={search.mileage_max || ""} />
            </div>
          </fieldset>
          <fieldset className="filter-wide"><legend className="field-label">Объём двигателя, л</legend><div className="range-fields"><input name="engine_volume_min" inputMode="decimal" type="number" min="0" max="20" step="0.1" aria-label="Объём двигателя от, л" placeholder="От" defaultValue={search.engine_volume_min || ""} /><input name="engine_volume_max" inputMode="decimal" type="number" min="0" max="20" step="0.1" aria-label="Объём двигателя до, л" placeholder="До" defaultValue={search.engine_volume_max || ""} /></div></fieldset>
          <fieldset className="filter-wide"><legend className="field-label">Мощность, л.с.</legend><div className="range-fields"><input name="power_min" inputMode="numeric" type="number" min="1" max="2500" aria-label="Мощность от, л.с." placeholder="От" defaultValue={search.power_min || ""} /><input name="power_max" inputMode="numeric" type="number" min="1" max="2500" aria-label="Мощность до, л.с." placeholder="До" defaultValue={search.power_max || ""} /></div></fieldset>
          <label className="field"><span>Топливо</span><select name="fuel" defaultValue={search.fuel || ""}><option value="">Любое</option><option value="petrol">Бензин</option><option value="diesel">Дизель</option><option value="hybrid">Гибрид</option><option value="electric">Электро</option><option value="lpg">Газ</option><option value="other">Другое</option></select></label>
          <label className="field"><span>Коробка</span><select name="transmission" defaultValue={search.transmission || ""}><option value="">Любая</option><option value="manual">Механика</option><option value="automatic">Автомат</option><option value="robot">Робот</option><option value="cvt">Вариатор</option><option value="other">Другое</option></select></label>
          <label className="field"><span>Привод</span><select name="drive" defaultValue={search.drive || ""}><option value="">Любой</option><option value="front">Передний</option><option value="rear">Задний</option><option value="all">Полный</option><option value="other">Другое</option></select></label>
          </>}
          <label className="field"><span>Состояние</span><select name="condition" defaultValue={search.condition || ""}><option value="">Любое</option><option value="new">Новый</option><option value="used">{isGoods(category) ? "Б/у" : "С пробегом"}</option></select></label>
          <label className="field"><span>Область</span><select name="region_id" value={regionId} onChange={(event) => {
            setRegionId(event.target.value);
            setCityId("");
            setCities([]);
          }}><option value="">Вся Беларусь</option>{regionId && !regions.some((item) => item.id === regionId) && <option value={regionId}>Область выбрана</option>}{regions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <div className="field">
            <label htmlFor="search-city">Город</label>
            <select id="search-city" name="city_id" value={cityId} onChange={(event) => setCityId(event.target.value)} disabled={!cities.length && !cityId} aria-busy={citiesLoading} aria-describedby={citiesError ? "city-catalog-status" : undefined}>
              <option value="">{citiesLoading ? "Загрузка городов…" : cityId && citiesError ? "Города временно недоступны" : "Любой город"}</option>
              {cityId && !cities.some((item) => item.id === cityId) && <option value={cityId}>Город выбран</option>}
              {cities.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            {citiesError && <p className="catalog-error muted" id="city-catalog-status" role="status">Не удалось загрузить города. <button className="button button-secondary button-small" type="button" onClick={() => setCitiesRetry((attempt) => attempt + 1)}>Повторить</button></p>}
          </div>
          <label className="field filter-wide"><span>Продавец</span><select name="seller_type" defaultValue={search.seller_type || ""}><option value="">Любой продавец</option><option value="private">Частное лицо</option><option value="company">Компания</option></select></label>
          {category === "cars" && <>
          <label className="check-field filter-wide"><input type="checkbox" name="damaged" value="true" defaultChecked={search.damaged === "true"} /> Есть повреждения</label>
          <label className="check-field filter-wide"><input type="checkbox" name="parts_only" value="true" defaultChecked={search.parts_only === "true"} /> На запчасти</label>
          <label className="check-field filter-wide"><input type="checkbox" name="exchange" value="true" defaultChecked={search.exchange === "true"} /> Возможен обмен</label>
          <label className="check-field filter-wide"><input type="checkbox" name="bargaining" value="true" defaultChecked={search.bargaining === "true"} /> Возможен торг</label>
          <label className="check-field filter-wide"><input type="checkbox" name="credit" value="true" defaultChecked={search.credit === "true"} /> Возможен кредит</label>
          <label className="check-field filter-wide"><input type="checkbox" name="leasing" value="true" defaultChecked={search.leasing === "true"} /> Возможен лизинг</label>
          <label className="check-field filter-wide"><input type="checkbox" name="has_vin" value="true" defaultChecked={search.has_vin === "true"} /> Есть VIN</label>
          <label className="check-field filter-wide"><input type="checkbox" name="has_photos" value="true" defaultChecked={search.has_photos === "true"} /> Есть фотографии</label>
          <label className="field filter-wide"><span>Комплектация</span><select name="equipment" multiple size={5} defaultValue={search.equipment || []}><option value="abs">ABS</option><option value="esp">ESP</option><option value="airbags">Подушки безопасности</option><option value="air_conditioning">Кондиционер</option><option value="climate_control">Климат-контроль</option><option value="heated_seats">Подогрев сидений</option><option value="cruise_control">Круиз-контроль</option><option value="parking_sensors">Парктроники</option><option value="rear_camera">Камера заднего вида</option><option value="leather_seats">Кожаный салон</option><option value="carplay">Apple CarPlay</option><option value="android_auto">Android Auto</option></select><small className="muted">Можно выбрать несколько значений.</small></label>
          <label className="field"><span>Район</span><input name="district" maxLength={120} defaultValue={search.district || ""} /></label>
          <label className="field"><span>Время звонков</span><input name="call_hours" maxLength={80} defaultValue={search.call_hours || ""} /></label>
          </>}
          <input type="hidden" name="page_size" value={search.page_size || "25"} />
          <div className="filter-actions">
            <a className="button button-secondary filter-reset" href={categoryPath(category)}>Сбросить</a>
            <button className="button button-primary filter-apply" type="submit">{category === "cars" ? "Показать автомобили" : "Показать объявления"}</button>
          </div>
        </form>
      </div>
    </aside>
  );
}
