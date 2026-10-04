"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiClientError } from "@/lib/api";
import { adminApi, type AdminCatalogItem as CatalogItem, type AdminCatalogKind, type AdminCatalogVersion } from "@/lib/admin";

function cleanUrl(value: string | null | undefined) {
  if (!value) return null;
  try { const url = new URL(value); return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null; }
  catch { return null; }
}

function errorText(issue: unknown) {
  if (issue instanceof ApiClientError) {
    if (issue.code === "revision_conflict") return "Запись справочника уже изменена. Обновите список перед новой попыткой.";
    if (issue.code === "reauthentication_failed") return "Текущий пароль администратора не подошёл.";
    if (issue.status === 403) return "Администраторская роль больше не активна.";
  }
  return issue instanceof Error ? issue.message : "Не удалось изменить запись справочника.";
}

function snapshotLabel(snapshot: AdminCatalogVersion["before"]) {
  const values = [snapshot.name, snapshot.aliases?.length ? `Синонимы: ${snapshot.aliases.join(", ")}` : null,
    snapshot.year_from || snapshot.year_to ? `Годы: ${snapshot.year_from ?? "—"}–${snapshot.year_to ?? "—"}` : null].filter(Boolean);
  return values.join(" · ") || "Нет сохранённых полей";
}

export function AdminCatalogItem({ kind, initialItem }: { kind: AdminCatalogKind; initialItem: CatalogItem }) {
  const router = useRouter();
  const [item, setItem] = useState(initialItem);
  const [editing, setEditing] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versions, setVersions] = useState<AdminCatalogVersion[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const supportsAliases = kind === "makes" || kind === "models";
  const supportsYears = kind === "generations";

  async function showVersions() {
    const nextOpen = !versionsOpen;
    setVersionsOpen(nextOpen);
    if (!nextOpen || versions) return;
    setBusy(true); setError("");
    try { setVersions((await adminApi.catalogVersions(kind, item.id)).items); }
    catch (issue) { setError(issue instanceof Error ? issue.message : "Не удалось загрузить историю."); }
    finally { setBusy(false); }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const values = new FormData(event.currentTarget);
    const name = String(values.get("name") || "").trim();
    const reason = String(values.get("reason") || "").trim();
    const currentPassword = String(values.get("current_password") || "");
    const confirmation = String(values.get("confirmation") || "");
    if (!name) { setError("Укажите новое название."); return; }
    if (!reason) { setError("Укажите причину изменения."); return; }
    if (confirmation !== "UPDATE_CATALOG") { setError("Введите UPDATE_CATALOG для подтверждения."); return; }
    const payload = {
      name, expected_revision: item.revision, reason, confirmation: "UPDATE_CATALOG" as const, current_password: currentPassword,
      ...(supportsAliases ? { aliases: String(values.get("aliases") || "").split(/[\n,]/).map((entry) => entry.trim()).filter(Boolean) } : {}),
      ...(supportsYears ? {
        year_from: String(values.get("year_from") || "").trim() ? Number(values.get("year_from")) : null,
        year_to: String(values.get("year_to") || "").trim() ? Number(values.get("year_to")) : null
      } : {})
    };
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await adminApi.updateCatalogItem(kind, item.id, payload);
      setItem(result.item);
      setVersions(null);
      setEditing(false);
      setNotice(result.changed ? "Изменение сохранено и добавлено в историю." : "Изменений нет.");
      router.refresh();
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  const canonicalUrl = cleanUrl(item.source?.canonical_url);
  const licenseUrl = cleanUrl(item.source?.license_url);
  return <article className="admin-catalog-item">
    <div className="admin-catalog-item-heading"><div><h2>{item.name}</h2><p className="muted">{item.kind} · {item.id} · ревизия {item.revision}{item.manual_override ? " · ручное изменение" : " · исходный справочник"}</p><p className="admin-catalog-aliases">Синонимы: {item.aliases.length ? item.aliases.join(", ") : "—"}{item.year_from || item.year_to ? ` · ${item.year_from ?? "—"}–${item.year_to ?? "—"}` : ""}</p></div>
      <div className="admin-catalog-actions"><button className="button button-secondary button-small" type="button" onClick={() => { setEditing((open) => !open); setError(""); }}>{editing ? "Закрыть" : "Изменить"}</button><button className="button button-secondary button-small" type="button" disabled={busy} onClick={showVersions}>{versionsOpen ? "Скрыть историю" : "История"}</button></div></div>
    {item.source && <details className="admin-catalog-source"><summary>Источник и происхождение</summary><dl>
      <div><dt>Источник</dt><dd>{item.source.source_name || item.source_name || "Не указан"}</dd></div>
      {canonicalUrl && <div><dt>Каноническая страница</dt><dd><a href={canonicalUrl} target="_blank" rel="noreferrer">Открыть источник</a></dd></div>}
      {licenseUrl && <div><dt>Условия использования</dt><dd><a href={licenseUrl} target="_blank" rel="noreferrer">Лицензия или условия</a></dd></div>}
      {item.source.permission_reference && <div><dt>Разрешение</dt><dd>{item.source.permission_reference}</dd></div>}
      {item.source.retrieved_at && <div><dt>Получено</dt><dd>{item.source.retrieved_at}</dd></div>}
      {item.source.checksum && <div><dt>Контрольная сумма</dt><dd><code>{item.source.checksum}</code></dd></div>}
    </dl></details>}
    {editing && <form className="admin-catalog-edit" onSubmit={submit}>
      <label className="field"><span>Название</span><input name="name" defaultValue={item.name} maxLength={1024} required /></label>
      {supportsAliases && <label className="field wide"><span>Синонимы, по одному на строку</span><textarea name="aliases" defaultValue={item.aliases.join("\n")} maxLength={4000} /></label>}
      {supportsYears && <div className="admin-catalog-years"><label className="field"><span>Год начала</span><input name="year_from" type="number" min={1886} max={2100} defaultValue={item.year_from ?? ""} /></label><label className="field"><span>Год окончания</span><input name="year_to" type="number" min={1886} max={2100} defaultValue={item.year_to ?? ""} /></label></div>}
      <label className="field wide"><span>Причина</span><textarea name="reason" maxLength={1000} required /></label>
      <label className="field"><span>Текущий пароль администратора</span><input name="current_password" type="password" autoComplete="current-password" maxLength={256} required /></label>
      <label className="field"><span>Введите UPDATE_CATALOG</span><input name="confirmation" autoComplete="off" required /></label>
      {error && <p className="inline-error wide" role="alert">{error}</p>}
      <div className="form-actions wide"><button className="button button-primary button-small" type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить запись"}</button><button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => setEditing(false)}>Отмена</button></div>
    </form>}
    {versionsOpen && <div className="admin-catalog-history"><h3>История изменений</h3>{versions === null ? <p className="muted" role="status">{busy ? "Загружаем историю…" : "История ещё не загружена."}</p> : versions.length ? <ol>{versions.map((version) => <li key={version.id}>
      <strong>Ревизия {version.revision}</strong> · {new Date(version.created_at).toLocaleString("ru-RU")} · {version.reason}
      {!version.valid && <p className="inline-error">Запись истории неполная или некорректная; исходные данные не раскрываются.</p>}
      <p>До: {snapshotLabel(version.before)}</p><p>После: {snapshotLabel(version.after)}</p>
    </li>)}</ol> : <p className="muted">Сохранённых изменений нет.</p>}</div>}
    {notice && <p className="notice" role="status">{notice}</p>}{error && !editing && <p className="inline-error" role="alert">{error}</p>}
  </article>;
}
