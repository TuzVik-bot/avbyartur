import type { Metadata } from "next";
import Link from "next/link";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = { title: "Предложить тему" };

export default function SuggestTopicPage() {
  return (
    <InformationalPage
      eyebrow="Обратная связь"
      title="Предложить тему"
      description="Помогите выбрать материалы для справки и следующего этапа пилота."
      notice="Отдельной формы отправки пока нет. Передайте предложение оператору тем же каналом, по которому получили доступ."
    >
      <section className="info-section">
        <h2>Какие темы полезны</h2>
        <ul className="info-list">
          <li>непонятный шаг поиска, входа или подачи объявления;</li>
          <li>пример данных, которого не хватает в каталоге;</li>
          <li>вопрос о доступности, безопасности или приватности;</li>
          <li>идея, которую можно проверить в пределах закрытого пилота.</li>
        </ul>
      </section>
      <section className="info-section">
        <h2>Как сформулировать предложение</h2>
        <p>Опишите задачу пользователя, ожидаемый результат и пример. Не отправляйте пароли, токены, полные cookie, персональные данные третьих лиц или платёжные реквизиты.</p>
        <p><Link className="text-link" href="/support">Если это ошибка, откройте инструкцию поддержки</Link></p>
      </section>
    </InformationalPage>
  );
}
