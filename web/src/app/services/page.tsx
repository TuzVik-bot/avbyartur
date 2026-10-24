import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = { title: "Услуги" };

export default function ServicesPage() {
  return <InformationalPage eyebrow="Для автомобилистов" title="Услуги" description="Автосервисы и СТО: техническое обслуживание, ремонт, шиномонтаж и другие автоуслуги.">
    <section className="info-section">
      <h2>Автосервисы и СТО</h2>
      <p>Найдите исполнителя в каталоге AVSERVICE.BY. Уточняйте стоимость, адрес и время работы непосредственно у выбранного сервиса.</p>
      <a className="text-link" href="https://www.avservice.by/directory" target="_blank" rel="noreferrer">Открыть каталог автоуслуг</a>
    </section>
  </InformationalPage>;
}
