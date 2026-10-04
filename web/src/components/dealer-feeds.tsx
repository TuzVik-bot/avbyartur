"use client";

import { useEffect, useRef, useState } from "react";
import { ApiClientError, createIdempotencyKey } from "@/lib/api";
import {
  dealerTeamApi,
  type DealerFeed,
  type DealerFeedCreate,
  type DealerFeedImportRun,
  type DealerFeedMissingCandidate,
  type DealerFeedPolicyPatch,
  type DealerTeamMember
} from "@/lib/dealer";
import { FeedImportHistory, type FeedImportDetail } from "@/components/feed-import-history";

const roleCanManage = (member: DealerTeamMember | undefined) => member?.status === "active" && (member.role === "owner" || member.role === "admin");
const roleCanImport = (member: DealerTeamMember | undefined) => member?.status === "active" && (member.role === "owner" || member.role === "admin" || member.role === "seller");
const MAX_FEED_BYTES = 10 * 1024 * 1024;
type FeedPolicyDraft = {
  manual_conflict_policy: DealerFeed["manual_conflict_policy"];
  missing_retirement_enabled: boolean;
  missing_retirement_delay_hours: string;
};
const feedMappingFields = [
  ["dealer_external_id", "Внешний ID строки"], ["make_id", "ID марки"], ["model_id", "ID модели"],
  ["generation_id", "ID поколения"], ["body_type_id", "ID типа кузова"], ["body_variant_id", "ID варианта кузова"],
  ["modification_id", "ID модификации"], ["manual_make", "Марка текстом"], ["manual_model", "Модель текстом"],
  ["title", "Заголовок"], ["year", "Год"], ["mileage_km", "Пробег, км"], ["fuel", "Топливо"],
  ["transmission", "Коробка передач"], ["drive", "Привод"], ["condition", "Состояние"], ["color", "Цвет"],
  ["customs_status", "Таможенный статус"], ["technical_condition", "Техническое состояние"],
  ["body_condition", "Состояние кузова"], ["exchange", "Обмен"], ["bargaining", "Торг"],
  ["credit", "Кредит"], ["leasing", "Лизинг"], ["equipment", "Опции"], ["district", "Район"],
  ["call_hours", "Время звонков"], ["damaged", "Повреждён"], ["parts_only", "Только на запчасти"],
  ["engine_volume_l", "Объём двигателя, л"], ["power_hp", "Мощность, л.с."], ["description", "Описание"],
  ["vin", "VIN"], ["price_amount", "Цена"], ["currency", "Валюта"], ["region_id", "ID области"],
  ["city_id", "ID города"], ["manual_city", "Город текстом"], ["contact_phone", "Телефон"]
] as const;

function errorText(issue: unknown) {
  if (issue instanceof ApiClientError) {
    if (issue.code === "company_not_approved") return "Компания ещё не допущена к пилоту. Настройка интеграций станет доступна после проверки.";
    if (issue.code === "feed_disabled") return "Интеграция отключена. Включите её перед импортом.";
    if (issue.code === "api_feed_required") return "Для этого источника нужен API-формат.";
    if (issue.code === "missing_retirement_disabled") return "Сначала включите отложенную остановку отсутствующих объявлений в настройках источника.";
    if (issue.code === "missing_confirmation_too_early") return "Срок ожидания ещё не прошёл. Повторите подтверждение после указанной даты.";
    if (issue.code === "missing_candidate_stale") return "Объявление или снимок изменились. Обновите список кандидатов.";
    if (issue.status === 403) return "У вашей роли нет доступа к настройке интеграций.";
    if (issue.status === 409) return issue.message;
  }
  return issue instanceof Error ? issue.message : "Не удалось выполнить действие.";
}

export function DealerFeeds({ initialFeeds, initialTeam, currentUserId }: {
  initialFeeds: DealerFeed[] | null;
  initialTeam: DealerTeamMember[];
  currentUserId: string;
}) {
  const [feeds, setFeeds] = useState(initialFeeds);
  const [history, setHistory] = useState<FeedImportDetail[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [format, setFormat] = useState<DealerFeedCreate["format"]>("csv");
  const [fieldMapping, setFieldMapping] = useState<Record<string, string>>({ dealer_external_id: "dealer_external_id" });
  const [files, setFiles] = useState<Record<string, File>>({});
  const [policyDrafts, setPolicyDrafts] = useState<Record<string, FeedPolicyDraft>>({});
  const [completeSnapshots, setCompleteSnapshots] = useState<Record<string, boolean>>({});
  const [missingCandidates, setMissingCandidates] = useState<Record<string, DealerFeedMissingCandidate[]>>({});
  const [snapshotPreviews, setSnapshotPreviews] = useState<Record<string, DealerFeedMissingCandidate[]>>({});
  const [candidateLoading, setCandidateLoading] = useState<Record<string, boolean>>({});
  const [oneTimeToken, setOneTimeToken] = useState<{ feedName: string; token: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const importKeys = useRef(new WeakMap<File, Partial<Record<"preview" | "apply", string>>>());
  const confirmationKeys = useRef(new Map<string, string>());
  const currentMember = initialTeam.find((member) => member.user_id === currentUserId);
  const manager = roleCanManage(currentMember);
  const canImport = roleCanImport(currentMember);
  const historyStorageKey = `avtorinok-feed-imports:${currentUserId}`;

  useEffect(() => {
    let active = true;
    try {
      const raw = sessionStorage.getItem(historyStorageKey);
      const ids: unknown = raw ? JSON.parse(raw) : [];
      if (Array.isArray(ids)) {
        const validIds = ids.filter((id): id is string => typeof id === "string" && /^[0-9a-f-]{36}$/i.test(id)).slice(0, 10);
        Promise.all(validIds.map(async (id) => {
          try {
            const [run, rows] = await Promise.all([dealerTeamApi.importRun(id), dealerTeamApi.importRows(id)]);
            return { run: run.run, rows: rows.items };
          } catch { return null; }
        })).then((items) => {
          if (active) setHistory(items.filter((item): item is FeedImportDetail => item !== null));
        });
      }
    } catch { /* Storage can be disabled; imports still work for this page view. */ }
    return () => { active = false; };
  }, [historyStorageKey]);

  async function reloadFeeds() {
    setBusy(true); setError("");
    try { setFeeds((await dealerTeamApi.feeds()).items); setNotice("Источники данных обновлены."); }
    catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function createFeed(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manager || busy) return;
    const cleanName = name.trim();
    if (cleanName.length < 2 || cleanName.length > 120) { setError("Название источника должно содержать от 2 до 120 символов."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const mapping = Object.fromEntries(Object.entries(fieldMapping).map(([key, value]) => [key, value.trim()]).filter(([, value]) => value));
      const result = await dealerTeamApi.createFeed({
        name: cleanName,
        format,
        manual_conflict_policy: "review",
        missing_retirement_enabled: false,
        missing_retirement_delay_hours: 168,
        ...(format === "api" ? {} : { field_mapping: mapping })
      });
      setFeeds((current) => [result.feed, ...(current ?? [])]);
      setName("");
      if (result.api_token) setOneTimeToken({ feedName: result.feed.name, token: result.api_token });
      setNotice("Источник данных создан.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function changeStatus(feed: DealerFeed) {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await dealerTeamApi.updateFeedStatus(feed, feed.status === "active" ? "disabled" : "active");
      setFeeds((current) => current?.map((item) => item.id === feed.id ? result.feed : item) ?? [result.feed]);
      setNotice(result.feed.status === "active" ? "Источник включён." : "Источник отключён.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function rotateToken(feed: DealerFeed) {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await dealerTeamApi.rotateFeedToken(feed.id);
      setOneTimeToken({ feedName: feed.name, token: result.api_token });
      setNotice("Новый ключ создан. Предыдущий ключ больше не действует.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  function policyFor(feed: DealerFeed): FeedPolicyDraft {
    return policyDrafts[feed.id] ?? {
      manual_conflict_policy: feed.manual_conflict_policy,
      missing_retirement_enabled: feed.missing_retirement_enabled,
      missing_retirement_delay_hours: String(feed.missing_retirement_delay_hours)
    };
  }

  function patchPolicy(feed: DealerFeed, patch: Partial<FeedPolicyDraft>) {
    setPolicyDrafts((current) => ({
      ...current,
      [feed.id]: {
        manual_conflict_policy: current[feed.id]?.manual_conflict_policy ?? feed.manual_conflict_policy,
        missing_retirement_enabled: current[feed.id]?.missing_retirement_enabled ?? feed.missing_retirement_enabled,
        missing_retirement_delay_hours: current[feed.id]?.missing_retirement_delay_hours ?? String(feed.missing_retirement_delay_hours),
        ...patch
      }
    }));
  }

  async function savePolicy(feed: DealerFeed) {
    const draft = policyFor(feed);
    const delay = Number(draft.missing_retirement_delay_hours);
    if (!Number.isInteger(delay) || delay < 1 || delay > 8760) {
      setError("Срок ожидания должен быть целым числом от 1 до 8760 часов.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const policy: DealerFeedPolicyPatch = {
        manual_conflict_policy: draft.manual_conflict_policy,
        missing_retirement_enabled: draft.missing_retirement_enabled,
        missing_retirement_delay_hours: delay
      };
      const result = await dealerTeamApi.updateFeedPolicy(feed.id, policy);
      setFeeds((current) => current?.map((item) => item.id === feed.id ? result.feed : item) ?? [result.feed]);
      setPolicyDrafts((current) => {
        const next = { ...current };
        delete next[feed.id];
        return next;
      });
      setNotice("Правила источника сохранены.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function loadMissingCandidates(feed: DealerFeed) {
    setCandidateLoading((current) => ({ ...current, [feed.id]: true })); setError("");
    try {
      const result = await dealerTeamApi.missingCandidates(feed.id);
      setMissingCandidates((current) => ({ ...current, [feed.id]: result.items }));
    } catch (issue) { setError(errorText(issue)); }
    finally { setCandidateLoading((current) => ({ ...current, [feed.id]: false })); }
  }

  async function confirmMissingCandidate(feed: DealerFeed, item: DealerFeedMissingCandidate) {
    if (!manager || !item.eligible || item.expected_listing_revision === null || item.snapshot_digest === null) return;
    const keyId = `${feed.id}:${item.dealer_external_id}:${item.expected_listing_revision}:${item.snapshot_digest}`;
    const key = confirmationKeys.current.get(keyId) ?? createIdempotencyKey();
    confirmationKeys.current.set(keyId, key);
    setBusy(true); setError(""); setNotice("");
    try {
      await dealerTeamApi.confirmMissingCandidate(feed.id, {
        dealer_external_id: item.dealer_external_id,
        expected_listing_revision: item.expected_listing_revision,
        snapshot_digest: item.snapshot_digest
      }, key);
      confirmationKeys.current.delete(keyId);
      setNotice(`Объявление ${item.dealer_external_id} приостановлено.`);
      await loadMissingCandidates(feed);
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function importFile(feed: DealerFeed, dryRun: boolean) {
    const file = files[feed.id];
    if (!file) { setError("Выберите файл для импорта."); return; }
    if (file.size > MAX_FEED_BYTES) { setError("Размер файла превышает 10 МБ."); return; }
    setBusy(true); setError(""); setNotice("");
    const kind = dryRun ? "preview" : "apply";
    const completeSnapshot = completeSnapshots[feed.id] ?? false;
    const keys = importKeys.current.get(file) ?? {};
    const key = keys[kind] ?? createIdempotencyKey();
    keys[kind] = key;
    importKeys.current.set(file, keys);
    try {
      const result = await dealerTeamApi.importFeedFile(feed.id, file, dryRun, key, completeSnapshot);
      delete keys[kind];
      if (completeSnapshot && dryRun) {
        setSnapshotPreviews((current) => ({ ...current, [feed.id]: result.missing_candidates ?? [] }));
      } else if (completeSnapshot) {
        setSnapshotPreviews((current) => ({ ...current, [feed.id]: [] }));
        setMissingCandidates((current) => ({ ...current, [feed.id]: result.missing_candidates ?? [] }));
      }
      setHistory((current) => [
        { run: result.run, rows: [] },
        ...current.filter((item) => item.run.id !== result.run.id)
      ].slice(0, 10));
      setSelectedRunId(result.run.id);
      try {
        const ids = [result.run.id, ...JSON.parse(sessionStorage.getItem(historyStorageKey) || "[]").filter((id: unknown) => id !== result.run.id)].slice(0, 10);
        sessionStorage.setItem(historyStorageKey, JSON.stringify(ids));
      } catch { /* History remains visible until this page is closed. */ }
      const [run, rows] = await Promise.all([dealerTeamApi.importRun(result.run.id), dealerTeamApi.importRows(result.run.id)]);
      setHistory((current) => current.map((item) => item.run.id === run.run.id ? { run: run.run, rows: rows.items } : item));
      if (dryRun) {
        setNotice("Предпросмотр готов. Данные не записаны.");
      } else if (completeSnapshot && result.run.status === "failed") {
        setNotice("Снимок отклонён целиком: есть строки с ошибками. Состояние объявлений и кандидатов не изменено.");
      } else if (result.run.rejected_rows > 0) {
        setNotice(`Импорт завершён: применено ${result.run.applied_rows}, отклонено ${result.run.rejected_rows}.`);
      } else {
        setNotice("Импорт обработан.");
      }
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  async function selectRun(runId: string) {
    setSelectedRunId(runId);
    const cached = history.find((item) => item.run.id === runId);
    if (cached?.rows.length) return;
    try {
      const [run, rows] = await Promise.all([dealerTeamApi.importRun(runId), dealerTeamApi.importRows(runId)]);
      setHistory((current) => current.map((item) => item.run.id === runId ? { run: run.run, rows: rows.items } : item));
    } catch (issue) { setError(errorText(issue)); }
  }

  if (feeds === null) return <section className="notice" role="alert"><p>Не удалось загрузить интеграции. Проверьте доступ компании или повторите загрузку.</p><button className="button button-secondary button-small" type="button" disabled={busy} onClick={reloadFeeds}>Повторить загрузку</button></section>;

  return <div className="dealer-feeds">
    {!canImport && <div className="notice" role="status">У вашей роли доступен просмотр. Импорт может выполнять владелец, администратор или продавец компании.</div>}
    {manager && <section className="section" aria-labelledby="feed-create-heading"><div className="section-heading"><div><h2 id="feed-create-heading">Подключить источник</h2><p className="muted">Предпросмотр файла не меняет объявления. Новые источники начинают работу с ручным конфликтом «На проверку» и выключенным снятием отсутствующих объявлений.</p></div></div>
      <form className="dealer-feed-create" onSubmit={createFeed}>
        <label className="field"><span>Название источника</span><input value={name} minLength={2} maxLength={120} onChange={(event) => setName(event.currentTarget.value)} required /></label>
        <label className="field"><span>Формат</span><select value={format} onChange={(event) => setFormat(event.currentTarget.value as DealerFeedCreate["format"])}><option value="csv">CSV</option><option value="xml">XML</option><option value="api">API</option></select></label>
        {format !== "api" && <details className="feed-mapping wide"><summary>Настроить соответствие заголовков</summary><p className="muted">Укажите названия столбцов из файла. Если заголовок совпадает с системным именем, поле можно оставить пустым.</p><div className="feed-mapping-grid">{feedMappingFields.map(([key, label]) => <label className="field" key={key}><span>{label} <code>{key}</code></span><input maxLength={120} value={fieldMapping[key] || ""} onChange={(event) => { const value = event.currentTarget.value; setFieldMapping((current) => ({ ...current, [key]: value })); }} /></label>)}</div></details>}
        <button className="button button-primary button-small" type="submit" disabled={busy}>{busy ? "Создаём…" : "Создать источник"}</button>
      </form>
    </section>}

    <section className="section" aria-labelledby="feeds-heading"><div className="section-heading"><div><h2 id="feeds-heading">Источники данных</h2><p className="muted">API-ключ показывается только при создании или ротации. Сохраните его в своей системе интеграции.</p></div><button className="button button-secondary button-small" type="button" onClick={reloadFeeds} disabled={busy}>Обновить</button></div>
      <div className="feed-downloads" aria-label="Примеры и схема фида"><span className="muted">Синтетические материалы:</span><a href="/api/v1/dealer/feeds/samples/csv" download>CSV</a><a href="/api/v1/dealer/feeds/samples/xml" download>XML</a><a href="/api/v1/dealer/feeds/samples/api" download>API JSON</a><a href="/api/v1/dealer/feeds/samples/schema" download>Схема JSON</a></div>
      {!feeds.length ? <p className="muted" role="status">Подключённых источников пока нет.</p> : <div className="feed-list">{feeds.map((feed) => {
        const policy = policyFor(feed);
        const candidates = missingCandidates[feed.id];
        const snapshotPreview = snapshotPreviews[feed.id];
        const delay = Number(policy.missing_retirement_delay_hours);
        const policyValid = Number.isInteger(delay) && delay >= 1 && delay <= 8760;
        return <article className="feed-card" key={feed.id}>
          <div className="feed-card-heading"><div><h3>{feed.name}</h3><p className="muted">{feed.format.toUpperCase()} · {feed.status === "active" ? "Включён" : "Отключён"}{feed.api_token_prefix ? ` · ключ ${feed.api_token_prefix}…` : ""}</p></div>{manager && <button className={feed.status === "active" ? "button button-secondary button-small" : "button button-primary button-small"} type="button" disabled={busy} onClick={() => changeStatus(feed)}>{feed.status === "active" ? "Отключить" : "Включить"}</button>}</div>

          {manager && <section className="feed-policy" aria-label={`Правила источника ${feed.name}`}>
            <h4>Правила синхронизации</h4>
            <div className="feed-policy-grid">
              <label className="field"><span>Если объявление изменили вручную</span><select value={policy.manual_conflict_policy} disabled={busy} onChange={(event) => patchPolicy(feed, { manual_conflict_policy: event.currentTarget.value as DealerFeed["manual_conflict_policy"] })}><option value="review">Оставить на проверку</option><option value="feed_wins">Применить данные фида</option></select></label>
              <label className="field"><span>Срок до остановки отсутствующего объявления, часов</span><input type="number" min={1} max={8760} step={1} value={policy.missing_retirement_delay_hours} disabled={busy} onChange={(event) => patchPolicy(feed, { missing_retirement_delay_hours: event.currentTarget.value })} /></label>
            </div>
            <label className="check-field"><input type="checkbox" checked={policy.missing_retirement_enabled} disabled={busy} onChange={(event) => patchPolicy(feed, { missing_retirement_enabled: event.currentTarget.checked })} /><span>Разрешить владельцу или админу останавливать объявление после срока ожидания и проверки снимка</span></label>
            <button className="button button-secondary button-small" type="button" disabled={busy || !policyDrafts[feed.id] || !policyValid} onClick={() => savePolicy(feed)}>Сохранить правила</button>
            {!policyValid && <p className="inline-error" role="alert">Срок ожидания должен быть от 1 до 8760 часов.</p>}
          </section>}

          {feed.format === "api" && <div className="feed-api-controls"><p className="muted">Передавайте записи в <code>/api/v1/dealer/feeds/{feed.id}/api-imports</code> с заголовками Bearer и Idempotency-Key. Сначала отправляйте JSON с <code>dry_run: true</code>.</p>{manager && <button className="button button-secondary button-small" type="button" disabled={busy || feed.status !== "active"} onClick={() => rotateToken(feed)}>Создать новый API-ключ</button>}</div>}

          {canImport && feed.format !== "api" && <div className="feed-file-import"><label className="field"><span>Файл {feed.format.toUpperCase()}</span><input type="file" accept={feed.format === "csv" ? ".csv,text/csv" : ".xml,application/xml,text/xml"} disabled={busy || feed.status !== "active"} onChange={(event) => { const selectedFile = event.currentTarget.files?.[0]; if (selectedFile) setFiles((current) => ({ ...current, [feed.id]: selectedFile })); }} /></label><span className="muted">{files[feed.id]?.name || "Файл до 10 МБ"}</span>
            <label className="check-field"><input type="checkbox" checked={completeSnapshots[feed.id] ?? false} disabled={busy || feed.status !== "active"} onChange={(event) => { const checked = event.currentTarget.checked; setCompleteSnapshots((current) => ({ ...current, [feed.id]: checked })); }} /><span>Это полный снимок всех активных объявлений источника</span></label>
            {(completeSnapshots[feed.id] ?? false) && <p className="feed-snapshot-warning">Любая отклонённая строка отклонит весь снимок. Отсутствующие объявления попадут в список ожидания только после успешного применения.</p>}
            <div className="feed-import-actions"><button className="button button-secondary button-small" type="button" disabled={busy || feed.status !== "active" || !files[feed.id]} onClick={() => importFile(feed, true)}>Предпросмотр</button><button className="button button-primary button-small" type="button" disabled={busy || feed.status !== "active" || !files[feed.id]} onClick={() => importFile(feed, false)}>{(completeSnapshots[feed.id] ?? false) ? "Применить весь снимок" : "Применить корректные строки"}</button></div>
          </div>}

          {snapshotPreview && snapshotPreview.length > 0 && <div className="feed-candidates" aria-label={`Предпросмотр отсутствующих объявлений ${feed.name}`}><h4>Предпросмотр отсутствующих объявлений</h4><p className="muted">Это оценка полного снимка; кандидатами они станут только после его успешного применения.</p><ul>{snapshotPreview.map((item) => <li key={item.dealer_external_id}><strong>{item.title}</strong> · {item.dealer_external_id} · ревизия {item.expected_listing_revision ?? "—"}</li>)}</ul></div>}

          <section className="feed-candidates" aria-label={`Проверка отсутствующих объявлений ${feed.name}`}>
            <div className="section-heading"><div><h4>Отсутствующие в снимке</h4><p className="muted">Пауза возможна только после срока ожидания, если ревизия и снимок не изменились.</p></div><button className="button button-secondary button-small" type="button" disabled={busy || candidateLoading[feed.id]} onClick={() => loadMissingCandidates(feed)}>{candidateLoading[feed.id] ? "Загружаем…" : "Проверить список"}</button></div>
            {candidates && (candidates.length === 0 ? <p className="muted" role="status">Кандидатов на остановку нет.</p> : <ul>{candidates.map((item) => <li key={item.dealer_external_id}>
              <div><strong>{item.title}</strong><span className="muted"> · {item.dealer_external_id} · ревизия {item.listing_revision}</span><p className="muted">{item.reason === "retirement_disabled" ? "Отложенная остановка выключена" : item.reason === "listing_changed" ? "Объявление изменилось после снимка" : item.reason === "listing_not_active" ? "Объявление уже не активно" : item.reason === "confirmation_delay" ? `Ожидание до ${item.due_at ? new Date(item.due_at).toLocaleString("ru-RU") : "позже"}` : item.eligible ? "Готово к подтверждению владельцем или администратором" : "Требуется проверка"}</p></div>
              {manager && <button className="button button-secondary button-small" type="button" disabled={busy || !item.eligible || item.expected_listing_revision === null || item.snapshot_digest === null} onClick={() => confirmMissingCandidate(feed, item)}>Подтвердить паузу</button>}
            </li>)}</ul>)}
          </section>
        </article>;
      })}</div>}
    </section>

    {oneTimeToken && <section className="notice feed-token-notice" aria-label="Новый API-ключ" role="status"><div><strong>Новый ключ для источника «{oneTimeToken.feedName}»</strong><p>Он больше не появится в интерфейсе. При ротации предыдущий ключ уже отозван.</p></div><code>{oneTimeToken.token}</code><button className="button button-secondary button-small" type="button" onClick={() => setOneTimeToken(null)}>Скрыть ключ</button></section>}
    <FeedImportHistory items={history} selectedId={selectedRunId} onSelect={selectRun} />
    {notice && <p className="notice" role="status">{notice}</p>}{error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
