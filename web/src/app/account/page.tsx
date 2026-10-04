import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, Building2, Heart, Plus, Rows3 } from "lucide-react";
import { AccountNav } from "@/components/account-nav";
import { serverApi } from "@/lib/server-api";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Кабинет" };

export default async function AccountPage() {
  const session = await requireSession("/account");
  const [listings, favorites, company] = await Promise.allSettled([serverApi.meListings(), serverApi.favorites(), serverApi.company()]);
  const listingCount = listings.status === "fulfilled" ? listings.value.pagination?.total ?? listings.value.items.length : null;
  const favoriteCount = favorites.status === "fulfilled" ? favorites.value.items.length : null;
  const companyData = company.status === "fulfilled" ? company.value.company : null;
  const failed = listings.status === "rejected" || favorites.status === "rejected" || company.status === "rejected";
  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Здравствуйте, {session.user.display_name}</h1><p>{session.user.email}</p></header>
      <AccountNav current="/account" />
      {failed && <p className="notice" role="status">Не удалось загрузить часть сведений кабинета. Недоступные счётчики отмечены тире; откройте соответствующий раздел или повторите позже.</p>}
      <div className="quick-links account-shortcuts">
        <Link href="/sell"><Plus size={16} /> Новое объявление</Link>
        <Link href="/account/listings"><Rows3 size={16} /> Мои объявления <span>{listingCount ?? "—"}</span></Link>
        <Link href="/account/favorites"><Heart size={16} /> Избранное <span>{favoriteCount ?? "—"}</span></Link>
        <Link href="/account/company"><Building2 size={16} /> {company.status === "rejected" ? "Сведения о компании недоступны" : companyData ? companyData.name : "Подключить компанию"} <ArrowRight size={14} /></Link>
      </div>
      <section className="section">
        <div className="section-heading"><h2>Что дальше</h2></div>
        <div className="help-grid">
          <article className="help-item"><h3>Продайте автомобиль</h3><p>Сохраните черновик, добавьте фотографии и отправьте объявление на проверку.</p><Link className="text-link" href="/sell">Начать подачу <ArrowRight size={15} /></Link></article>
          <article className="help-item"><h3>Управляйте объявлениями</h3><p>Проверяйте статус модерации, снимайте объявление с публикации или отмечайте продажу.</p><Link className="text-link" href="/account/listings">Открыть список <ArrowRight size={15} /></Link></article>
        </div>
      </section>
    </div>
  );
}
