import type { Metadata } from "next";
import Link from "next/link";
import { InformationalPage } from "@/components/informational-page";
import { serverApi } from "@/lib/server-api";

export const metadata: Metadata = {
  title: "Проверка транспорта по VIN",
  robots: { index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } }
};

type VinCheckStatus = Awaited<ReturnType<typeof serverApi.vinCheckStatus>>;

const unavailable: VinCheckStatus = {
  available: false,
  provider: null,
  supported_categories: [],
  message: "Поставщик проверки VIN пока не подключён."
};

export default async function VinCheckPage() {
  let status: VinCheckStatus = unavailable;
  try {
    status = await serverApi.vinCheckStatus();
  } catch {
    status = { ...unavailable, message: "Не удалось получить статус сервиса проверки VIN." };
  }

  return (
    <InformationalPage
      eyebrow="Сервисы"
      title="Проверка транспорта по VIN"
      description="Перед покупкой важно сверить идентификаторы и изучить доступные сведения об истории транспорта."
      notice={status.message}
    >
      <section className="info-section">
        <h2>Что нужно знать</h2>
        <ul className="info-list">
          <li>Состав отчёта зависит от страны, типа транспорта и источников данных поставщика.</li>
          <li>Отсутствие записи в отчёте не доказывает отсутствие ДТП, ограничений или других событий.</li>
          <li>Пока поставщик не выбран и не подключён, VIN для сервиса проверки не принимается и не сохраняется.</li>
        </ul>
        <p><Link className="text-link" href="/useful-information?topic=vin">Материалы о проверке VIN</Link></p>
      </section>
    </InformationalPage>
  );
}
