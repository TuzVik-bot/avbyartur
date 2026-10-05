"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";

export function HomeSearch({ makes, priceOperationsAvailable }: { makes: CatalogItem[]; priceOperationsAvailable: boolean }) {
  const [makeId, setMakeId] = useState("");
  const [modelId, setModelId] = useState("");
  const [models, setModels] = useState<CatalogItem[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    if (!makeId) {
      setModels([]);
      setModelsLoading(false);
      setModelsError(false);
      return () => { active = false; };
    }
    setModels([]);
    setModelId("");
    setModelsLoading(true);
    setModelsError(false);
    api.catalog("models", { make_id: makeId })
      .then((result) => { if (active) setModels(result.items); })
      .catch(() => { if (active) { setModels([]); setModelsError(true); } })
      .finally(() => { if (active) setModelsLoading(false); });
    return () => { active = false; };
  }, [makeId, retry]);

  return (
    <form className="search-strip home-search" action="/cars" method="get" role="search">
      <label className="field"><span>Марка</span><select name="make_id" value={makeId} onChange={(event) => { setModelId(""); setMakeId(event.target.value); }}><option value="">Любая марка</option>{makes.map((make) => <option key={make.id} value={make.id}>{make.name}</option>)}</select></label>
      <label className="field"><span>Модель</span><select name="model_id" value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={!makeId || modelsLoading || (!models.length && !modelsError)} aria-busy={modelsLoading} aria-describedby={modelsError ? "home-model-status" : undefined}>
        <option value="">{!makeId ? "Любая модель" : modelsLoading ? "Загрузка моделей…" : modelsError ? "Модели временно недоступны" : models.length ? "Любая модель" : "Нет доступных моделей"}</option>
        {models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
      </select></label>
      {modelsError && <p className="catalog-error home-model-error" id="home-model-status" role="status">Не удалось загрузить модели. <button className="button button-secondary button-small" type="button" onClick={() => setRetry((count) => count + 1)}>Повторить</button></p>}
      <label className="field"><span>Цена до, BYN</span><input name="price_max" inputMode="numeric" type="number" min="1" placeholder="Без ограничения" disabled={!priceOperationsAvailable} aria-describedby={!priceOperationsAvailable ? "home-price-status" : undefined} /></label>
      {!priceOperationsAvailable && <p className="catalog-error home-price-note" id="home-price-status" role="status">Фильтр по цене временно недоступен: нет подтверждённого курса НБРБ за последние 72 часа. Цены показаны в исходной валюте.</p>}
      <button className="button home-search-button" type="submit"><Search size={18} /> Найти</button>
    </form>
  );
}
