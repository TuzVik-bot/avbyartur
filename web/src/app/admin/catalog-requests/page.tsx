import Link from "next/link";
import type { Metadata } from "next";
import { CatalogRequestQueue } from "@/app/admin/catalog-requests/catalog-request-queue";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Не найденные модификации · Модерация" };

export default async function CatalogRequestsPage() {
  const session = await requireSession("/admin/catalog-requests");
  if (session.user.role !== "moderator" && session.user.role !== "admin") {
    return <div className="page-width"><header className="page-head"><h1>Нет доступа</h1><p>Запросы каталога доступны модераторам и администраторам.</p></header><Link className="button button-secondary" href="/account">В кабинет</Link></div>;
  }

  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Рабочая очередь</p><h1>Не найденные модификации</h1><p>Сопоставляйте запросы с существующими модификациями каталога. Одобрение не меняет объявление или справочник.</p></header>
    <p><Link className="button button-secondary button-small" href="/moderation">К очередям модерации</Link></p>
    <CatalogRequestQueue />
  </div>;
}
