import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, CheckCircle2, CreditCard, Megaphone, ShieldCheck } from "lucide-react";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = {
  title: "Продвижение объявлений",
  description: "Форматы продвижения объявлений и доступность заказа на Авторынке."
};

export default function PromotionPage() {
  return (
    <InformationalPage
      eyebrow="Коммерческие функции"
      title="Продвижение объявлений"
      description="Узнайте о форматах продвижения и текущей доступности заказа."
      sections={[{ id: "promotion-status", title: "Доступность заказа" }, { id: "promotion-services", title: "Виды продвижения" }, { id: "promotion-available", title: "Что доступно сейчас" }]}
    >
      <section className="info-section" aria-labelledby="promotion-status">
        <div className="info-card">
          <div className="section-heading">
            <h2 id="promotion-status"><Megaphone size={20} aria-hidden="true" /> Доступность заказа</h2>
            <span className="status-pill status-pending">Готовится</span>
          </div>
          <p>Владельцу активного объявления ссылка на услуги доступна в карточке и в разделе «Мои объявления». Кабинет показывает настроенные активные тарифы, если они есть, но покупка сейчас отключена.</p>
          <p className="muted">В кабинете отображаются название, стоимость и срок настроенного активного тарифа. Заказ и оплата недоступны.</p>
        </div>
      </section>

      <section className="info-section" aria-labelledby="promotion-services">
        <div className="section-heading"><h2 id="promotion-services">Виды продвижения</h2></div>
        <ul className="info-list">
          <li><ArrowRight size={18} aria-hidden="true" /><span><strong>Поднять объявление</strong> — формат повышения позиции в выдаче.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span><strong>Выделить объявление</strong> — визуальное оформление объявления в выдаче.</span></li>
          <li><Megaphone size={18} aria-hidden="true" /><span><strong>Разместить вверху</strong> — формат для показа объявления выше в выдаче.</span></li>
          <li><CreditCard size={18} aria-hidden="true" /><span><strong>PRO</strong> — отдельная подписка для автокомпаний; подробности указаны на странице <Link className="text-link" href="/pro-subscription">PRO для компаний</Link>.</span></li>
        </ul>
      </section>

      <section className="info-section" aria-labelledby="promotion-available">
        <div className="section-heading">
          <h2 id="promotion-available">Что доступно сейчас</h2>
        </div>
        <ul className="info-list">
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Подать объявление вручную, сохранить его как черновик и добавить фотографии.</span></li>
          <li><ShieldCheck size={18} aria-hidden="true" /><span>Заполнить форму объявления и увидеть его актуальный статус в кабинете.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Управлять жизненным циклом объявления: снять с публикации или отметить продажу.</span></li>
        </ul>
      </section>


      <nav className="quick-links" aria-label="Дальше">
        <span>Полезные ссылки:</span>
        <Link className="button button-secondary" href="/account/billing">Посмотреть тарифы в кабинете <ArrowRight size={16} /></Link>
        <Link className="button button-primary" href="/sell">Подать объявление <ArrowRight size={16} /></Link>
        <Link className="button button-secondary" href="/help">Помощь <ArrowRight size={16} /></Link>
      </nav>
    </InformationalPage>
  );
}
