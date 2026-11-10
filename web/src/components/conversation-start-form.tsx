"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Send } from "lucide-react";
import { api, ApiClientError, createIdempotencyKey } from "@/lib/api";
import { MAX_CONVERSATION_MESSAGE_LENGTH } from "@/lib/types";
import { userMessage } from "@/lib/user-message";

const MESSAGE_TEMPLATES = ["Ещё продаётся?", "Возможен торг?", "Рассматриваете обмен?"] as const;

function draftKey(listingId: string) {
  return `conversation-draft:${listingId}`;
}

// Session storage can be blocked (private mode, disabled site data); drafts are a convenience only.
function readDraft(listingId: string) {
  try {
    return window.sessionStorage.getItem(draftKey(listingId));
  } catch {
    return null;
  }
}

function writeDraft(listingId: string, value: string | null) {
  try {
    if (value === null) window.sessionStorage.removeItem(draftKey(listingId));
    else window.sessionStorage.setItem(draftKey(listingId), value);
  } catch {
    // The draft is simply not kept when storage is unavailable.
  }
}

export function ConversationStartForm({ listingId, listingTitle, exchange = false }: { listingId: string; listingTitle: string; exchange?: boolean }) {
  const router = useRouter();
  const nextPath = `/account/messages/new?listing_id=${encodeURIComponent(listingId)}${exchange ? "&intent=exchange" : ""}`;
  const [message, setMessage] = useState(exchange ? "Здравствуйте! Хочу предложить обмен. Рассмотрите мой автомобиль?" : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const actionKey = useRef<{ body: string; key: string } | null>(null);

  useEffect(() => {
    const draft = readDraft(listingId);
    if (draft) setMessage(draft);
  }, [listingId]);

  function changeMessage(next: string) {
    if (actionKey.current && next.trim() !== actionKey.current.body) actionKey.current = null;
    setMessage(next);
  }

  function insertTemplate(template: string) {
    const current = message.trimEnd();
    changeMessage((current ? `${current} ${template}` : template).slice(0, MAX_CONVERSATION_MESSAGE_LENGTH));
  }

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
      writeDraft(listingId, null);
      router.replace(`/account/messages/${encodeURIComponent(result.conversation.id)}`);
      router.refresh();
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) {
        writeDraft(listingId, message);
        router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      }
      else if (issue instanceof ApiClientError && Object.keys(issue.fieldErrors).length) setError(Object.values(issue.fieldErrors).join(" "));
      else setError(userMessage(issue, "Не удалось начать переписку. Повторите попытку."));
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
      <div className="conversation-templates" role="group" aria-label="Быстрые вопросы продавцу">
        {MESSAGE_TEMPLATES.map((template) => <button key={template} className="button button-secondary button-small" type="button" data-message-template onClick={() => insertTemplate(template)}>{template}</button>)}
      </div>
      <label className="field"><span>Ваше сообщение продавцу</span><textarea name="message" value={message} onChange={(event) => changeMessage(event.target.value)} rows={5} maxLength={MAX_CONVERSATION_MESSAGE_LENGTH} required placeholder="Здравствуйте! Подскажите, пожалуйста, автомобиль ещё продаётся?" /></label>
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
