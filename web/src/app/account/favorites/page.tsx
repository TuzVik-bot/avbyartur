import type { Metadata } from "next";
import Link from "next/link";
import { AccountNav } from "@/components/account-nav";
import { ListingCard } from "@/components/listing-card";
import { serverApi } from "@/lib/server-api";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Избранное" };

export default async function FavoritesPage() {
  await requireSession("/account/favorites");
  let items;
  try { items = (await serverApi.favorites()).items; } catch { items = null; }
  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Избранное</h1></header>
      <AccountNav current="/account/favorites" />
      {items === null ? <p className="notice" role="status">Не удалось загрузить избранное. Обновите страницу чуть позже.</p> : items.length ? <div className="listing-grid">{items.map((item) => <ListingCard key={item.id} listing={item} saved />)}</div> : <div className="empty-state"><h2>Здесь пока пусто</h2><p className="muted">Сохраняйте объявления, чтобы быстро вернуться к ним.</p><Link className="button button-secondary" href="/cars">Найти автомобиль</Link></div>}
    </div>
  );
}
