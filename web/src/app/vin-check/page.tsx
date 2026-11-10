import type { Metadata } from "next";
import Link from "next/link";
import { InformationalPage } from "@/components/informational-page";
import { VinFormatCheck } from "@/components/vin-format-check";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

export const metadata: Metadata = {
  title: "Проверка авто по VIN",
  description: "Статус сервиса проверки автомобиля по VIN на Авторынке.",
  alternates: { canonical: siteUrl("/vin-check") },
  openGraph: buildOpenGraph({
    title: "Проверка авто по VIN",
    description: "Статус сервиса проверки автомобиля по VIN на Авторынке.",
    path: "/vin-check",
  }),
};

export default function VinCheckPage() {
  return (
    <InformationalPage
      eyebrow="Сервисы"
      title="Проверка авто по VIN"
      description="Проверка формата VIN и информация о доступности отчёта об истории автомобиля."
      sections={[{ id: "vin-format-section", title: "Проверка формата" }, { id: "vin-check-status", title: "Статус сервиса" }, { id: "vin-location", title: "Где найти VIN" }, { id: "vin-next", title: "Что проверить дальше" }]}
    >
      <section className="info-section" aria-labelledby="vin-format-section">
        <div className="info-card">
          <h2 id="vin-format-section">Проверка формата</h2>
          <p>Можно проверить, соответствует ли номер формату стандартного 17-символьного VIN. Историю автомобиля эта проверка не запрашивает.</p>
          <VinFormatCheck />
        </div>
      </section>
      <section className="info-section" aria-labelledby="vin-check-status">
        <div className="info-card">
          <div className="section-heading">
            <h2 id="vin-check-status">Статус сервиса</h2>
            <span className="status-pill status-pending">Пока недоступен</span>
          </div>
          <p>Поставщик отчётов об истории автомобиля ещё не подключён. Заказать или получить отчёт по VIN на Авторынке пока нельзя.</p>
          <p>Совпадение с форматом не подтверждает подлинность VIN, комплектацию, пробег, ДТП или историю регистрации.</p>
        </div>
      </section>
      <section className="info-section" aria-labelledby="vin-location">
        <div className="info-card">
          <h2 id="vin-location">Где найти VIN</h2>
          <p>VIN указан в документах на автомобиль и на самом автомобиле. Сверьте номер в документах с маркировкой на кузове перед покупкой.</p>
          <p>Место маркировки зависит от модели. Если номер трудно прочитать или видны следы изменений, попросите специалиста осмотреть автомобиль до сделки.</p>
        </div>
      </section>
      <section className="info-section" aria-labelledby="vin-next">
        <h2 id="vin-next">Что проверить дальше</h2>
        <p>На Едином портале электронных услуг Беларуси можно изучить доступные сведения об автомобиле и условия их получения. Например, в перечне есть проверка розыска по полному совпадению VIN. Доступ и стоимость уточняйте в карточке услуги.</p>
        <p><a className="text-link" href="https://e-pasluga.by/services/gai-transport" target="_blank" rel="noreferrer">Государственные услуги по транспорту</a></p>
        <p>Объедините сведения из официальных источников с осмотром документов и независимой диагностикой. <Link className="text-link" href="/useful-information/check-car-before-buying">Открыть чеклист покупателя</Link>.</p>
      </section>
    </InformationalPage>
  );
}
