"use client";

import { Send } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiClientError } from "@/lib/api";

type TelegramStatus = {
  linked: boolean;
  linked_at: string | null;
  bot_username: string;
  channel_available: boolean;
};

export function AccountTelegram() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [linkCode, setLinkCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    try {
      const next = await api.telegramStatus();
      setStatus(next);
      if (next.linked) setLinkCode("");
    } catch {
      setStatus((current) => current);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function startLink() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.telegramLinkStart();
      setLinkCode(result.code);
      setStatus((current) => current ? { ...current, bot_username: result.bot_username || current.bot_username } : current);
    } catch (issue) {
      setError(issue instanceof ApiClientError && issue.status === 503
        ? "Telegram-уведомления ещё не настроены владельцем портала."
        : "Не удалось получить код. Повторите попытку позже.");
    } finally {
      setBusy(false);
    }
  }

  async function unlink() {
    if (typeof window !== "undefined" && !window.confirm("Отвязать Telegram? Уведомления в мессенджер перестанут приходить.")) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await api.telegramUnlink();
      setStatus(next);
      setNotice("Telegram отвязан.");
    } catch {
      setError("Не удалось отвязать Telegram. Повторите попытку позже.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="section" aria-labelledby="telegram-heading">
    <div className="section-heading"><div><p className="eyebrow">Уведомления</p><h2 id="telegram-heading">Telegram</h2></div><Send size={20} aria-hidden="true" /></div>
    {status === null ? <p className="muted">Загружаем статус Telegram…</p> : !status.channel_available ? <p className="muted">Telegram-уведомления пока не настроены. Этот раздел появится, когда владелец портала подключит бота.</p> : status.linked ? <div>
      <p className="inline-success" role="status">Аккаунт привязан{status.linked_at ? ` (${new Date(status.linked_at).toLocaleDateString("ru-RU")})` : ""}. Канал «Telegram» доступен в сохранённых поисках.</p>
      <button className="button button-secondary" type="button" onClick={() => void unlink()} disabled={busy}>Отвязать</button>
    </div> : <div>
      <p className="muted">Привяжите аккаунт, чтобы получать уведомления о новых объявлениях в Telegram.</p>
      {linkCode ? <div>
        <p>Откройте бота {status.bot_username ? <strong>@{status.bot_username}</strong> : "в Telegram"} и отправьте ему команду:</p>
        <p><code className="telegram-code">/start {linkCode}</code></p>
        <p className="muted">Статус обновится автоматически после команды боту.</p>
        <div className="form-actions">
          <button className="button button-secondary" type="button" onClick={() => void refresh()} disabled={busy}>Проверить статус</button>
          <button className="button button-secondary" type="button" onClick={() => void startLink()} disabled={busy}>Новый код</button>
        </div>
      </div> : <button className="button" type="button" onClick={() => void startLink()} disabled={busy}>Получить код привязки</button>}
    </div>}
    {notice && <p className="inline-success" role="status">{notice}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </section>;
}
