import type { Metadata } from "next";
import Link from "next/link";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = { title: "О проекте" };

export default function AboutPage() {
  return (
    <InformationalPage
      eyebrow="О проекте"
      title="Авторынок BY — закрытый пилот"
      description="Площадка для поиска автомобилей и проверки сценария подачи объявления в Беларуси."
      notice="Пилотная версия: доступ предоставляется оператором, а содержание и процессы ещё проходят проверку."
    >
      <section className="info-section">
        <h2>Что уже работает</h2>
        <p>Гость может искать опубликованные объявления, открывать карточку автомобиля и запросить контакт продавца. Владелец предоставленной учётной записи может создать черновик, добавить фото, отправить его на премодерацию, а после публикации приостановить, возобновить или отметить объявление как проданное. Уведомления по сохранённым поискам появляются в кабинете и отмечаются прочитанными.</p>
        <p>Компании проходят отдельную проверку. Решения модератора и изменения статуса сохраняются в серверной истории.</p>
      </section>
      <section className="info-section">
        <h2>Границы текущей версии</h2>
        <ul className="info-list">
          <li>Публичной регистрации, SMS-входа и восстановления пароля нет.</li>
          <li>Платежей, кредита, чата и внешних фидов дилеров нет. Email, SMS и Telegram-доставка уведомлений пока не подключены.</li>
          <li>Пилот закрыт внешним барьером доступа и помечен как noindex; данные предназначены для тестирования.</li>
        </ul>
      </section>
      <section className="info-section">
        <h2>Куда перейти дальше</h2>
        <div className="info-links">
          <Link className="button button-primary" href="/cars">Искать автомобили</Link>
          <Link className="button button-secondary" href="/help">Открыть помощь</Link>
          <Link className="button button-secondary" href="/support">Поддержка пилота</Link>
        </div>
      </section>
    </InformationalPage>
  );
}
