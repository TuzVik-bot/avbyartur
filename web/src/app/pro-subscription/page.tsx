import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, BarChart3, Building2, CheckCircle2, CreditCard, Users } from "lucide-react";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = {
  title: "Pro для компаний",
  description: "Статус профессиональной подписки для компаний в закрытом пилоте Авторынка."
};

export default function ProSubscriptionPage() {
  return (
    <InformationalPage
      eyebrow="Коммерческие функции"
      title="Pro для компаний"
      description="Черновой статус будущего расширенного кабинета для автосалонов и других компаний. В закрытом пилоте подписка не подключается."
    >
      <section className="info-section" aria-labelledby="pro-status">
        <div className="info-card">
          <div className="section-heading">
            <h2 id="pro-status"><Building2 size={20} aria-hidden="true" /> Статус подписки</h2>
            <span className="status-pill status-pending">Не доступна</span>
          </div>
          <p>Тарифы, счета, платежи и управление подпиской пока не реализованы. Эта страница фиксирует направление работ и не создаёт обязательств по подключению.</p>
          <p className="muted">Условия Pro будут определены отдельно после проверки коммерческой модели и юридических документов.</p>
        </div>
      </section>

      <section className="info-section" aria-labelledby="pro-pilot">
        <div className="section-heading">
          <h2 id="pro-pilot">Что уже есть в пилоте</h2>
        </div>
        <ul className="info-list">
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Базовый профиль компании и публичная страница после решения модератора.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Ручная подача объявлений от имени допущенной компании.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Премодерация объявлений и отображение текущих статусов в кабинете.</span></li>
        </ul>
      </section>

      <section className="info-section" aria-labelledby="pro-next">
        <div className="section-heading">
          <h2 id="pro-next">Что относится к следующему этапу</h2>
        </div>
        <div className="info-card">
          <ul className="info-list">
            <li><Users size={18} aria-hidden="true" /><span>Командные роли и управление сотрудниками компании.</span></li>
            <li><BarChart3 size={18} aria-hidden="true" /><span>Расширенная статистика и инструменты для работы с наличием.</span></li>
            <li><CreditCard size={18} aria-hidden="true" /><span>Согласованные тарифы, счета и безопасное подключение оплаты.</span></li>
          </ul>
        </div>
      </section>

      <nav className="quick-links" aria-label="Разделы для компаний">
        <span>Сейчас можно:</span>
        <Link className="button button-primary" href="/account/company">Открыть кабинет компании <ArrowRight size={16} /></Link>
        <Link className="button button-secondary" href="/dealers">Посмотреть компании <ArrowRight size={16} /></Link>
      </nav>
    </InformationalPage>
  );
}
