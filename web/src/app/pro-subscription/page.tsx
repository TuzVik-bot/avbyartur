import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, BarChart3, Building2, CheckCircle2, CreditCard, Users } from "lucide-react";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = {
  title: "Pro для компаний",
  description: "Возможности кабинета компании и доступность подписки PRO на Авторынке."
};

export default function ProSubscriptionPage() {
  return (
    <InformationalPage
      eyebrow="Коммерческие функции"
      title="Pro для компаний"
      description="Информация о возможностях кабинета компании и доступности подписки PRO."
      sections={[{ id: "pro-status", title: "Статус подписки" }, { id: "pro-account", title: "Как работать с кабинетом" }, { id: "pro-pilot", title: "Что уже есть в кабинете компании" }]}
    >
      <section className="info-section" aria-labelledby="pro-status">
        <div className="info-card">
          <div className="section-heading">
            <h2 id="pro-status"><Building2 size={20} aria-hidden="true" /> Статус подписки</h2>
            <span className="status-pill status-pending">Недоступна</span>
          </div>
          <p>Система поддерживает тарифы для компаний, но активный пакет может отсутствовать. Если он настроен, его параметры видны в разделе тарифов кабинета. Создать заказ и оплатить подписку сейчас нельзя.</p>
          <p className="muted">Срок, стоимость и состав платного PRO будут указаны до покупки после утверждения условий и подключения платежного сервиса.</p>
        </div>
      </section>

      <section className="info-section" aria-labelledby="pro-account">
        <h2 id="pro-account">Как работать с кабинетом</h2>
        <p>В кабинете компании можно поддерживать профиль и объявления в актуальном состоянии, а также проверять текущий статус объявлений после подачи. Доступные действия зависят от роли сотрудника.</p>
        <p>В разделе тарифов отображаются активные настроенные предложения, если они есть. Изучите название, срок и стоимость тарифа; оформление и оплата подписки сейчас недоступны.</p>
      </section>

      <section className="info-section" aria-labelledby="pro-pilot">
        <div className="section-heading">
          <h2 id="pro-pilot">Что уже есть в кабинете компании</h2>
        </div>
        <ul className="info-list">
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Базовый профиль компании и публичная страница после решения модератора.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Ручная подача объявлений от имени допущенной компании.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Отображение текущих статусов объявлений в кабинете.</span></li>
          <li><Users size={18} aria-hidden="true" /><span>Управление командой компании: сотрудники и их роли в кабинете.</span></li>
          <li><BarChart3 size={18} aria-hidden="true" /><span>Аналитика объявлений с отдельными счётчиками просмотров, показов телефона, диалогов и переходов к компании.</span></li>
        </ul>
        <p className="muted">Показатели аналитики — независимые агрегаты. Они не связывают действия одного посетителя и сами по себе не подтверждают состоявшийся звонок или сообщение.</p>
      </section>


      <nav className="quick-links" aria-label="Разделы для компаний">
        <span>Сейчас можно:</span>
        <Link className="button button-secondary" href="/account/billing"><CreditCard size={16} /> Проверить тарифы</Link>
        <Link className="button button-primary" href="/account/company">Открыть кабинет компании <ArrowRight size={16} /></Link>
        <Link className="button button-secondary" href="/dealers">Посмотреть компании <ArrowRight size={16} /></Link>
      </nav>
    </InformationalPage>
  );
}
