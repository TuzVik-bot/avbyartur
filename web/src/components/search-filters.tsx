"use client";

import styles from "./search-filters.module.css";

import { useEffect, useRef, useState } from "react";
import { Filter, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { matchesCatalogSearch } from "@/lib/catalog-search";
import { modelDisplayName } from "@/lib/format";
import { catalogIds } from "@/lib/search-state";
import { api } from "@/lib/api";
import type { CatalogCity, CatalogItem, CatalogModification, ListingSearch } from "@/lib/types";
import { getListingSubcategories } from "@/lib/listing-subcategories";

const emptyCatalogItems: CatalogItem[] = [];
const emptyModifications: CatalogModification[] = [];

function citiesForRegion(cities: CatalogCity[], regionId: string) {
  return regionId ? cities.filter((city) => city.region_id === regionId) : cities;
}

function modelLabel(item: CatalogItem, makes: CatalogItem[]) {
  const make = makes.find((entry) => entry.id === item.make_id)?.name;
  if (!make) return item.name;
  return modelDisplayName(make, item.name);
}

function offerLabel(count: number) {
  const plural = new Intl.PluralRules("ru").select(count);
  const noun = plural === "one" ? "предложение" : plural === "few" ? "предложения" : "предложений";
  return `${count.toLocaleString("ru-BY")} ${noun}`;
}

function searchFromFilterForm(form: HTMLFormElement): ListingSearch {
  const search: ListingSearch = {};
  const excluded = new Set(["page", "page_size", "sort"]);
  new FormData(form).forEach((entry, key) => {
    if (excluded.has(key) || typeof entry !== "string" || !entry.trim()) return;
    if (key === "equipment") {
      search.equipment = [...(search.equipment || []), entry.trim()];
      return;
    }
    (search as Record<string, string | string[]>)[key] = entry.trim();
  });
  return search;
}

export function SearchFilters({ search, makes, initialModels, initialGenerations, initialModifications = emptyModifications, regions, initialCities, bodyTypes, priceOperationsAvailable = true, initialCount }: {
  search: ListingSearch;
  makes: CatalogItem[];
  initialModels: CatalogItem[];
  initialGenerations?: CatalogItem[];
  initialModifications?: CatalogModification[];
  regions: CatalogItem[];
  initialCities: CatalogCity[];
  bodyTypes: CatalogItem[];
  priceOperationsAvailable?: boolean;
  initialCount?: number | null;
}) {
  const categoryCode = search.category_code || "cars";
  const subcategories = getListingSubcategories(categoryCode);
  const isCarCategory = categoryCode === "cars";
  const hasVehicleYear = ["cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft"].includes(categoryCode);
  const initialRegionId = search.region_id || initialCities.find((city) => city.id === search.city_id)?.region_id || "";
  const [open, setOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [resultCount, setResultCount] = useState<number | null>(initialCount ?? null);
  const [countLoading, setCountLoading] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const focusBeforeOpen = useRef<HTMLElement | null>(null);
  const countRequestId = useRef(0);
  const [makeIds, setMakeIds] = useState(search.make_ids || search.make_id || "");
  const [modelIds, setModelIds] = useState(search.model_ids || search.model_id || "");
  const selectedMakes = makeIds.split(",").filter(Boolean);
  const selectedModels = modelIds.split(",").filter(Boolean);
  const validMakeIds = catalogIds(makeIds);
  const validModelIds = catalogIds(modelIds);
  const validCatalogSelection = (!makeIds || validMakeIds.length > 0) && (!modelIds || validModelIds.length > 0);
  const modelId = validCatalogSelection && validMakeIds.length === 1 && validModelIds.length === 1 ? validModelIds[0] : "";
  const [makeQuery, setMakeQuery] = useState("");
  const [modelQuery, setModelQuery] = useState("");
  const [generationId, setGenerationId] = useState(search.generation_id || "");
  const [bodyVariantId, setBodyVariantId] = useState(search.body_variant_id || "");
  const [modificationId, setModificationId] = useState(search.modification_id || "");
  const previousCategoryCode = useRef(categoryCode);
  const [regionId, setRegionId] = useState(initialRegionId);
  const [cityId, setCityId] = useState(search.city_id || "");
  const [models, setModels] = useState(initialModels);
  const [searchedModels, setSearchedModels] = useState<CatalogItem[]>([]);
  const [modelSearchLoading, setModelSearchLoading] = useState(false);
  const [modelSearchError, setModelSearchError] = useState(false);
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
  const firstMakeId = useRef<string | undefined>(search.make_ids || search.make_id || "");
  const firstGenerationModelId = useRef<string | undefined>(initialGenerations !== undefined && (!search.generation_id || initialGenerations.some((item) => item.id === search.generation_id)) ? (search.model_ids || search.model_id || "").split(",").length === 1 ? (search.model_ids || search.model_id || "") : "" : undefined);
  const firstRegionId = useRef<string | undefined>(initialRegionId && initialCities.some((city) => city.region_id === initialRegionId) ? initialRegionId : undefined);
  const firstGenerationId = useRef<string | undefined>(search.generation_id || "");

  useEffect(() => {
    overlayRef.current?.querySelector("form")?.dispatchEvent(new Event("change", { bubbles: true }));
  }, [makeIds, modelIds]);

  useEffect(() => {
    setResultCount(initialCount ?? null);
  }, [initialCount]);

  useEffect(() => {
    const form = overlayRef.current?.querySelector("form");
    if (!form) return;
    let active = true;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const updateCount = (event: Event) => {
      // Catalog text and picker controls only edit the available options.
      // Recount after make_ids/model_ids change, via the form event above.
      // Updating state here before React's delegated onChange runs can reset
      // the controlled search input and swallow the character being typed.
      const target = event.target;
      if ((target instanceof HTMLInputElement || target instanceof HTMLSelectElement) && !target.name) return;
      if (timeout) clearTimeout(timeout);
      const nextSearch = searchFromFilterForm(form);
      const currentRequest = ++countRequestId.current;
      setCountLoading(false);
      if (!Object.keys(nextSearch).length) {
        setResultCount(initialCount ?? null);
        return;
      }
      setResultCount(null);
      timeout = setTimeout(async () => {
        setCountLoading(true);
        try {
          const response = await api.listingCount(nextSearch);
          if (active && countRequestId.current === currentRequest) setResultCount(response.total);
        } catch {
          if (active && countRequestId.current === currentRequest) setResultCount(null);
        } finally {
          if (active && countRequestId.current === currentRequest) setCountLoading(false);
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
  }, [initialCount, search]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 800px)");
    const update = () => {
      setIsMobile(media.matches);
      if (media.matches) setOpen(false);
    };
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  useEffect(() => {
    if (!isMobile || !open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(overlayRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      ) || [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !overlayRef.current?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !overlayRef.current?.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      (focusBeforeOpen.current || triggerRef.current)?.focus();
    };
  }, [isMobile, open]);

  useEffect(() => {
    const categoryChanged = previousCategoryCode.current !== categoryCode;
    previousCategoryCode.current = categoryCode;
    const incomingMakes = search.make_ids || search.make_id || "";
    const nextMakeIds = categoryChanged ? catalogIds(incomingMakes).filter((id) => makes.some((item) => item.id === id)).join(",") : incomingMakes;
    const incomingModels = search.model_ids || search.model_id || "";
    firstMakeId.current = categoryChanged ? undefined : incomingModels && !catalogIds(incomingModels).every((id) => initialModels.some((item) => item.id === id)) ? undefined : nextMakeIds;
    firstGenerationId.current = categoryChanged ? "" : search.generation_id || "";
    firstGenerationModelId.current = categoryChanged ? undefined : initialGenerations !== undefined && (!search.generation_id || initialGenerations.some((item) => item.id === search.generation_id)) ? catalogIds(incomingModels).length === 1 ? incomingModels : "" : undefined;
    firstRegionId.current = initialRegionId && initialCities.some((city) => city.region_id === initialRegionId) ? initialRegionId : undefined;
    setModels(categoryChanged ? [] : initialModels);
    setModelsLoading(false);
    setModelsError(false);
    setMakeIds(nextMakeIds);
    setModelIds(categoryChanged ? "" : search.model_ids || search.model_id || "");
    setGenerationId(categoryChanged ? "" : search.generation_id || "");
    setGenerations(categoryChanged ? emptyCatalogItems : initialGenerations || emptyCatalogItems);
    setGenerationsLoading(false);
    setGenerationsError(false);
    setBodyVariantId(categoryChanged ? "" : search.body_variant_id || "");
    setModificationId(categoryChanged ? "" : search.modification_id || "");
    if (categoryChanged) setBodyVariants(emptyCatalogItems);
    setModifications(categoryChanged ? emptyModifications : initialModifications);
    setModificationsLoading(false);
    setModificationsError(false);
    setRegionId(initialRegionId);
    setCityId(search.city_id || "");
    setCities(citiesForRegion(initialCities, initialRegionId));
    setCitiesLoading(false);
    setCitiesError(false);
  }, [categoryCode, makes, search.make_id, search.model_id, search.make_ids, search.model_ids, search.generation_id, search.body_variant_id, search.modification_id, search.region_id, search.city_id, initialRegionId, initialGenerations, initialModifications, initialModels, initialCities]);

  useEffect(() => {
    setCities(citiesForRegion(initialCities, regionId));
  }, [initialCities, regionId]);

  useEffect(() => {
    if (firstMakeId.current === makeIds) {
      firstMakeId.current = undefined;
      return;
    }
    let active = true;
    if (!makeIds || !validCatalogSelection) {
      setModels([]);
      setModelsLoading(false);
      setModelsError(false);
      return () => { active = false; };
    }
    setModels((current) => current.filter((item) => selectedModels.includes(item.id)));
    setModelsLoading(true);
    setModelsError(false);
    Promise.all([
      ...validMakeIds.map((id) => api.catalog("models", { make_id: id, category_code: categoryCode })),
      ...(validModelIds.length ? [api.catalog("models", { model_ids: validModelIds.join(","), category_code: categoryCode })] : [])
    ])
      .then((groups) => { if (active) setModels((current) => [...new Map([...current.filter((item) => selectedModels.includes(item.id)), ...groups.flatMap((group) => group.items)].map((item) => [item.id, item])).values()]); })
      .catch(() => { if (active) setModelsError(true); })
      .finally(() => { if (active) setModelsLoading(false); });
    return () => { active = false; };
  }, [makeIds, modelIds, modelsRetry, categoryCode]);

  useEffect(() => {
    let active = true;
    const query = modelQuery.trim();
    setSearchedModels([]);
    setModelSearchError(false);
    setModelSearchLoading(false);
    if (!makeIds || !validCatalogSelection || !query) return () => { active = false; };
    setModelSearchLoading(true);
    const timer = setTimeout(() => {
      Promise.all(validMakeIds.map((id) => api.catalog("models", { make_id: id, q: query, category_code: categoryCode })))
        .then((groups) => { if (active) setSearchedModels(groups.flatMap((group) => group.items)); })
        .catch(() => { if (active) setModelSearchError(true); })
        .finally(() => { if (active) setModelSearchLoading(false); });
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [makeIds, modelIds, modelQuery, modelsRetry, categoryCode]);

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

  const activeFilterCount = Object.entries(search).filter(([key, value]) =>
    !["currency", "page", "page_size", "sort"].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value))
  ).length;
  const mobileDialogOpen = isMobile && open;

  return (
    <aside className={`search-filters ${open ? "is-open" : ""}`} aria-label="Фильтры поиска">
      <button ref={triggerRef} className="button button-secondary filter-toggle" type="button" aria-expanded={open} aria-controls="search-filter-panel" onClick={() => {
        if (!open) focusBeforeOpen.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        setOpen(!open);
      }}>
        <SlidersHorizontal size={17} /> <span>Фильтры{activeFilterCount ? ` · ${activeFilterCount}` : ""}</span> <Filter size={15} />
      </button>
      <div
        ref={overlayRef}
        className={`filter-overlay ${mobileDialogOpen ? "is-open" : ""}`}
        role={mobileDialogOpen ? "dialog" : undefined}
        aria-modal={mobileDialogOpen ? "true" : undefined}
        aria-hidden={isMobile && !open ? "true" : undefined}
        aria-labelledby="search-filter-heading"
        onClick={(event) => { if (event.target === event.currentTarget) setOpen(false); }}
      >
      <div id="search-filter-panel" className={`filter-panel ${open ? "is-open" : ""}`}>
        <div className="filter-panel-heading">
          <h2 id="search-filter-heading">Параметры поиска</h2>
          <button ref={closeRef} className="icon-button filter-close" type="button" aria-label="Закрыть фильтры" onClick={() => setOpen(false)}><X size={19} /></button>
        </div>
        <form key={JSON.stringify(search)} action="/cars" method="get" className="filter-form" onSubmit={() => { if (mobileDialogOpen) setOpen(false); }}>
          <div className="filter-grid">
          {subcategories.length > 0 && <label className="field filter-wide">
            <span>Подкатегория</span>
            <select name="subcategory" defaultValue={search.subcategory || ""}>
              <option value="">Все подкатегории</option>
              {subcategories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>}
          <input type="hidden" name="category_code" value={categoryCode} />
          {hasVehicleYear && <>
          <div className="field filter-wide">
            <span>Марка</span>
            <input type="hidden" name="make_ids" value={makeIds} />
            <details className={styles.catalogPicker}>
              <summary>Выбрать марки{selectedMakes.length ? ` (${selectedMakes.length})` : ""}</summary>
              <input type="search" aria-label="Поиск марки" onKeyDown={(event) => { if (event.key === "Enter" || event.key === "ArrowDown") { event.preventDefault(); const first = event.currentTarget.parentElement?.querySelector<HTMLButtonElement>("button"); if (event.key === "Enter") first?.click(); else first?.focus(); } }} placeholder="Начните вводить марку" value={makeQuery} onChange={(event) => setMakeQuery(event.target.value)} />
              <div className={styles.catalogOptions} aria-label="Марки">{makes.filter((item) => !selectedMakes.includes(item.id) && matchesCatalogSearch(item, makeQuery)).map((item) => <button type="button" key={item.id} onClick={() => { if (selectedMakes.length >= 50) return; setMakeIds([...selectedMakes, item.id].join(",")); setMakeQuery(""); changeGeneration(""); }}>{item.name}</button>)}</div>
            </details>
            <div className="active-filters">{selectedMakes.map((id) => <button className="filter-chip" type="button" key={id} onClick={() => {
              const removedModels = new Set([...models, ...searchedModels].filter((item) => item.make_id === id).map((item) => item.id));
              setMakeIds(selectedMakes.filter((item) => item !== id).join(","));
              setModelIds(selectedMakes.length > 1 ? selectedModels.filter((item) => !removedModels.has(item)).join(",") : "");
              changeGeneration("");
            }}>{makes.find((item) => item.id === id)?.name || "Марка выбрана"} <X size={13} aria-hidden="true" /></button>)}</div>
          </div>
          <div className="filter-wide">
            <div className="field">
              <span>Модель</span>
              <input type="hidden" name="model_ids" value={modelIds} />
              <details className={styles.catalogPicker}>
                <summary aria-disabled={!makeIds}>{!makeIds ? "Сначала выберите марку" : `Выбрать модели${selectedModels.length ? ` (${selectedModels.length})` : ""}`}</summary>
                <input type="search" aria-label="Поиск модели" onKeyDown={(event) => { if (event.key === "Enter" || event.key === "ArrowDown") { event.preventDefault(); const first = event.currentTarget.parentElement?.querySelector<HTMLButtonElement>("button"); if (event.key === "Enter") first?.click(); else first?.focus(); } }} placeholder="Начните вводить модель" value={modelQuery} onChange={(event) => setModelQuery(event.target.value)} disabled={!makeIds} />
                <div className={styles.catalogOptions} aria-label="Модели" aria-busy={modelsLoading || modelSearchLoading}>{[...new Map([...models, ...searchedModels].map((item) => [item.id, item])).values()].filter((item) => selectedMakes.includes(item.make_id || "") && !selectedModels.includes(item.id) && matchesCatalogSearch(item, modelQuery)).map((item) => <button type="button" key={item.id} onClick={() => { if (selectedModels.length >= 50) return; setModels((current) => current.some((entry) => entry.id === item.id) ? current : [...current, item]); setModelIds([...selectedModels, item.id].join(",")); setModelQuery(""); changeGeneration(""); }}>{modelLabel(item, makes)}</button>)}</div>
              </details>
              <div className="active-filters">{selectedModels.map((id) => <button className="filter-chip" type="button" key={id} onClick={() => { setModelIds(selectedModels.filter((item) => item !== id).join(",")); changeGeneration(""); }}>{[...models, ...searchedModels].find((item) => item.id === id)?.name || "Модель выбрана"} <X size={13} aria-hidden="true" /></button>)}</div>
            </div>
            {modelSearchLoading && <p className="muted" role="status">Поиск моделей…</p>}
            {(modelsError || modelSearchError) && <p className="catalog-error muted" id="model-catalog-status" role="status">Не удалось загрузить модели. <button className="button button-secondary button-small" type="button" onClick={() => setModelsRetry((attempt) => attempt + 1)}>Повторить</button></p>}
          </div>
          {isCarCategory && <div className="filter-wide">
            <label className="field">
              <span>Поколение</span>
              <select name="generation_id" value={generationId} onChange={(event) => changeGeneration(event.target.value)} disabled={(generationsLoading && !generationId) || (!generations.length && !generationId)} aria-busy={generationsLoading} aria-describedby={generationsError ? "generation-catalog-status" : undefined}>
                <option value="">{!modelId ? "Любое поколение" : generationsLoading ? "Загрузка поколений…" : generationsError ? "Поколения временно недоступны" : generations.length ? "Любое поколение" : "Нет доступных поколений"}</option>
                {generationId && !generations.some((item) => item.id === generationId) && <option value={generationId}>Поколение выбрано</option>}
                {generations.map((item) => <option key={item.id} value={item.id}>{item.name}{item.year_from ? ` · ${item.year_from}${item.year_to ? `–${item.year_to}` : ""}` : ""}</option>)}
              </select>
            </label>
            {generationsError && <p className="catalog-error muted" id="generation-catalog-status" role="status">Не удалось загрузить поколения. <button className="button button-secondary button-small" type="button" onClick={() => setGenerationsRetry((attempt) => attempt + 1)}>Повторить</button></p>}
          </div>}
          </>}
          <fieldset className="filter-wide" disabled={!priceOperationsAvailable}>
            <legend className="field-label">Цена, {search.currency || "BYN"}</legend>
            <div className="range-fields">
              <input name="price_min" inputMode="numeric" type="number" min="1" aria-label={`Цена от, ${search.currency || "BYN"}`} placeholder="От" defaultValue={search.price_min || ""} />
              <input name="price_max" inputMode="numeric" type="number" min="1" aria-label={`Цена до, ${search.currency || "BYN"}`} placeholder="До" defaultValue={search.price_max || ""} />
            </div>
          </fieldset>
          <input type="hidden" name="currency" value={search.currency || "BYN"} />
          {search.q && <input type="hidden" name="q" value={search.q} />}
          {search.sort && <input type="hidden" name="sort" value={search.sort} />}
          {hasVehicleYear && <fieldset className="filter-wide">
            <legend className="field-label">Год выпуска</legend>
            <div className="range-fields">
              <input name="year_min" inputMode="numeric" type="number" min="1886" aria-label="Год от" placeholder="От" defaultValue={search.year_min || ""} />
              <input name="year_max" inputMode="numeric" type="number" min="1886" aria-label="Год до" placeholder="До" defaultValue={search.year_max || ""} />
            </div>
          </fieldset>}
          <label className="field"><span>Область</span><select name="region_id" value={regionId} onChange={(event) => {
            setRegionId(event.target.value);
            setCityId("");
            setCities([]);
          }}><option value="">Вся Беларусь</option>{regionId && !regions.some((item) => item.id === regionId) && <option value={regionId}>Область выбрана</option>}{regions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          {isCarCategory && <label className="field"><span>Коробка</span><select name="transmission" defaultValue={search.transmission || ""}><option value="">Любая</option><option value="manual">Механика</option><option value="automatic">Автомат</option><option value="robot">Робот</option><option value="cvt">Вариатор</option><option value="other">Другое</option></select></label>}
          <details className={styles.additional}><summary>Дополнительные параметры</summary>
            <div className={styles.additionalGrid}>
              {isCarCategory && <>
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
          {isCarCategory && <fieldset className="filter-wide">
            <legend className="field-label">Пробег, км</legend>
            <div className="range-fields">
              <input name="mileage_min" inputMode="numeric" type="number" min="0" aria-label="Пробег от, км" placeholder="От" defaultValue={search.mileage_min || ""} />
              <input name="mileage_max" inputMode="numeric" type="number" min="0" aria-label="Пробег до, км" placeholder="До" defaultValue={search.mileage_max || ""} />
            </div>
          </fieldset>}
          {isCarCategory && <fieldset className="filter-wide"><legend className="field-label">Объём двигателя, л</legend><div className="range-fields"><input name="engine_volume_min" inputMode="decimal" type="number" min="0" max="20" step="0.1" aria-label="Объём двигателя от, л" placeholder="От" defaultValue={search.engine_volume_min || ""} /><input name="engine_volume_max" inputMode="decimal" type="number" min="0" max="20" step="0.1" aria-label="Объём двигателя до, л" placeholder="До" defaultValue={search.engine_volume_max || ""} /></div></fieldset>}
          {isCarCategory && <fieldset className="filter-wide"><legend className="field-label">Мощность, л.с.</legend><div className="range-fields"><input name="power_min" inputMode="numeric" type="number" min="1" max="2500" aria-label="Мощность от, л.с." placeholder="От" defaultValue={search.power_min || ""} /><input name="power_max" inputMode="numeric" type="number" min="1" max="2500" aria-label="Мощность до, л.с." placeholder="До" defaultValue={search.power_max || ""} /></div></fieldset>}
          {isCarCategory && <>
          <label className="field"><span>Топливо</span><select name="fuel" defaultValue={search.fuel || ""}><option value="">Любое</option><option value="petrol">Бензин</option><option value="diesel">Дизель</option><option value="hybrid">Гибрид</option><option value="electric">Электро</option><option value="lpg">Газ</option><option value="other">Другое</option></select></label>
          <label className="field"><span>Привод</span><select name="drive" defaultValue={search.drive || ""}><option value="">Любой</option><option value="front">Передний</option><option value="rear">Задний</option><option value="all">Полный</option><option value="other">Другое</option></select></label>
          </>}
          <label className="field"><span>Состояние</span><select name="condition" defaultValue={search.condition || ""}><option value="">Любое</option><option value="new">Новый</option><option value="used">С пробегом</option></select></label>

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
          {isCarCategory && <label className="check-field filter-wide"><input type="checkbox" name="in_transit" value="true" defaultChecked={search.in_transit === "true"} /> Авто в пути</label>}
          <label className="check-field filter-wide"><input type="checkbox" name="damaged" value="true" defaultChecked={search.damaged === "true"} /> Есть повреждения</label>
          <label className="check-field filter-wide"><input type="checkbox" name="parts_only" value="true" defaultChecked={search.parts_only === "true"} /> На запчасти</label>
          <label className="check-field filter-wide"><input type="checkbox" name="exchange" value="true" defaultChecked={search.exchange === "true"} /> Возможен обмен</label>
          <label className="check-field filter-wide"><input type="checkbox" name="bargaining" value="true" defaultChecked={search.bargaining === "true"} /> Возможен торг</label>
          <label className="check-field filter-wide"><input type="checkbox" name="credit" value="true" defaultChecked={search.credit === "true"} /> Возможен кредит</label>
          <label className="check-field filter-wide"><input type="checkbox" name="leasing" value="true" defaultChecked={search.leasing === "true"} /> Возможен лизинг</label>
          {isCarCategory && <label className="check-field filter-wide"><input type="checkbox" name="has_vin" value="true" defaultChecked={search.has_vin === "true"} /> Есть VIN</label>}
          <label className="check-field filter-wide"><input type="checkbox" name="has_photos" value="true" defaultChecked={search.has_photos === "true"} /> Есть фотографии</label>
          {isCarCategory && <label className="field filter-wide"><span>Комплектация</span><select name="equipment" multiple size={5} defaultValue={search.equipment || []}><option value="abs">ABS</option><option value="esp">ESP</option><option value="airbags">Подушки безопасности</option><option value="air_conditioning">Кондиционер</option><option value="climate_control">Климат-контроль</option><option value="heated_seats">Подогрев сидений</option><option value="cruise_control">Круиз-контроль</option><option value="parking_sensors">Парктроники</option><option value="rear_camera">Камера заднего вида</option><option value="leather_seats">Кожаный салон</option><option value="carplay">Apple CarPlay</option><option value="android_auto">Android Auto</option></select><small className="muted">Можно выбрать несколько значений.</small></label>}
          <label className="field"><span>Район</span><input name="district" maxLength={120} defaultValue={search.district || ""} /></label>
          <label className="field"><span>Время звонков</span><input name="call_hours" maxLength={80} defaultValue={search.call_hours || ""} /></label>
            </div>
          </details>
          <input type="hidden" name="page_size" value={search.page_size || "25"} />
          </div>
          <div className="filter-wide filter-apply-wrap">
            <button className="button button-primary filter-apply" type="submit">{countLoading ? "Подбираем…" : resultCount === null ? `Показать ${categoryCode === "cars" ? "автомобили" : "предложения"}` : `Показать ${offerLabel(resultCount)}`}</button>
            <span className="filter-result-count" role="status" aria-live="polite" data-count-state={resultCount === null ? "generic" : "count"}>
              {countLoading ? "Подбираем подходящие предложения" : resultCount === null ? "Количество уточнится после применения фильтров" : `Найдено ${offerLabel(resultCount)}`}
            </span>
          </div>
        </form>
      </div>
      </div>
    </aside>
  );
}
