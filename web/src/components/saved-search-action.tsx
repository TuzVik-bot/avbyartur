"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { BellRing, BookmarkPlus, Check, Save } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "@/components/auth-provider";
import { categoryPath } from "@/lib/listing-categories";
import type { ListingSearch } from "@/lib/types";
import { ApiClientError, apiRequest } from "@/lib/api";

type SavedSearchActionProps = {
  search: ListingSearch;
  title: string;
};

function canonicalSearch(search: ListingSearch) {
  const pairs: Array<[string, string]> = [];
  for (const key of Object.keys(search).sort()) {
    if (key === "page" || key === "page_size") continue;
    const value = search[key as keyof ListingSearch];
    const values = Array.isArray(value) ? [...new Set(value)].sort() : [value];
    for (const entry of values) {
      if (entry === undefined || entry === null || entry === "") continue;
      pairs.push([key, String(entry)]);
    }
  }
  const params = new URLSearchParams(pairs);
  const filters: Record<string, string | string[]> = {};
  for (const [key, value] of pairs) {
    if (key === "equipment") {
      const current = filters[key];
      filters[key] = current === undefined ? [value] : [...(Array.isArray(current) ? current : [current]), value];
    } else {
      filters[key] = value;
    }
  }
  const path = categoryPath(search.category_code || "cars");
  return { url: params.size ? `${path}?${params.toString()}` : path, filters };
}

function messageFor(error: unknown) {
  if (error instanceof ApiClientError && error.fieldErrors && Object.keys(error.fieldErrors).length) {
    return Object.values(error.fieldErrors).join(" ");
  }
  return error instanceof Error ? error.message : "Не удалось сохранить поиск.";
}

function idempotencyKey() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `saved-search-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function SavedSearchAction({ search, title }: SavedSearchActionProps) {
  const router = useRouter();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(title.trim().slice(0, 120));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<"saved" | "subscribed" | null>(null);
  const canonical = canonicalSearch(search);
  const loginHref = `/login?next=${encodeURIComponent(canonical.url)}`;

  async function submit(intent: "save" | "subscribe", event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setError("");
    const cleanName = name.trim();
    if (!cleanName) {
      setError("Укажите название поиска.");
      return;
    }
    setBusy(true);
    try {
      const created = await apiRequest<{ saved_search: { id: string; revision: number } }>("me/saved-searches", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey() },
        body: JSON.stringify({
          name: cleanName,
          ...canonical,
          notifications_enabled: false,
          notification_channel: null,
          notification_frequency: "daily",
        }),
      });
      if (intent === "save") {
        setResult("saved");
        setOpen(false);
        return;
      }

      try {
        await apiRequest(`me/saved-searches/${encodeURIComponent(created.saved_search.id)}`, {
          method: "PATCH",
          body: JSON.stringify({
            notifications_enabled: true,
            notification_channel: "web",
            notification_frequency: "daily",
            expected_revision: created.saved_search.revision,
          }),
        });
        setResult("subscribed");
        setOpen(false);
      } catch (issue) {
        if (issue instanceof ApiClientError && issue.status === 401) {
          router.push(loginHref);
          return;
        }
        setResult("saved");
        setOpen(false);
        setError(`Поиск сохранён, но подписку включить не удалось. ${messageFor(issue)}`);
      }
    } catch (issue) {
      if (issue instanceof ApiClientError && issue.status === 401) {
        router.push(loginHref);
        return;
      }
      setError(messageFor(issue));
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return <div className="saved-search-action" aria-live="polite">
      <p className="inline-success" role="status"><Check size={15} aria-hidden="true" /> {result === "subscribed" ? "Подписка включена: новые объявления будут приходить раз в день в личном кабинете." : "Поиск сохранён без уведомлений."} <Link className="text-link" href="/account/saved-searches">Управлять поисками</Link></p>
      {error && <p className="notice" role="alert">{error}</p>}
    </div>;
  }

  if (!user) {
    return <div className="saved-search-action">
      <Link className="button button-secondary button-small" href={loginHref}><BookmarkPlus size={15} aria-hidden="true" /> Сохранить поиск</Link>
      <Link className="button button-secondary button-small" href={loginHref}><BellRing size={15} aria-hidden="true" /> Подписаться на новые объявления</Link>
    </div>;
  }

  return <div className="saved-search-action">
    {!open ? <>
      <button className="button button-secondary button-small" type="button" aria-label="Сохранить поиск" onClick={() => { setError(""); setOpen(true); }}>
        <BookmarkPlus size={15} aria-hidden="true" /> Сохранить поиск
      </button>
      <button className="button button-secondary button-small" type="button" aria-label="Подписаться на новые объявления" onClick={() => { setError(""); setOpen(true); }}>
        <BellRing size={15} aria-hidden="true" /> Подписаться на новые объявления
      </button>
    </> : <form className="form-grid saved-search-form" onSubmit={(event) => void submit("save", event)}>
      <label className="field"><span>Название поиска</span><input autoFocus name="saved-search-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required /></label>
      <p className="muted saved-search-frequency">Подписка означает уведомления в личном кабинете раз в день.</p>
      {error && <p className="notice" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="button button-primary button-small" type="submit" disabled={busy}><Save size={14} aria-hidden="true" /> {busy ? "Сохраняем…" : "Сохранить поиск"}</button>
        <button className="button button-secondary button-small" type="button" aria-label="Подписаться на новые объявления" onClick={() => void submit("subscribe")} disabled={busy}><BellRing size={14} aria-hidden="true" /> {busy ? "Подписываем…" : "Подписаться на новые объявления"}</button>
        <button className="button button-secondary button-small" type="button" onClick={() => { setError(""); setOpen(false); }}>Отмена</button>
      </div>
    </form>}
  </div>;
}
