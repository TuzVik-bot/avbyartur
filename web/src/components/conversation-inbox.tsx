"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, MessageCircle, RefreshCw } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { api, ApiClientError } from "@/lib/api";
import type { ConversationSummary } from "@/lib/types";

function conversationTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ru-BY", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function errorMessage(issue: unknown) {
  if (issue instanceof ApiClientError && Object.keys(issue.fieldErrors).length) return Object.values(issue.fieldErrors).join(" ");
  return issue instanceof Error ? issue.message : "Не удалось загрузить переписки.";
}

function loginAfterUnauthorized(issue: unknown, nextPath: string, router: ReturnType<typeof useRouter>) {
  if (issue instanceof ApiClientError && issue.status === 401) {
    router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
    return true;
  }
  return false;
}

export function ConversationInbox() {
  const router = useRouter();
  const { user } = useAuth();
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api.conversations();
      setItems(result.items);
    } catch (issue) {
      if (!loginAfterUnauthorized(issue, "/account/messages", router)) setError(errorMessage(issue));
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => { void load(); }, [load]);

  return <section className="conversation-inbox" aria-labelledby="conversation-inbox-title">
    <aside className="conversation-safety-note" role="note">
      <AlertTriangle size={19} aria-hidden="true" />
      <p>Не переводите предоплату незнакомым продавцам и не переходите по внешним ссылкам из сообщений.</p>
    </aside>

    <div className="conversation-toolbar">
      <div>
        <p className="eyebrow">Личный кабинет</p>
        <h2 id="conversation-inbox-title">Переписки</h2>
      </div>
      <button className="button button-secondary button-small" type="button" onClick={() => void load()} disabled={loading} aria-busy={loading}>
        <RefreshCw size={14} aria-hidden="true" /> {loading ? "Обновляем…" : "Обновить"}
      </button>
    </div>

    {loading && items.length === 0 ? <div className="empty-state conversation-loading" role="status" aria-busy="true">Загружаем переписки…</div>
      : error ? <div className="empty-state conversation-retry" role="alert">
        <h2>Не удалось загрузить переписки</h2>
        <p className="muted">{error}</p>
        <button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}>{loading ? "Обновляем…" : "Повторить"}</button>
      </div>
        : items.length === 0 ? <div className="empty-state">
          <div className="empty-illustration empty-messages-illustration" aria-hidden="true" />
          <h2>Пока нет переписок</h2>
          <p className="muted">Откройте объявление и напишите продавцу, чтобы начать разговор.</p>
          <Link className="button button-secondary" href="/cars">Найти автомобиль</Link>
        </div>
          : <div className="conversation-list" aria-live="polite">
            {items.map((item) => {
              const counterpart = item.participants.find((participant) => participant.id !== user?.id) ?? item.participants[0];
              const blocked = item.blocked_by_me || item.is_blocked;
              const updatedAt = item.last_message_at ?? item.last_message?.created_at ?? null;
              return <Link className={`conversation-card${item.unread_count > 0 ? " is-unread" : ""}`} href={`/account/messages/${encodeURIComponent(item.id)}`} key={item.id}>
                <span className="conversation-avatar" aria-hidden="true"><MessageCircle size={19} /></span>
                <span className="conversation-card-body">
                  <span className="conversation-card-heading">
                    <strong>{counterpart?.display_name || "Собеседник"}</strong>
                    <time className="muted" dateTime={updatedAt || undefined}>{conversationTime(updatedAt)}</time>
                  </span>
                  <span className="conversation-listing-title">{item.listing.title}</span>
                  <span className="conversation-preview">{blocked ? "Переписка заблокирована" : item.last_message?.body || "Переписка началась"}</span>
                </span>
                {item.unread_count > 0 && <span className="conversation-unread-count" aria-label={`Непрочитанных сообщений: ${item.unread_count}`}>{item.unread_count}</span>}
              </Link>;
            })}
          </div>}
  </section>;
}
