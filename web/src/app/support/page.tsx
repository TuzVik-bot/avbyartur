import type { Metadata } from "next";
import Link from "next/link";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = { title: "Поддержка" };

export default function SupportPage() {
  return (
    <InformationalPage
      eyebrow="Поддержка"
      title="Поддержка закрытого пилота"
      description="Проверим проблему по шагам и сохраним данные для оператора пилота."
      notice="В текущем интерфейсе нет публичной формы тикетов, чата или обещанного времени ответа. Напишите оператору способом, которым вы получили приглашение в пилот."
    >
      <section className="info-section">
        <h2>Что приложить к сообщению</h2>
        <ul className="info-list">
          <li>страницу и действие, на котором появилась проблема;</li>
          <li>время ошибки и короткое описание ожидаемого результата;</li>
          <li>идентификатор объявления, если он виден в адресе или кабинете;</li>
          <li>скриншот без пароля, cookie, CSRF-токена и других секретов.</li>
        </ul>
      </section>
      <section className="info-section">
        <h2>Перед обращением</h2>
        <p>Для проблем с поиском обновите страницу и проверьте фильтры. Для подачи объявления сохраните черновик и дождитесь статуса «готово» у всех фотографий. Если вход не выполняется, проверьте адрес учётной записи и обратитесь к оператору: самостоятельного сброса пароля нет.</p>
        <p><Link className="text-link" href="/faq">Посмотреть ответы на частые вопросы</Link></p>
      </section>
    </InformationalPage>
  );
}
