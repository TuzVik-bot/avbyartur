import type { Metadata } from "next";
import Link from "next/link";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = { title: "Предложить тему", description: "Темы, которые могут помочь покупателям и продавцам разобраться в работе площадки." };

export default function Page() {
  return (
    <InformationalPage eyebrow="Обратная связь" title="Предложить тему" description="Темы, которые могут помочь покупателям и продавцам разобраться в работе площадки." sections={[{ id: "topics", title: "Какие темы полезны" }, { id: "prepare", title: "Как подготовить предложение" }]}>
      <section className="info-section"><h2 id="topics">Какие темы полезны</h2><ul className="info-list"><li>Поиск автомобиля и работа с фильтрами.</li><li>Подготовка фотографий и заполнение объявления.</li><li>Работа с кабинетом, сообщениями и уведомлениями.</li><li>Проверка автомобиля и безопасное общение с продавцом.</li></ul></section>
      <section className="info-section"><h2 id="prepare">Как подготовить предложение</h2><p>Сформулируйте вопрос, опишите задачу и укажите, какой информации вам не хватило. Не включайте пароли, платёжные данные или персональные сведения других людей.</p><p>Отдельной формы отправки предложений сейчас нет. Если речь об объявлении, используйте жалобу в его карточке; инструкции по другим ситуациям собраны в разделе поддержки.</p><div className="info-links"><Link className="button button-secondary" href="/support">Поддержка</Link><Link className="button button-secondary" href="/help">Помощь</Link></div></section>
    </InformationalPage>
  );
}
