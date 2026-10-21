import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, BarChart3, Building2, CheckCircle2, CreditCard, Users } from "lucide-react";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = {
  title: "Pro для компаний",
  description: "Статус платной подписки PRO для компаний в закрытом пилоте Авторынка."
};

export default function ProSubscriptionPage() {
  return (
    <InformationalPage
      eyebrow="Коммерческие функции"
      title="Pro для компаний"
      description="Платная подписка PRO предназначена для автокомпаний. В закрытом пилоте её состав и стоимость ещё не утверждены, а оформление и оплата отключены."
    >
      <section className="info-section" aria-labelledby="pro-status">
        <div className="info-card">
          <div className="section-heading">
            <h2 id="pro-status"><Building2 size={20} aria-hidden="true" /> Статус подписки</h2>
            <span className="status-pill status-pending">Не доступна</span>
          </div>
          <p>Система поддерживает тарифы для компаний, но активный пакет может отсутствовать. Если он настроен, его параметры видны в разделе тарифов кабинета. Создать заказ и оплатить подписку сейчас нельзя.</p>
          <p className="muted">Срок, стоимость и состав платного PRO будут указаны до покупки после утверждения условий и подключения платежного сервиса.</p>
        </div>
      </section>

      <section className="info-section" aria-labelledby="pro-pilot">
        <div className="section-heading">
          <h2 id="pro-pilot">Что уже есть в кабинете компании</h2>
        </div>
        <ul className="info-list">
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Базовый профиль компании и публичная страница после решения модератора.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Ручная подача объявлений от имени допущенной компании.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Премодерация объявлений и отображение текущих статусов в кабинете.</span></li>
          <li><Users size={18} aria-hidden="true" /><span>Управление командой компании: сотрудники и их роли в кабинете.</span></li>
          <li><BarChart3 size={18} aria-hidden="true" /><span>Аналитика объявлений с отдельными счётчиками просмотров, показов телефона, диалогов и переходов к компании.</span></li>
        </ul>
        <p className="muted">Показатели аналитики — независимые агрегаты. Они не связывают действия одного посетителя и сами по себе не подтверждают состоявшийся звонок или сообщение.</p>
      </section>

      <section className="info-section" aria-labelledby="pro-next">
        <div className="section-heading">
          <h2 id="pro-next">Что нужно согласовать для платного PRO</h2>
        </div>
        <div className="info-card">
          <ul className="info-list">
            <li><CheckCircle2 size={18} aria-hidden="true" /><span>Состав платного пакета, его стоимость и срок действия.</span></li>
            <li><CheckCircle2 size={18} aria-hidden="true" /><span>Правила оформления, юридические условия и возвраты.</span></li>
            <li><CreditCard size={18} aria-hidden="true" /><span>Согласованные тарифы, счета и безопасное подключение оплаты.</span></li>
          </ul>
        </div>
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
