import type { Metadata } from "next";
import Link from "next/link";
import { AccountNav } from "@/components/account-nav";
import { FavoritePriceDropToggle } from "@/components/favorite-price-drop-toggle";
import { ListingCard } from "@/components/listing-card";
import { serverApi } from "@/lib/server-api";
import { requireSession } from "@/lib/server";
import type { FavoriteListing } from "@/lib/types";
import styles from "./favorites.module.css";

export const metadata: Metadata = { title: "Избранное" };

export default async function FavoritesPage() {
  await requireSession("/account/favorites");
  let items: FavoriteListing[] | null;
  try { items = (await serverApi.favorites()).items; } catch { items = null; }
  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Избранное</h1></header>
      <AccountNav current="/account/favorites" />
      {items === null ? <p className="notice" role="status">Не удалось загрузить избранное. Обновите страницу чуть позже.</p> : items.length ? <>
        <aside className={styles.alertInfo} aria-label="Уведомления о снижении цены">
          <p>Если после включения продавец снизит цену в той же валюте, уведомление появится в кабинете при включённом канале «Уведомления в кабинете». Снижения до включения не рассылаются.</p>
          <Link href="/account/notifications">Входящие и настройки уведомлений</Link>
        </aside>
        <div className="listing-grid">
          {items.map((item) => <div className={styles.favoriteItem} key={item.id}>
            <ListingCard listing={item} saved />
            <FavoritePriceDropToggle listingId={item.id} listingTitle={item.title} initialEnabled={item.price_drop_notifications_enabled} />
          </div>)}
        </div>
      </> : <div className="empty-state"><h2>Здесь пока пусто</h2><p className="muted">Сохраняйте объявления, чтобы быстро вернуться к ним.</p><Link className="button button-secondary" href="/cars">Найти автомобиль</Link></div>}
    </div>
  );
}
