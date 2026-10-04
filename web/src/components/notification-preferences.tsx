"use client";

import { useState } from "react";
import { ApiClientError, api, type NotificationPreferences as Preferences } from "@/lib/api";

type Draft = Pick<Preferences, "web_enabled" | "email_enabled">;

function errorText(issue: unknown) {
  if (issue instanceof ApiClientError && issue.code === "revision_conflict") return "Настройки уже изменились в другом окне. Загрузите актуальные значения и повторите.";
  return "Не удалось сохранить настройки уведомлений. Повторите попытку.";
}

export function NotificationPreferences({ initialPreferences }: { initialPreferences: Preferences | null }) {
  const [preferences, setPreferences] = useState(initialPreferences);
  const [draft, setDraft] = useState<Draft | null>(initialPreferences ? {
    web_enabled: initialPreferences.web_enabled, email_enabled: initialPreferences.email_enabled
  } : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function reload() {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.notificationPreferences();
      setPreferences(result.preferences);
      setDraft({ web_enabled: result.preferences.web_enabled, email_enabled: result.preferences.email_enabled });
    } catch {
      setError("Не удалось загрузить настройки уведомлений. Повторите попытку.");
    } finally { setBusy(false); }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preferences || !draft || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.updateNotificationPreferences({ ...draft, expected_revision: preferences.revision });
      setPreferences(result.preferences);
      setDraft({ web_enabled: result.preferences.web_enabled, email_enabled: result.preferences.email_enabled });
      setNotice("Настройки уведомлений сохранены.");
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  return <section className="notification-preferences" aria-labelledby="notification-preferences-title">
    <div className="section-heading"><div><p className="eyebrow">Каналы доставки</p><h2 id="notification-preferences-title">Настройки уведомлений</h2></div></div>
    {!preferences || !draft ? <div>
      <p className="muted">Не удалось загрузить сохранённые настройки.</p>
      <button className="button button-secondary button-small" type="button" onClick={() => void reload()} disabled={busy}>{busy ? "Загружаем…" : "Повторить загрузку"}</button>
    </div> : <form className="notification-preferences-form" onSubmit={submit} aria-busy={busy}>
      <label className="check-field"><input type="checkbox" name="web_enabled" checked={draft.web_enabled} onChange={(event) => { const checked = event.currentTarget.checked; setDraft((current) => current ? { ...current, web_enabled: checked } : current); }} /> Уведомления в кабинете</label>
      <label className="check-field"><input type="checkbox" name="email_enabled" checked={draft.email_enabled} onChange={(event) => { const checked = event.currentTarget.checked; setDraft((current) => current ? { ...current, email_enabled: checked } : current); }} /> Email-уведомления</label>
      {!preferences.email_verified && <p className="notice" role="status">Сначала подтвердите адрес электронной почты в настройках профиля. Выбор сохраняется; отправка также зависит от доступности почтового сервиса.</p>}
      {preferences.email_verified && <p className="muted">Отправка email зависит от доступности почтового сервиса.</p>}
      {error && <p className="inline-error" role="alert">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      <button className="button button-primary button-small" type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить настройки"}</button>
    </form>}
  </section>;
}
