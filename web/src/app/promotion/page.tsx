import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, CheckCircle2, Megaphone, ShieldCheck } from "lucide-react";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = {
  title: "Продвижение объявлений",
  description: "Статус продвижения объявлений в закрытом пилоте Авторынка."
};

export default function PromotionPage() {
  return (
    <InformationalPage
      eyebrow="Коммерческие функции"
      title="Продвижение объявлений"
      description="Здесь будет описание платных способов выделить автомобиль в выдаче. В текущем закрытом пилоте функция ещё не подключена."
    >
      <section className="info-section" aria-labelledby="promotion-status">
        <div className="info-card">
          <div className="section-heading">
            <h2 id="promotion-status"><Megaphone size={20} aria-hidden="true" /> Статус в пилоте</h2>
            <span className="status-pill status-pending">Готовится</span>
          </div>
          <p>Продвижение, тарифы, платежи и callbacks пока не реализованы. Поэтому в кабинете нельзя выбрать услугу, провести платёж или изменить позицию объявления.</p>
          <p className="muted">Это информационная страница будущего коммерческого режима, а не предложение купить услугу.</p>
        </div>
      </section>

      <section className="info-section" aria-labelledby="promotion-available">
        <div className="section-heading">
          <h2 id="promotion-available">Что доступно сейчас</h2>
        </div>
        <ul className="info-list">
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Подать объявление вручную, сохранить его как черновик и добавить фотографии.</span></li>
          <li><ShieldCheck size={18} aria-hidden="true" /><span>Пройти премодерацию и увидеть актуальный статус объявления в кабинете.</span></li>
          <li><CheckCircle2 size={18} aria-hidden="true" /><span>Управлять жизненным циклом объявления: снять с публикации или отметить продажу.</span></li>
        </ul>
      </section>

      <section className="info-section" aria-labelledby="promotion-before-launch">
        <div className="section-heading">
          <h2 id="promotion-before-launch">До коммерческого запуска</h2>
        </div>
        <div className="info-card">
          <p>Нужно отдельно согласовать состав услуг и правила показа, юридические условия, возвраты и провайдера оплаты. После этого функция должна пройти отдельную проверку на тестовом стенде и в интерфейсе кабинета.</p>
        </div>
      </section>

      <nav className="quick-links" aria-label="Дальше">
        <span>В закрытом пилоте:</span>
        <Link className="button button-primary" href="/sell">Подать объявление <ArrowRight size={16} /></Link>
        <Link className="button button-secondary" href="/help">Правила пилота <ArrowRight size={16} /></Link>
      </nav>
    </InformationalPage>
  );
}
