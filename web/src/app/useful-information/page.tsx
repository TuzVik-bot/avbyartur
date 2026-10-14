import type { Metadata } from "next";
import { ArrowUpRight, Building2, Wrench } from "lucide-react";
import { InformationalPage } from "@/components/informational-page";

export const metadata: Metadata = { title: "Полезная информация" };

const directories = [
  {
    title: "Автосервисы и СТО",
    description: "Поиск по городам Беларуси: техническое обслуживание, ремонт, шиномонтаж и другие автоуслуги.",
    provider: "AVSERVICE.BY",
    href: "https://www.avservice.by/directory",
    action: "Открыть каталог",
    icon: Wrench,
  },
  {
    title: "Автосалоны и дилеры",
    description: "Каталог автосалонов, автохаусов и дилеров с фильтрами по городам и маркам.",
    provider: "Автопортал BY",
    href: "https://avtoportal.by/cat/avtosalony-belarusi/",
    action: "Открыть список",
    icon: Building2,
  },
] as const;

export default function UsefulInformationPage() {
  return (
    <InformationalPage
      eyebrow="Для автомобилистов"
      title="Полезная информация"
      description="Автоцентры, автосервисы и дилеры Беларуси. Выберите каталог и уточните адрес, услуги и график работы у его владельца."
      notice={<>Сейчас здесь собраны ссылки на действующие каталоги. Единого подтверждённого реестра всех автоцентров Беларуси и разрешённого к копированию набора данных мы не нашли, поэтому адреса и телефоны сторонних организаций не переносим без согласованного источника.</>}
    >
      <section className="info-section" aria-labelledby="auto-center-directories-title">
        <h2 id="auto-center-directories-title">Каталоги автоцентров</h2>
        <div className="useful-directory-grid">
          {directories.map(({ title, description, provider, href, action, icon: Icon }) => (
            <article className="info-card useful-directory-card" key={href}>
              <div className="useful-directory-icon"><Icon size={20} aria-hidden="true" /></div>
              <h3>{title}</h3>
              <p>{description}</p>
              <a className="text-link" href={href} target="_blank" rel="noreferrer">
                {action} <ArrowUpRight size={16} aria-hidden="true" />
              </a>
              <p className="useful-directory-source">Источник: {provider}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="info-section">
        <h2>Перед поездкой</h2>
        <ul className="info-list">
          <li>проверьте адрес и часы работы непосредственно в выбранном каталоге;</li>
          <li>уточните, обслуживает ли центр вашу марку и выполняет нужную работу;</li>
          <li>позвоните заранее, чтобы подтвердить запись и наличие нужных запчастей.</li>
        </ul>
      </section>
    </InformationalPage>
  );
}
