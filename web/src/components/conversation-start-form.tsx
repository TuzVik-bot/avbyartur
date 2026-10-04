"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { AlertTriangle, Send } from "lucide-react";
import { api, ApiClientError, createIdempotencyKey } from "@/lib/api";
import { MAX_CONVERSATION_MESSAGE_LENGTH } from "@/lib/types";

export function ConversationStartForm({ listingId, listingTitle }: { listingId: string; listingTitle: string }) {
  const router = useRouter();
  const nextPath = `/account/messages/new?listing_id=${encodeURIComponent(listingId)}`;
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const actionKey = useRef<{ body: string; key: string } | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = message.trim();
    if (busy || !body) return;
    setError("");
    if (message.length > MAX_CONVERSATION_MESSAGE_LENGTH) {
      setError(`Сообщение не должно превышать ${MAX_CONVERSATION_MESSAGE_LENGTH} символов.`);
      return;
    }
    const attempt = actionKey.current?.body === body ? actionKey.current : { body, key: createIdempotencyKey() };
    actionKey.current = attempt;
    setBusy(true);
    try {
      const result = await api.createConversation(listingId, body, attempt.key);
      actionKey.current = null;
      router.replace(`/account/messages/${encodeURIComponent(result.conversation.id)}`);
      router.refresh();
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      else if (issue instanceof ApiClientError && Object.keys(issue.fieldErrors).length) setError(Object.values(issue.fieldErrors).join(" "));
      else setError(issue instanceof Error ? issue.message : "Не удалось начать переписку. Повторите попытку.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="conversation-start-card" aria-labelledby="conversation-start-title">
    <p className="eyebrow">Новое сообщение</p>
    <h2 id="conversation-start-title">{listingTitle}</h2>
    <aside className="conversation-safety-note" role="note">
      <AlertTriangle size={19} aria-hidden="true" />
      <p>Не переводите предоплату незнакомым продавцам и не переходите по внешним ссылкам из сообщений.</p>
    </aside>
    <form className="conversation-compose" onSubmit={submit}>
      <label className="field"><span>Ваше сообщение продавцу</span><textarea name="message" value={message} onChange={(event) => {
        const next = event.target.value;
        if (actionKey.current && next.trim() !== actionKey.current.body) actionKey.current = null;
        setMessage(next);
      }} rows={5} maxLength={MAX_CONVERSATION_MESSAGE_LENGTH} required placeholder="Здравствуйте! Подскажите, пожалуйста, автомобиль ещё продаётся?" /></label>
      <span className="conversation-character-count" aria-live="polite">{message.length}/{MAX_CONVERSATION_MESSAGE_LENGTH} символов</span>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="conversation-compose-actions">
        <Link className="button button-secondary" href="/account/messages">Отмена</Link>
        <button className="button button-primary" type="submit" disabled={busy || !message.trim() || message.length > MAX_CONVERSATION_MESSAGE_LENGTH} aria-busy={busy}>
          <Send size={16} aria-hidden="true" /> {busy ? "Отправляем…" : "Отправить сообщение"}
        </button>
      </div>
    </form>
  </section>;
}
