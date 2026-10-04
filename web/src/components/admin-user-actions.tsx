"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { adminApi, type AdminRole, type AdminUser, type AdminUserUpdate } from "@/lib/admin";

export function AdminUserActions({ user, currentUserId, onUpdated }: {
  user: AdminUser;
  currentUserId: string;
  onUpdated?: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const editable = user.status === "active" || user.status === "blocked";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const role = String(form.get("role") || "") as AdminRole;
    const status = String(form.get("status") || "");
    const reason = String(form.get("reason") || "").trim();
    const currentPassword = String(form.get("current_password") || "");
    const confirmed = form.get("confirmation") === "yes";

    if (!currentPassword) { setError("Введите текущий пароль администратора."); return; }
    if (!reason) { setError("Укажите причину изменения."); return; }
    if (!confirmed) { setError("Подтвердите изменение пользователя."); return; }
    if (role === user.role && status === user.status) { setError("Изменений нет."); return; }
    if (!["user", "moderator", "admin"].includes(role) || !["active", "blocked"].includes(status)) {
      setError("Выберите допустимую роль и статус.");
      return;
    }

    const payload: AdminUserUpdate = {
      role,
      status: status as "active" | "blocked",
      expected_role: user.role,
      expected_status: user.status,
      reason,
      confirmation: "UPDATE_USER",
      current_password: currentPassword
    };

    setBusy(true);
    setError("");
    try {
      await adminApi.updateUser(user.id, payload);
      setOpen(false);
      onUpdated?.();
      router.refresh();
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Не удалось изменить права пользователя.");
    } finally {
      setBusy(false);
    }
  }

  if (!editable) return <p className="muted">Изменение недоступно для статуса «{user.status}».</p>;

  return (
    <div className="admin-user-action">
      {!open ? <button className="button button-secondary button-small" type="button" onClick={() => setOpen(true)}>Изменить доступ</button> : (
        <form className="admin-user-form" onSubmit={submit}>
          <label className="field">
            <span>Роль</span>
            <select name="role" defaultValue={user.role}>
              <option value="user">Пользователь</option>
              <option value="moderator">Модератор</option>
              <option value="admin">Администратор</option>
            </select>
          </label>
          <label className="field">
            <span>Статус</span>
            <select name="status" defaultValue={user.status}>
              <option value="active">Активен</option>
              <option value="blocked">Заблокирован</option>
            </select>
          </label>
          <label className="field">
            <span>Причина</span>
            <textarea name="reason" required maxLength={1000} />
          </label>
          <label className="field">
            <span>Текущий пароль администратора</span>
            <input name="current_password" type="password" autoComplete="current-password" required />
          </label>
          <label className="check-field">
            <input name="confirmation" type="checkbox" value="yes" required />
            Подтверждаю изменение пользователя {user.email || user.id}
          </label>
          {error && <p className="inline-error" role="alert">{error}</p>}
          <div className="form-actions">
            <button className="button button-primary button-small" type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить доступ"}</button>
            <button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => { setOpen(false); setError(""); }}>Отмена</button>
          </div>
        </form>
      )}
      {error && !open && <p className="inline-error" role="alert">{error}</p>}
      {currentUserId === user.id && <p className="muted">Изменение своей роли или блокировка собственного аккаунта запрещены сервером.</p>}
    </div>
  );
}
