"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Check, LoaderCircle, RefreshCw, Search, X } from "lucide-react";
import { ApiClientError } from "@/lib/api";
import {
  catalogRequestsApi,
  type CatalogRequest,
  type CatalogRequestMatch,
  type CatalogRequestStatus,
} from "@/lib/catalog-requests";

const PAGE_SIZE = 25;

function statusLabel(status: CatalogRequestStatus) {
  if (status === "pending") return "Ожидает проверки";
  if (status === "resolved") return "Найден вариант";
  return "Отклонён";
}

function requestError(issue: unknown) {
  if (issue instanceof ApiClientError && issue.status === 409) {
    return "Запрос изменился. Обновите очередь и повторите решение.";
  }
  if (issue instanceof ApiClientError && issue.status === 429) {
    return "Слишком много попыток. Повторите позже.";
  }
  return "Не удалось выполнить действие. Проверьте данные и повторите попытку.";
}

function valueOrDash(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function matchSpecs(match: CatalogRequestMatch) {
  const specs = match.specs;
  if (!specs) return [];
  return [
    ["Код двигателя", specs.engine_code],
    ["Объём, л", specs.engine_l],
    ["Мощность, л.с.", specs.power_hp],
    ["Топливо", specs.fuel],
    ["Коробка", specs.transmission],
    ["Привод", specs.drive],
    ["Период выпуска", specs.production_period_raw],
  ].filter((item) => item[1] !== null && item[1] !== undefined && item[1] !== "");
}

export function CatalogRequestQueue() {
  const [status, setStatus] = useState<CatalogRequestStatus>("pending");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<CatalogRequest[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [queries, setQueries] = useState<Record<string, string>>({});
  const [searching, setSearching] = useState<Record<string, boolean>>({});
  const [searchErrors, setSearchErrors] = useState<Record<string, string>>({});
  const [searched, setSearched] = useState<Record<string, boolean>>({});
  const [matches, setMatches] = useState<Record<string, CatalogRequestMatch[]>>({});
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});
  const [acting, setActing] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const result = await catalogRequestsApi.listModeration({
        status,
        page,
        page_size: PAGE_SIZE,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => { void load(); }, [load]);

  async function searchMatches(event: FormEvent<HTMLFormElement>, requestId: string) {
    event.preventDefault();
    const query = (queries[requestId] || "").trim();
    if (!query) {
      setSearchErrors((current) => ({ ...current, [requestId]: "Введите название или характеристику." }));
      return;
    }
    setSearchErrors((current) => ({ ...current, [requestId]: "" }));
    setSearching((current) => ({ ...current, [requestId]: true }));
    setSearched((current) => ({ ...current, [requestId]: false }));
    try {
      const result = await catalogRequestsApi.searchMatches(requestId, query);
      setMatches((current) => ({ ...current, [requestId]: result.items }));
      setSelected((current) => ({ ...current, [requestId]: "" }));
      setSearched((current) => ({ ...current, [requestId]: true }));
    } catch {
      setSearchErrors((current) => ({
        ...current,
        [requestId]: "Не удалось найти варианты. Повторите поиск.",
      }));
    } finally {
      setSearching((current) => ({ ...current, [requestId]: false }));
    }
  }

  async function review(
    item: CatalogRequest,
    decision: "resolve" | "reject",
  ) {
    const reason = (reasons[item.id] || "").trim();
    const modificationId = selected[item.id];
    if (reason.length < 5 || (decision === "resolve" && !modificationId)) return;
    setActing((current) => ({ ...current, [item.id]: true }));
    setActionErrors((current) => ({ ...current, [item.id]: "" }));
    try {
      const result = await catalogRequestsApi.review(item.id, {
        expected_revision: item.revision,
        decision,
        reason,
        resolved_modification_id: decision === "resolve" ? modificationId : null,
      });
      if (status === "pending") {
        setItems((current) => current.filter((row) => row.id !== item.id));
        setTotal((current) => Math.max(0, current - 1));
        const lastPage = Math.max(1, Math.ceil(Math.max(0, total - 1) / PAGE_SIZE));
        if (page > lastPage) setPage(lastPage);
      } else {
        setItems((current) => current.map((row) => row.id === item.id ? result.request : row));
      }
    } catch (issue) {
      setActionErrors((current) => ({ ...current, [item.id]: requestError(issue) }));
      if (issue instanceof ApiClientError && issue.status === 409) await load();
    } finally {
      setActing((current) => ({ ...current, [item.id]: false }));
    }
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section className="section" aria-label="Очередь запросов каталога">
      <div className="section-heading">
        <div>
          <h2>Запросы продавцов</h2>
          <p className="muted">Одобрение связывает запрос с существующей записью и возвращает продавцу рекомендацию. Объявление и справочник здесь не изменяются.</p>
        </div>
        <button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}>
          {loading ? <LoaderCircle size={16} /> : <RefreshCw size={16} />} Обновить
        </button>
      </div>

      <div className="form-grid admin-catalog-request-filters">
        <label className="field">
          <span>Статус запросов</span>
          <select aria-label="Статус запросов" value={status} onChange={(event) => { setPage(1); setStatus(event.target.value as CatalogRequestStatus); }}>
            <option value="pending">Ожидают проверки</option>
            <option value="resolved">Найден вариант</option>
            <option value="rejected">Отклонены</option>
          </select>
        </label>
        <p className="muted" role="status">{total} запросов</p>
      </div>

      {loading && <p className="notice" role="status">Загружаем очередь…</p>}
      {!loading && loadError && <div className="notice" role="alert"><p>Не удалось загрузить очередь. Проверьте доступ к API.</p><button className="button button-secondary" type="button" onClick={() => void load()}>Повторить</button></div>}
      {!loading && !loadError && items.length === 0 && <p className="empty-state">Запросов пока нет.</p>}

      {!loading && !loadError && items.map((item) => {
        const catalog = item.snapshot.catalog;
        const parameters = item.snapshot.manual_parameters;
        const reviewReason = reasons[item.id]?.trim() || "";
        return (
          <article className="admin-summary-card catalog-request-card" key={item.id}>
            <header className="section-heading">
              <div>
                <p className="eyebrow">{statusLabel(item.status)} · ревизия {item.revision}</p>
                <h3>{item.manual_modification_name || "Название модификации не указано"}</h3>
                <p className="muted">Объявление {item.listing_id} · ревизия {item.listing_revision}</p>
              </div>
              <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString("ru-BY")}</time>
            </header>

            <dl className="admin-count-list catalog-request-snapshot">
              <li><span>Марка</span><strong>{catalog.make?.name || item.snapshot.manual_identity.make || "—"}</strong></li>
              <li><span>Модель</span><strong>{catalog.model?.name || item.snapshot.manual_identity.model || "—"}</strong></li>
              <li><span>Поколение</span><strong>{catalog.generation?.name || "Не выбрано"}</strong></li>
              <li><span>Кузов</span><strong>{catalog.body_variant?.name || catalog.body_type?.name || "—"}</strong></li>
              <li><span>Год / пробег</span><strong>{valueOrDash(parameters.year)} · {valueOrDash(parameters.mileage_km)} км</strong></li>
              <li><span>Двигатель / мощность</span><strong>{valueOrDash(parameters.engine_volume_l)} л · {valueOrDash(parameters.power_hp)} л.с.</strong></li>
              <li><span>Топливо / КПП / привод</span><strong>{valueOrDash(parameters.fuel)} · {valueOrDash(parameters.transmission)} · {valueOrDash(parameters.drive)}</strong></li>
            </dl>
            {item.note && <p className="notice"><strong>Комментарий продавца:</strong> {item.note}</p>}
            {item.resolved_modification && <p className="notice"><strong>Рекомендация:</strong> {item.resolved_modification.name} · {item.resolved_modification.generation.name}</p>}
            {item.review_reason && <p className="muted"><strong>Причина решения:</strong> {item.review_reason}</p>}

            {item.status === "pending" && <>
              <form className="catalog-request-search" onSubmit={(event) => void searchMatches(event, item.id)}>
                <label className="field">
                  <span>Поиск по названию или характеристике</span>
                  <input
                    aria-label="Название или характеристика"
                    value={queries[item.id] || ""}
                    onChange={(event) => setQueries((current) => ({ ...current, [item.id]: event.target.value }))}
                    maxLength={100}
                  />
                </label>
                <button className="button button-secondary" type="submit" disabled={searching[item.id]}>
                  {searching[item.id] ? <LoaderCircle size={16} /> : <Search size={16} />} Найти совпадение
                </button>
              </form>
              {searchErrors[item.id] && <p className="inline-error" role="alert">{searchErrors[item.id]}</p>}
              {searching[item.id] && <p className="muted" role="status">Ищем существующие варианты…</p>}
              {searched[item.id] && (matches[item.id] || []).length === 0 && <p className="notice">Совпадений не найдено. Здесь связываются только существующие записи; для нового ряда нужны отдельно подтверждённые источник и процедура.</p>}
              {(matches[item.id] || []).map((candidate) => {
                const specs = matchSpecs(candidate);
                return <button
                  className="catalog-request-match"
                  type="button"
                  key={candidate.id}
                  aria-pressed={selected[item.id] === candidate.id}
                  onClick={() => setSelected((current) => ({ ...current, [item.id]: candidate.id }))}
                >
                  <span className="catalog-request-match-heading"><strong>{candidate.name}</strong>{selected[item.id] === candidate.id && <Check size={17} />}</span>
                  <span>{candidate.make.name} · {candidate.model.name} · {candidate.generation.name}</span>
                  {specs.length > 0 && <dl>{specs.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}</dl>}
                  {candidate.source?.name && <span className="muted">Источник в каталоге: {candidate.source.name}</span>}
                </button>;
              })}

              <label className="field">
                <span>Причина решения</span>
                <textarea
                  aria-label="Причина решения"
                  value={reasons[item.id] || ""}
                  onChange={(event) => setReasons((current) => ({ ...current, [item.id]: event.target.value }))}
                  minLength={5}
                  maxLength={2000}
                  rows={3}
                  required
                />
              </label>
              {actionErrors[item.id] && <p className="inline-error" role="alert">{actionErrors[item.id]}</p>}
              <div className="form-actions">
                <button
                  className="button button-primary"
                  type="button"
                  disabled={acting[item.id] || reviewReason.length < 5 || !selected[item.id]}
                  onClick={() => void review(item, "resolve")}
                >
                  {acting[item.id] ? <LoaderCircle size={16} /> : <Check size={16} />} Связать существующую модификацию
                </button>
                <button
                  className="button button-secondary"
                  type="button"
                  disabled={acting[item.id] || reviewReason.length < 5}
                  onClick={() => void review(item, "reject")}
                >
                  <X size={16} /> Отклонить с причиной
                </button>
              </div>
            </>}
          </article>
        );
      })}

      {!loading && !loadError && total > PAGE_SIZE && <div className="form-actions">
        <button className="button button-secondary" type="button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Назад</button>
        <span className="muted">Страница {page} из {pageCount}</span>
        <button className="button button-secondary" type="button" disabled={page >= pageCount} onClick={() => setPage((current) => current + 1)}>Вперёд</button>
      </div>}
    </section>
  );
}
