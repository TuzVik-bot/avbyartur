import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { SavedSearches, type SavedSearch } from "@/components/saved-searches";
import { requireSession } from "@/lib/server";
import { serverApiRequest } from "@/lib/server-api";

export const metadata: Metadata = { title: "Сохранённые поиски" };

type SearchParams = { from?: string | string[] };

function initialUrl(value: string | string[] | undefined) {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate || !candidate.startsWith("/cars")) return "/cars";
  return candidate;
}

export default async function SavedSearchesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireSession("/account/saved-searches");
  const params = await searchParams;
  let items: SavedSearch[] | null = null;
  try { items = (await serverApiRequest<{ items: SavedSearch[] }>("me/saved-searches")).items.map((item) => item); }
  catch { /* The client receives a clear retry state when the list is unavailable. */ }
  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Сохранённые поиски</h1><p>Сохраняйте фильтры и управляйте уведомлениями о новых объявлениях.</p></header>
    <AccountNav current="/account/saved-searches" />
    {items === null ? <p className="notice" role="status">Не удалось загрузить сохранённые поиски. Обновите страницу чуть позже.</p> : <SavedSearches initialItems={items} initialUrl={initialUrl(params.from)} />}
  </div>;
}
