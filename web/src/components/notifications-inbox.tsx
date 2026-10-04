"use client";

import { Bell, Check, ExternalLink, Inbox, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { api, ApiClientError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { UserNotification, UserNotificationList } from "@/lib/types";

type NotificationsInboxProps = {
  initialItems: UserNotification[];
  initialUnreadCount: number;
  initialLoadError?: boolean;
};

function safeHref(value: string) {
  const trimmed = value.trim();
  return trimmed.startsWith("/") && !trimmed.startsWith("//") ? trimmed : "/cars";
}

function messageFor(error: unknown, fallback: string) {
  if (error instanceof ApiClientError && error.fieldErrors && Object.keys(error.fieldErrors).length) return Object.values(error.fieldErrors).join(" ");
  return error instanceof Error ? error.message : fallback;
}

function notificationDate(value: string) {
  return formatDate(value);
}

export function NotificationsInbox({ initialItems, initialUnreadCount, initialLoadError = false }: NotificationsInboxProps) {
  const [items, setItems] = useState(initialItems);
  const [unreadCount, setUnreadCount] = useState(Math.max(0, initialUnreadCount));
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(!initialLoadError);

  const visibleItems = useMemo(() => onlyUnread ? items.filter((item) => !item.read_at) : items, [items, onlyUnread]);

  async function refresh() {
    setBusy("refresh");
    setError("");
    try {
      const result: UserNotificationList = await api.notifications({ limit: 50 });
      setItems(result.items);
      setUnreadCount(Math.max(0, result.unread_count));
      setLoaded(true);
    } catch (issue) {
      setError(messageFor(issue, "Не удалось обновить уведомления."));
    } finally {
      setBusy(null);
    }
  }

  async function markRead(item: UserNotification) {
    if (item.read_at) return;
    setBusy(`read:${item.id}`);
    setError("");
    try {
      await api.markNotificationRead(item.id);
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, read_at: new Date().toISOString() } : entry));
      setUnreadCount((current) => Math.max(0, current - 1));
    } catch (issue) {
      setError(messageFor(issue, "Не удалось отметить уведомление прочитанным."));
    } finally {
      setBusy(null);
    }
  }

  return <div className="notifications-inbox">
    <section className="notification-support-note" aria-labelledby="notification-support-title">
      <div className="notification-support-icon" aria-hidden="true"><Bell size={18} /></div>
      <div>
        <h2 id="notification-support-title">Уведомления о новых автомобилях</h2>
        <p>Web-инбокс работает. Email-настройка сохраняется, но письма не отправляются; SMS и Telegram для этих уведомлений пока недоступны.</p>
        <a className="text-link" href="/account/saved-searches">Настроить сохранённые поиски <ExternalLink size={14} aria-hidden="true" /></a>
      </div>
    </section>

    <div className="notifications-toolbar">
      <div>
        <p className="eyebrow">Личный кабинет</p>
        <h2>Входящие</h2>
        <p className="muted">{unreadCount > 0 ? `Непрочитано: ${unreadCount}` : "Все сообщения прочитаны"}</p>
      </div>
      <div className="notifications-toolbar-actions">
        <label className="check-field"><input type="checkbox" checked={onlyUnread} onChange={(event) => setOnlyUnread(event.target.checked)} /> Только непрочитанные</label>
        <button className="button button-secondary button-small" type="button" onClick={() => void refresh()} disabled={busy === "refresh"}>
          <RefreshCw size={14} aria-hidden="true" /> {busy === "refresh" ? "Обновляем…" : "Обновить"}
        </button>
      </div>
    </div>

    {error && loaded && <p className="notice" role="alert">{error}</p>}

    {!loaded ? <div className="empty-state notification-retry-state" role="alert">
      <h2>Не удалось загрузить уведомления</h2>
      <p className="muted">{error || "Не удалось загрузить уведомления. Повторите попытку."}</p>
      <button className="button button-secondary" type="button" onClick={() => void refresh()} disabled={busy === "refresh"}>{busy === "refresh" ? "Обновляем…" : "Повторить"}</button>
    </div> : visibleItems.length > 0 ? <div className="notification-list" aria-live="polite">
      {visibleItems.map((item) => {
        const unread = !item.read_at;
        const itemBusy = busy === `read:${item.id}`;
        return <article className={`notification-item${unread ? " is-unread" : ""}`} key={item.id}>
          <div className="notification-item-mark" aria-hidden="true">{unread ? <span /> : <Check size={15} />}</div>
          <div className="notification-item-content">
            <div className="notification-item-topline">
              <span className="notification-kind"><Inbox size={14} aria-hidden="true" /> Сохранённый поиск</span>
              <time className="muted" dateTime={item.created_at}>{notificationDate(item.created_at)}</time>
            </div>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
            <div className="notification-item-actions">
              <a className="text-link" href={safeHref(item.url)}>Открыть объявление <ExternalLink size={14} aria-hidden="true" /></a>
              {unread && <button className="button button-secondary button-small" type="button" onClick={() => void markRead(item)} disabled={itemBusy}>{itemBusy ? "Сохраняем…" : "Отметить прочитанным"}</button>}
            </div>
          </div>
        </article>;
      })}
    </div> : <div className="empty-state">
      <h2>{onlyUnread ? "Непрочитанных сообщений нет" : "Пока нет уведомлений"}</h2>
      <p className="muted">Когда новое объявление совпадёт с активным сохранённым поиском, оно появится здесь.</p>
      <a className="button button-secondary" href="/account/saved-searches">Открыть сохранённые поиски</a>
    </div>}
  </div>;
}
