import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";
import { VinFormatCheck } from "@/components/vin-format-check";

export const metadata: Metadata = {
  title: "Проверка авто по VIN",
  description: "Статус сервиса проверки автомобиля по VIN на Авторынке."
};

export default function VinCheckPage() {
  return (
    <InformationalPage
      eyebrow="Сервисы"
      title="Проверка авто по VIN"
      description="Проверка формата VIN и информация о доступности отчёта об истории автомобиля."
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
        </div>
      </section>
    </InformationalPage>
  );
}
