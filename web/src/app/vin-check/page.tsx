import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = {
  title: "Проверка авто по VIN",
  description: "Статус сервиса проверки автомобиля по VIN на Авторынке."
};

export default function VinCheckPage() {
  return (
    <InformationalPage
      eyebrow="Сервисы"
      title="Проверка авто по VIN"
      description="Проверка истории автомобиля по его идентификационному номеру."
    >
      <section className="info-section" aria-labelledby="vin-check-status">
        <div className="info-card">
          <div className="section-heading">
            <h2 id="vin-check-status">Статус сервиса</h2>
            <span className="status-pill status-pending">Пока недоступен</span>
          </div>
          <p>Поставщик отчётов об истории автомобиля ещё не подключён. Сейчас получить отчёт по VIN на Авторынке нельзя.</p>
        </div>
      </section>
      <section className="info-section" aria-labelledby="vin-location">
        <div className="info-card">
          <h2 id="vin-location">Где найти VIN</h2>
          <p>VIN указан в документах на автомобиль и на самом автомобиле. Сверьте номер в документах с маркировкой на кузове перед покупкой.</p>
        </div>
      </section>
    </InformationalPage>
  );
}
