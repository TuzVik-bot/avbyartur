"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiClientError } from "@/lib/api";
import { adminApi, type RuntimeSetting } from "@/lib/admin";

const settingInfo: Record<string, { title: string; description: string }> = {
  private_listing_quota: { title: "Лимит частных объявлений", description: "Максимум объявлений на одного частного продавца." },
  company_listing_quota: { title: "Лимит объявлений компании", description: "Максимум объявлений на одну компанию." },
  saved_search_limit: { title: "Лимит сохранённых поисков", description: "Максимум поисковых уведомлений на аккаунт." }
};

function errorText(issue: unknown) {
  if (issue instanceof ApiClientError) {
    if (issue.code === "revision_conflict") return "Лимит уже изменён. Обновите страницу и проверьте актуальное значение.";
    if (issue.code === "reauthentication_failed") return "Текущий пароль администратора не подошёл.";
    if (issue.status === 403) return "Администраторская роль больше не активна.";
  }
  return issue instanceof Error ? issue.message : "Не удалось сохранить лимит.";
}

export function AdminRuntimeSetting({ initialSetting }: { initialSetting: RuntimeSetting }) {
  const router = useRouter();
  const [setting, setSetting] = useState(initialSetting);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const info = settingInfo[setting.key] ?? { title: setting.key, description: "Ограничение приложения." };

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const values = new FormData(event.currentTarget);
    const rawValue = String(values.get("value") || "");
    const value = Number(rawValue);
    const reason = String(values.get("reason") || "").trim();
    const currentPassword = String(values.get("current_password") || "");
    const confirmation = String(values.get("confirmation") || "");
    if (!Number.isSafeInteger(value) || value < 1 || value > 10000) { setError("Введите целое число от 1 до 10000."); return; }
    if (!reason) { setError("Укажите причину изменения."); return; }
    if (confirmation !== "UPDATE_SETTING") { setError("Введите UPDATE_SETTING для подтверждения."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await adminApi.updateRuntimeSetting(setting.key, {
        value, expected_revision: setting.revision, reason,
        confirmation: "UPDATE_SETTING", current_password: currentPassword
      });
      setSetting(result.setting);
      setEditing(false);
      setNotice(result.changed ? "Лимит сохранён и записан в аудит." : "Лимит не изменился.");
      router.refresh();
    } catch (issue) { setError(errorText(issue)); }
    finally { setBusy(false); }
  }

  return <article className="admin-runtime-setting">
    <div className="admin-runtime-setting-summary"><div><h2>{info.title}</h2><p>{info.description}</p><p className="muted">Источник: {setting.source === "override" ? "администраторское значение" : "настройка окружения"} · ревизия {setting.revision}</p></div><div className="admin-runtime-setting-value"><strong>{setting.value}</strong><span>ед.</span></div></div>
    {!editing ? <button className="button button-secondary button-small" type="button" onClick={() => { setEditing(true); setError(""); }}>Изменить лимит</button> : <form className="admin-runtime-setting-form" onSubmit={submit}>
      <label className="field"><span>Новое значение (1–10000)</span><input type="number" name="value" min={1} max={10000} step={1} defaultValue={setting.value} required /></label>
      <label className="field"><span>Причина</span><textarea name="reason" maxLength={1000} required /></label>
      <label className="field"><span>Текущий пароль администратора</span><input type="password" name="current_password" autoComplete="current-password" maxLength={256} required /></label>
      <label className="field"><span>Введите UPDATE_SETTING</span><input name="confirmation" autoComplete="off" required /></label>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="form-actions"><button className="button button-primary button-small" type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить лимит"}</button><button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => setEditing(false)}>Отмена</button></div>
    </form>}
    {notice && <p className="notice" role="status">{notice}</p>}{error && !editing && <p className="inline-error" role="alert">{error}</p>}
  </article>;
}
