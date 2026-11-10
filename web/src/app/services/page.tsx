import type { Metadata } from "next";
import Link from "next/link";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";
import { InformationalPage } from "@/components/informational-page";

const description = "Как выбрать СТО и подготовиться к обслуживанию автомобиля.";
export const metadata: Metadata = { title: "Автоуслуги", description, alternates: { canonical: siteUrl("/services") }, openGraph: buildOpenGraph({ title: "Автоуслуги", description, path: "/services" }) };

export default function ServicesPage() {
  return <InformationalPage eyebrow="Сервисы" title="Автоуслуги" description="Как выбрать СТО и подготовиться к обслуживанию автомобиля." sections={[{ id: "services-search", title: "Поиск автосервиса" }, { id: "services-prepare", title: "Перед обращением" }, { id: "services-work", title: "После диагностики" }, { id: "services-buy", title: "Проверка перед покупкой" }]}>
    <section className="info-section" aria-labelledby="services-search"><h2 id="services-search">Поиск автосервиса</h2><p>Для поиска СТО, шиномонтажа или ремонта можно воспользоваться внешним каталогом AVSERVICE.BY. До записи уточните у исполнителя адрес, специализацию, наличие нужного оборудования и время приёма.</p><a className="text-link" href="https://www.avservice.by/directory" target="_blank" rel="noreferrer">Перейти в каталог AVSERVICE.BY</a><p>Это сторонний ресурс: Авторынок не принимает через эту страницу заявки на ремонт и не подтверждает качество работы отдельных исполнителей.</p></section>
    <section className="info-section" aria-labelledby="services-prepare"><h2 id="services-prepare">Перед обращением</h2><ul className="info-list"><li>Опишите симптомы и условия, при которых они появляются. Подготовьте марку, модель, год и сведения о предыдущих работах.</li><li>Попросите предварительно объяснить диагностику, возможные работы и порядок согласования дополнительных расходов.</li><li>Уточните стоимость, сроки, происхождение запчастей и условия гарантии непосредственно у выбранного исполнителя.</li><li>После работ сохраните заказ-наряд, документы об оплате и перечень заменённых деталей.</li></ul></section>
    <section className="info-section" aria-labelledby="services-work"><h2 id="services-work">После диагностики</h2><p>Попросите объяснить результаты, отдельно указать срочные работы и те, которые можно запланировать позже. Согласуйте объём ремонта и стоимость запчастей до начала работ, а при изменении цены попросите согласовать её заново.</p><p>При получении автомобиля проверьте выполненные работы и сохраните документы исполнителя: они помогут при дальнейших обращениях по обслуживанию или гарантии.</p></section>
    <section className="info-section" aria-labelledby="services-buy"><h2 id="services-buy">Проверка перед покупкой</h2><p>До сделки договоритесь о независимой диагностике и попросите заключение по обнаруженным неисправностям. Сравните её результаты с документами и состоянием автомобиля.</p><Link className="text-link" href="/useful-information/check-car-before-buying">Чеклист проверки автомобиля</Link></section>
  </InformationalPage>;
}
