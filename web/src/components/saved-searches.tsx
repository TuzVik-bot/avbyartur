"use client";

import { Bell, Check, ExternalLink, Pause, Play, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiRequest, ApiClientError } from "@/lib/api";

export type SavedSearchStatus = "active" | "paused";
export type SavedSearchChannel = "email" | "web";
export type SavedSearchFrequency = "instant" | "daily" | "weekly";

export type SavedSearch = {
  id: string;
  name: string;
  url: string;
  filters: Record<string, unknown>;
  status: SavedSearchStatus;
  revision: number;
  notifications_enabled: boolean;
  notification_channel: SavedSearchChannel | null;
  notification_frequency: SavedSearchFrequency;
  notification?: {
    enabled?: boolean;
    channel?: SavedSearchChannel | null;
    frequency?: SavedSearchFrequency;
  } | null;
  created_at: string;
  updated_at: string;
};

type SavedSearchDraft = Pick<SavedSearch, "notifications_enabled" | "notification_channel" | "notification_frequency">;

const frequencyLabels: Record<Exclude<SavedSearchFrequency, "weekly">, string> = { instant: "Сразу", daily: "Раз в день" };
const filterLabels: Record<string, string> = {
  q: "Поиск",
  make_id: "Марка",
  model_id: "Модель",
  generation_id: "Поколение",
  modification_id: "Модификация",
  body_variant_id: "Кузов",
  price_min: "Цена от",
  price_max: "Цена до",
  currency: "Валюта",
  year_min: "Год от",
  year_max: "Год до",
  mileage_min: "Пробег от",
  mileage_max: "Пробег до",
  fuel: "Топливо",
  transmission: "Коробка",
  drive: "Привод",
  body_type: "Тип кузова",
  damaged: "После ДТП",
  parts_only: "На запчасти",
  condition: "Состояние",
  region_id: "Регион",
  city_id: "Город",
  seller_type: "Продавец"
};

function randomIdempotencyKey() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `saved-search-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function normalizeSavedSearch(value: SavedSearch): SavedSearch {
  const notification = value.notification || {};
  return {
    ...value,
    url: value.url || (value as SavedSearch & { search_url?: string }).search_url || "/cars",
    filters: value.filters && typeof value.filters === "object" ? value.filters : {},
    notifications_enabled: value.notifications_enabled ?? notification.enabled ?? false,
    notification_channel: value.notification_channel ?? notification.channel ?? null,
    notification_frequency: value.notification_frequency ?? notification.frequency ?? "daily"
  };
}

function normalizeUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) throw new Error("Укажите ссылку на поиск.");
  let parsed: URL;
  try { parsed = new URL(trimmed, typeof window === "undefined" ? "http://localhost" : window.location.origin); }
  catch { throw new Error("Ссылка на поиск выглядит некорректно."); }
  if (parsed.origin !== (typeof window === "undefined" ? "http://localhost" : window.location.origin)) throw new Error("Сохранить можно только поиск на этом сайте.");
  if (!parsed.pathname.startsWith("/cars")) throw new Error("Ссылка должна вести в раздел поиска автомобилей.");
  return `${parsed.pathname}${parsed.search}` || "/cars";
}

function filtersFromUrl(value: string) {
  const parsed = new URL(value, "http://localhost");
  const filters: Record<string, string | string[]> = {};
  for (const key of [...new Set([...parsed.searchParams.keys()])].sort()) {
    if (key === "page" || key === "page_size") continue;
    const values = parsed.searchParams.getAll(key).filter(Boolean);
    if (!values.length) continue;
    filters[key] = key === "equipment" ? [...new Set(values)].sort() : values[0];
  }
  return filters;
}

function filterSummary(filters: Record<string, unknown>) {
  return Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .slice(0, 6)
    .map(([key, value]) => `${filterLabels[key] || key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`);
}

function errorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiClientError && error.fieldErrors && Object.keys(error.fieldErrors).length) return Object.values(error.fieldErrors).join(" ");
  return error instanceof Error ? error.message : fallback;
}

async function createSavedSearch(data: { name: string; url: string; filters: Record<string, unknown> }) {
  return apiRequest<{ saved_search: SavedSearch }>("me/saved-searches", {
    method: "POST",
    body: JSON.stringify(data),
    headers: { "Idempotency-Key": randomIdempotencyKey() }
  });
}

async function updateSavedSearch(id: string, revision: number, data: Partial<SavedSearchDraft> & { name?: string; url?: string; filters?: Record<string, unknown> }) {
  return apiRequest<{ saved_search: SavedSearch }>(`me/saved-searches/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ ...data, expected_revision: revision })
  });
}

async function changeSavedSearchStatus(id: string, action: "pause" | "resume", revision: number) {
  return apiRequest<{ saved_search: SavedSearch }>(`me/saved-searches/${encodeURIComponent(id)}/${action}`, {
    method: "POST",
    body: JSON.stringify({ expected_revision: revision })
  });
}

export function SavedSearches({ initialItems, initialUrl = "/cars" }: { initialItems: SavedSearch[]; initialUrl?: string }) {
  const [items, setItems] = useState(() => initialItems.map(normalizeSavedSearch));
  const [drafts, setDrafts] = useState<Record<string, SavedSearchDraft>>(() => Object.fromEntries(initialItems.map((raw) => {
    const item = normalizeSavedSearch(raw);
    return [item.id, { notifications_enabled: item.notifications_enabled, notification_channel: item.notification_channel, notification_frequency: item.notification_frequency }];
  })));
  const [name, setName] = useState("");
  const [url, setUrl] = useState(initialUrl || "/cars");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [emailAvailable, setEmailAvailable] = useState(false);

  useEffect(() => {
    let active = true;
    void apiRequest<{ preferences: { email_verified: boolean; email_delivery_configured: boolean } }>("me/notification-preferences")
      .then(({ preferences }) => {
        if (active) setEmailAvailable(preferences.email_verified && preferences.email_delivery_configured);
      })
      .catch(() => { if (active) setEmailAvailable(false); });
    return () => { active = false; };
  }, []);

  const sortedItems = useMemo(() => items, [items]);

  function updateDraft(id: string, patch: Partial<SavedSearchDraft>) {
    setDrafts((current) => ({ ...current, [id]: { ...(current[id] || { notifications_enabled: false, notification_channel: null, notification_frequency: "daily" }), ...patch } }));
  }

  async function submitCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const cleanName = name.trim();
    if (!cleanName) { setError("Назовите сохранённый поиск."); return; }
    let cleanUrl: string;
    try { cleanUrl = normalizeUrl(url); }
    catch (issue) { setError(errorMessage(issue, "Не удалось проверить ссылку.")); return; }
    setBusy("create");
    try {
      const result = await createSavedSearch({ name: cleanName, url: cleanUrl, filters: filtersFromUrl(cleanUrl) });
      const savedSearch = normalizeSavedSearch(result.saved_search);
      setItems((current) => [savedSearch, ...current]);
      setDrafts((current) => ({ ...current, [savedSearch.id]: { notifications_enabled: savedSearch.notifications_enabled, notification_channel: savedSearch.notification_channel, notification_frequency: savedSearch.notification_frequency } }));
      setName("");
      setSuccess("Поиск сохранён. Вы сможете изменить уведомления в любой момент.");
    } catch (issue) { setError(errorMessage(issue, "Не удалось сохранить поиск.")); }
    finally { setBusy(null); }
  }

  async function submitPreferences(item: SavedSearch) {
    const draft = drafts[item.id] || { notifications_enabled: item.notifications_enabled, notification_channel: item.notification_channel, notification_frequency: item.notification_frequency };
    setError("");
    setSuccess("");
    setBusy(`save:${item.id}`);
    try {
      const result = await updateSavedSearch(item.id, item.revision, draft);
      const updated = normalizeSavedSearch(result.saved_search);
      setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
      setDrafts((current) => ({ ...current, [updated.id]: { notifications_enabled: updated.notifications_enabled, notification_channel: updated.notification_channel, notification_frequency: updated.notification_frequency } }));
      setSuccess(`Настройки «${updated.name}» сохранены.`);
    } catch (issue) { setError(errorMessage(issue, "Не удалось сохранить настройки уведомлений.")); }
    finally { setBusy(null); }
  }

  async function toggleStatus(item: SavedSearch) {
    const action = item.status === "active" ? "pause" : "resume";
    setError("");
    setSuccess("");
    setBusy(`${action}:${item.id}`);
    try {
      const result = await changeSavedSearchStatus(item.id, action, item.revision);
      const updated = normalizeSavedSearch(result.saved_search);
      setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
      setDrafts((current) => ({ ...current, [updated.id]: { notifications_enabled: updated.notifications_enabled, notification_channel: updated.notification_channel, notification_frequency: updated.notification_frequency } }));
      setSuccess(updated.status === "active" ? "Поиск снова активен." : "Поиск поставлен на паузу.");
    } catch (issue) { setError(errorMessage(issue, "Не удалось изменить статус поиска.")); }
    finally { setBusy(null); }
  }

  async function remove(item: SavedSearch) {
    if (typeof window !== "undefined" && !window.confirm(`Удалить сохранённый поиск «${item.name}»?`)) return;
    setError("");
    setSuccess("");
    setBusy(`delete:${item.id}`);
    try {
      await apiRequest<{ ok: true }>(`me/saved-searches/${encodeURIComponent(item.id)}`, { method: "DELETE" });
      setItems((current) => current.filter((entry) => entry.id !== item.id));
      setSuccess("Сохранённый поиск удалён.");
    } catch (issue) { setError(errorMessage(issue, "Не удалось удалить поиск.")); }
    finally { setBusy(null); }
  }

  return <div className="saved-searches">
    <section className="form-section" aria-labelledby="new-saved-search-title">
      <div className="section-heading"><div><p className="eyebrow">Уведомления о новых авто</p><h2 id="new-saved-search-title">Сохранить поиск</h2></div><Bell size={21} aria-hidden="true" /></div>
      <p className="muted">Скопируйте ссылку из поиска автомобилей или начните с раздела <a className="text-link" href="/cars">все автомобили</a>. Web-инбокс работает. {emailAvailable ? "Email доступен при подтверждённом адресе и настроенной доставке." : "Email пока недоступен: нужен подтверждённый адрес и настроенная доставка."} SMS и Telegram пока не поддерживаются.</p>
      <form className="form-grid" onSubmit={submitCreate}>
        <label className="field"><span>Название поиска</span><input name="name" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} placeholder="Например, семейный кроссовер" required /></label>
        <label className="field"><span>Ссылка на результаты</span><input name="url" value={url} onChange={(event) => setUrl(event.target.value)} maxLength={2048} inputMode="url" required /></label>
        <div className="wide form-actions"><span className="muted">Фильтры будут прочитаны из query-параметров ссылки.</span><button className="button button-primary" type="submit" disabled={busy === "create"}><Plus size={16} /> {busy === "create" ? "Сохраняем…" : "Сохранить поиск"}</button></div>
      </form>
    </section>

    <div className="section-heading saved-searches-heading"><div><p className="eyebrow">Личный кабинет</p><h2>Мои сохранённые поиски</h2></div><span className="muted">{items.length} {items.length === 1 ? "поиск" : "поиска"}</span></div>
    {error && <p className="notice" role="alert">{error}</p>}
    {success && <p className="inline-success" role="status"><Check size={15} /> {success}</p>}
    {sortedItems.length === 0 ? <div className="empty-state"><h2>Сохранённых поисков пока нет</h2><p className="muted">Добавьте поиск, чтобы быстро вернуться к нужным фильтрам.</p><a className="button button-secondary" href="/cars">Открыть поиск автомобилей</a></div> : <div className="account-list">{sortedItems.map((item) => {
      const draft = drafts[item.id] || { notifications_enabled: item.notifications_enabled, notification_channel: item.notification_channel, notification_frequency: item.notification_frequency };
      const filters = filterSummary(item.filters);
      const itemBusy = busy?.endsWith(`:${item.id}`) || false;
      return <article className="account-list-item saved-search-item" key={item.id}>
        <div>
          <div className="dealer-topline"><h3><a href={item.url}>{item.name}</a></h3><span className={`status-pill status-${item.status}`}>{item.status === "active" ? "Активен" : "На паузе"}</span></div>
          <p className="muted"><a href={item.url}>{item.url}</a> <ExternalLink size={13} aria-hidden="true" /></p>
          {filters.length > 0 && <div className="active-filters" aria-label="Фильтры поиска">{filters.map((filter) => <span className="filter-chip" key={filter}>{filter}</span>)}</div>}
          <form className="form-grid saved-search-preferences" onSubmit={(event) => { event.preventDefault(); void submitPreferences(item); }}>
            <label className="check-field"><input type="checkbox" checked={draft.notifications_enabled} onChange={(event) => updateDraft(item.id, event.target.checked ? { notifications_enabled: true, notification_channel: draft.notification_channel || "web", notification_frequency: draft.notification_frequency || "daily" } : { notifications_enabled: false })} /> Получать уведомления</label>
            <label className="field"><span>Канал</span><select value={draft.notification_channel || ""} onChange={(event) => updateDraft(item.id, { notification_channel: (event.target.value || null) as SavedSearchChannel | null })} disabled={!draft.notifications_enabled}><option value="">Не выбран</option><option value="web">В кабинете</option>{(emailAvailable || draft.notification_channel === "email") && <option value="email" disabled={!emailAvailable}>{emailAvailable ? "Email" : "Email — временно недоступен"}</option>}</select></label>
            <label className="field"><span>Частота</span><select value={draft.notification_frequency} onChange={(event) => updateDraft(item.id, { notification_frequency: event.target.value as SavedSearchFrequency })} disabled={!draft.notifications_enabled}>{draft.notification_frequency === "weekly" && <option value="weekly" disabled>Раз в неделю — сохранённая настройка</option>}{Object.entries(frequencyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <div className="wide account-item-actions"><button className="button button-secondary button-small" type="submit" disabled={Boolean(itemBusy)}><Save size={14} /> {busy === `save:${item.id}` ? "Сохраняем…" : "Сохранить уведомления"}</button><button className="button button-secondary button-small" type="button" disabled={Boolean(itemBusy)} onClick={() => void toggleStatus(item)}>{item.status === "active" ? <><Pause size={14} /> Пауза</> : <><Play size={14} /> Возобновить</>}</button><button className="button button-danger button-small" type="button" disabled={Boolean(itemBusy)} onClick={() => void remove(item)}><Trash2 size={14} /> Удалить</button></div>
          </form>
        </div>
      </article>;
    })}</div>}
  </div>;
}
