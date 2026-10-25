import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Сотрудничество с Авторынком для автосалонов, дилеров, автосервисов и медиа в Беларуси.";
export const metadata: Metadata = {
  title: "Партнёрам",
  description,
  alternates: { canonical: siteUrl("/partner") },
  openGraph: buildOpenGraph({ title: "Партнёрам", description, path: "/partner" }),
};

export default function PartnerPage() {
  return (
    <InformationalPage
      eyebrow="Партнёрам"
      title="Сотрудничество"
      description="Информация для компаний и владельцев данных, которые хотят обсудить пилот."
      notice="Коммерческие условия, тарифы и договорные реквизиты ещё не утверждены. Эта страница не является офертой."
    >
      <section className="info-section">
        <h2>Что предусмотрено сейчас</h2>
        <p>В пилоте компания может вести профиль после проверки и подавать объявления от имени компании. Объявления проходят общую премодерацию, а лимиты и доступные действия задаются сервером пилота.</p>
      </section>
      <section className="info-section">
        <h2>Что нужно согласовать отдельно</h2>
        <ul className="info-list">
          <li>реквизиты и статус юридического лица;</li>
          <li>право использовать фотографии, описания и товарные знаки;</li>
          <li>условия обработки данных и канал обмена материалами;</li>
          <li>коммерческие модели, продвижение и интеграции после пилота.</li>
        </ul>
        <p>В текущем интерфейсе нет подключения внешней выгрузки, платного продвижения или оплаты. Передайте предложение оператору способом, которым вы получили доступ.</p>
      </section>
    </InformationalPage>
  );
}
