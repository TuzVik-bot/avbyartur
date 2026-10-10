"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Ban, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { api, ApiClientError, createIdempotencyKey } from "@/lib/api";
import { listingHref } from "@/lib/format";
import { MAX_CONVERSATION_MESSAGE_LENGTH, type ConversationThread } from "@/lib/types";

function messageTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ru-BY", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function errorMessage(issue: unknown, fallback: string) {
  if (issue instanceof ApiClientError && Object.keys(issue.fieldErrors).length) return Object.values(issue.fieldErrors).join(" ");
  return issue instanceof Error ? issue.message : fallback;
}

export function ConversationThreadView({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const nextPath = `/account/messages/${encodeURIComponent(conversationId)}`;
  const [thread, setThread] = useState<ConversationThread | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [actionError, setActionError] = useState("");
  const [messageError, setMessageError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [readError, setReadError] = useState("");
  const [markingRead, setMarkingRead] = useState(false);
  const [confirmBlock, setConfirmBlock] = useState(false);
  const [blocking, setBlocking] = useState(false);
  const sendKey = useRef<{ body: string; key: string } | null>(null);
  const readKey = useRef<string | null>(null);
  const readInFlight = useRef(false);
  const blockKey = useRef<string | null>(null);
  const loadingOlderRef = useRef(false);
  const messageListRef = useRef<HTMLDivElement>(null);
  const olderScrollAnchor = useRef<{ height: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const anchor = olderScrollAnchor.current;
    const list = messageListRef.current;
    if (!anchor || !list) return;
    list.scrollTop = anchor.top + list.scrollHeight - anchor.height;
    olderScrollAnchor.current = null;
  }, [thread]);

  const markRead = useCallback(async () => {
    if (readInFlight.current) return;
    setReadError("");
    setMarkingRead(true);
    readInFlight.current = true;
    const key = readKey.current ?? createIdempotencyKey();
    readKey.current = key;
    try {
      await api.markConversationRead(conversationId, key);
      readKey.current = null;
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      else setReadError(errorMessage(issue, "Не удалось отметить сообщения прочитанными."));
    } finally {
      readInFlight.current = false;
      setMarkingRead(false);
    }
  }, [conversationId, nextPath, router]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    setActionError("");
    try {
      const result = await api.conversation(conversationId);
      setThread(result);
      setHistoryError("");
      await markRead();
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      else setLoadError(errorMessage(issue, "Не удалось загрузить переписку."));
    } finally {
      setLoading(false);
    }
  }, [conversationId, markRead, nextPath, router]);

  useEffect(() => { void load(); }, [load]);

  const loadOlderMessages = useCallback(async () => {
    const current = thread;
    const cursor = current?.next_before_sequence;
    if (!current || !current.has_more || cursor === null || cursor === undefined || loadingOlderRef.current) return;
    setHistoryError("");
    loadingOlderRef.current = true;
    setLoadingOlder(true);
    try {
      const olderPage = await api.conversation(conversationId, { beforeSequence: cursor });
      const list = messageListRef.current;
      olderScrollAnchor.current = list ? { height: list.scrollHeight, top: list.scrollTop } : null;
      setThread((existing) => {
        if (!existing) return existing;
        const visibleIds = new Set(existing.messages.map((message) => message.id));
        const olderMessages = olderPage.messages.filter((message) => !visibleIds.has(message.id));
        return {
          ...existing,
          messages: [...olderMessages, ...existing.messages],
          has_more: olderPage.has_more,
          next_before_sequence: olderPage.next_before_sequence
        };
      });
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      else setHistoryError(errorMessage(issue, "Не удалось загрузить более ранние сообщения."));
    } finally {
      loadingOlderRef.current = false;
      setLoadingOlder(false);
    }
  }, [conversationId, nextPath, router, thread]);

  async function sendMessage(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = draft.trim();
    if (sending || !body || !thread || thread.conversation.blocked_by_me || thread.conversation.is_blocked) return;
    setMessageError("");
    if (draft.length > MAX_CONVERSATION_MESSAGE_LENGTH) {
      setMessageError(`Сообщение не должно превышать ${MAX_CONVERSATION_MESSAGE_LENGTH} символов.`);
      return;
    }
    const attempt = sendKey.current?.body === body ? sendKey.current : { body, key: createIdempotencyKey() };
    sendKey.current = attempt;
    setSending(true);
    try {
      const result = await api.sendConversationMessage(conversationId, body, attempt.key);
      sendKey.current = null;
      setThread((current) => current ? {
        ...current,
        conversation: { ...current.conversation, last_message: result.message, last_message_at: result.message.created_at },
        messages: [...current.messages, result.message]
      } : current);
      setDraft("");
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      else setMessageError(errorMessage(issue, "Не удалось отправить сообщение."));
    } finally {
      setSending(false);
    }
  }

  async function blockConversation() {
    if (blocking || !thread) return;
    setActionError("");
    const key = blockKey.current ?? createIdempotencyKey();
    blockKey.current = key;
    setBlocking(true);
    try {
      await api.blockConversation(conversationId, key);
      blockKey.current = null;
      setThread((current) => current ? { ...current, conversation: { ...current.conversation, blocked_by_me: true } } : current);
      setConfirmBlock(false);
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      else setActionError(errorMessage(issue, "Не удалось заблокировать переписку."));
    } finally {
      setBlocking(false);
    }
  }

  const conversation = thread?.conversation;
  const blocked = Boolean(conversation && (conversation.blocked_by_me || conversation.is_blocked));
  const counterpart = conversation?.participants.find((participant) => participant.id !== user?.id) ?? conversation?.participants[0];
  const listingLink = conversation ? listingHref({ id: conversation.listing.id, slug: conversation.listing.slug, category_code: conversation.listing.category_code, make: null, model: null }) : "/cars";

  return <section className="conversation-thread" aria-labelledby="conversation-thread-title">
    <Link className="conversation-back-link" href="/account/messages"><ArrowLeft size={15} aria-hidden="true" /> Все переписки</Link>
    <aside className="conversation-safety-note" role="note">
      <AlertTriangle size={19} aria-hidden="true" />
      <p>Не переводите предоплату незнакомым продавцам и не переходите по внешним ссылкам из сообщений.</p>
    </aside>

    {loading && !thread ? <div className="empty-state conversation-loading" role="status" aria-busy="true">Загружаем переписку…</div>
      : loadError ? <div className="empty-state conversation-retry" role="alert">
        <h2>Не удалось загрузить переписку</h2>
        <p className="muted">{loadError}</p>
        <button className="button button-secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> {loading ? "Загружаем…" : "Повторить"}</button>
      </div>
        : thread && conversation ? <>
          <header className="conversation-thread-header">
            <div>
              <p className="eyebrow">{counterpart?.display_name || "Собеседник"}</p>
              <h1 id="conversation-thread-title">{conversation.listing.title}</h1>
              <Link className="text-link" href={listingLink}>Открыть объявление</Link>
            </div>
            {!blocked && <button className="button button-secondary button-small" type="button" onClick={() => setConfirmBlock(true)}><Ban size={15} aria-hidden="true" /> Заблокировать</button>}
          </header>

          {blocked && <p className="conversation-blocked-note" role="status"><Ban size={16} aria-hidden="true" /> {conversation.blocked_by_me ? "Вы заблокировали эту переписку. Отправка сообщений отключена." : "Переписка заблокирована собеседником. Отправка сообщений отключена."}</p>}
          {confirmBlock && !blocked && <div className="conversation-block-confirm" role="group" aria-label="Подтверждение блокировки">
            <p>Заблокировать собеседника? Новые сообщения в этой переписке будут отключены.</p>
            <button className="button button-secondary button-small" type="button" onClick={() => { blockKey.current = null; setConfirmBlock(false); }}>Отмена</button>
            <button className="button button-danger button-small" type="button" onClick={() => void blockConversation()} disabled={blocking} aria-busy={blocking}>{blocking ? "Блокируем…" : "Заблокировать"}</button>
          </div>}
          {actionError && <p className="inline-error" role="alert">{actionError}</p>}
          {readError && <div className="conversation-action-retry" role="alert">
            <p>{readError}</p>
            <button className="button button-secondary button-small" type="button" onClick={() => void markRead()} disabled={markingRead} aria-busy={markingRead}><RefreshCw size={14} aria-hidden="true" /> {markingRead ? "Повторяем…" : "Повторить отметку о прочтении"}</button>
          </div>}

          {historyError && <p className="inline-error conversation-thread-history-error" role="alert">{historyError}</p>}
          {thread.has_more && <div className="conversation-history-paging">
            <button className="button button-secondary button-small" type="button" onClick={() => void loadOlderMessages()} disabled={loadingOlder} aria-busy={loadingOlder}>
              {loadingOlder ? "Загружаем историю…" : historyError ? "Повторить загрузку истории" : "Загрузить более ранние сообщения"}
            </button>
          </div>}

          <div ref={messageListRef} className="conversation-message-list" role="log" aria-label="Сообщения в переписке" aria-live="polite" aria-relevant="additions text">
            {thread.messages.length === 0 ? <p className="muted conversation-empty-messages">В этой переписке пока нет сообщений.</p> : thread.messages.map((item) => {
              const ownMessage = item.sender_id === user?.id;
              return <article className={`conversation-message${ownMessage ? " is-mine" : ""}`} key={item.id}>
                <p className="conversation-message-body">{item.body}</p>
                <time className="conversation-message-time" dateTime={item.created_at}>{messageTime(item.created_at)}{ownMessage && item.read_at ? " · прочитано" : ""}</time>
              </article>;
            })}
          </div>

          {!blocked ? <form className="conversation-compose" onSubmit={sendMessage}>
            <label className="field"><span>Сообщение</span><textarea name="message" value={draft} onChange={(event) => {
              const next = event.target.value;
              if (sendKey.current && next.trim() !== sendKey.current.body) sendKey.current = null;
              setDraft(next);
            }} rows={3} maxLength={MAX_CONVERSATION_MESSAGE_LENGTH} required placeholder="Напишите сообщение…" /></label>
            <span className="conversation-character-count" aria-live="polite">{draft.length}/{MAX_CONVERSATION_MESSAGE_LENGTH} символов</span>
            {messageError && <p className="inline-error" role="alert">{messageError}</p>}
            <div className="conversation-compose-actions">
              <span className="muted conversation-plain-text-note"><ShieldCheck size={14} aria-hidden="true" /> Отправляется только текст</span>
              <button className="button button-primary" type="submit" disabled={sending || !draft.trim() || draft.length > MAX_CONVERSATION_MESSAGE_LENGTH} aria-busy={sending}><Send size={16} aria-hidden="true" /> {sending ? "Отправляем…" : "Отправить"}</button>
            </div>
          </form> : <p className="muted conversation-plain-text-note"><ShieldCheck size={14} aria-hidden="true" /> Сообщения в заблокированной переписке отправить нельзя.</p>}
        </> : null}
  </section>;
}
