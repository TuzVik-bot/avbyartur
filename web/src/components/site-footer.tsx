import Link from "next/link";
import { FooterChannels } from "./footer-channels";
import { FooterGroup } from "./footer-group";
import { ContactClickConsent } from "./contact-click-consent";
import { SiteAssistant } from "./site-assistant";
import styles from "./site-footer.module.css";
import { advertisementSections } from "@/lib/advertisement-sections";

type FooterLink = { href: string; label: string };

type FooterGroup = {
  id: string;
  title: string;
  links: FooterLink[];
};

const footerGroups: FooterGroup[] = [
  { id: "advertisements", title: "Объявления", links: [...advertisementSections] },
  {
    id: "information",
    title: "Информация",
    links: [
      { href: "/about", label: "О нас" },
      { href: "/faq", label: "Часто задаваемые вопросы" },
      { href: "/support", label: "Служба поддержки" },
      { href: "/partner", label: "Информация для рекламодателей" },
      { href: "/help", label: "Помощь и документы" },
      { href: "/useful-information", label: "Полезная информация" }
    ]
  },
  {
    id: "editorial",
    title: "Редакция",
    links: [
      { href: "/suggest-topic", label: "Предложить тему редакции" },
      { href: "/commenting-rules", label: "Правила комментирования" },
      { href: "/material-using", label: "Правила использования материалов" }
    ]
  },
  {
    id: "rules-and-policies",
    title: "Правила и политики",
    links: [
      { href: "/terms-of-use", label: "Пользовательское соглашение" },
      { href: "/privacy-policy", label: "Политика конфиденциальности" },
      { href: "/cookie-policy", label: "Политика использования cookie-файлов" },
      { href: "/submitting-advert", label: "Правила подачи объявлений" },
      { href: "/credit-policy", label: "Финансовые предложения и данные" }
    ]
  },
  {
    id: "sections",
    title: "Разделы",
    links: [
      { href: "/promotion", label: "Продвижение" },
      { href: "/pro-subscription", label: "PRO-подписка" },
      { href: "/dealers", label: "Компаниям" },
      { href: "/sell", label: "Подать объявление" },
      { href: "/customs-calculator", label: "Таможенный калькулятор" },
      { href: "/currency-converter", label: "Конвертер валют" },
      { href: "/vin-check", label: "Проверка авто по VIN" },
      { href: "/sale-contract", label: "Договор купли-продажи" }
    ]
  }
];

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="page-width footer-inner">
        <Link className="footer-brand" href="/">Авторынок <span>BY</span></Link>
        <nav className="footer-links" aria-label="Дополнительная навигация">
          {footerGroups.map((group) => (
            <FooterGroup key={group.id} id={group.id} title={group.title}>
              <ul>
                {group.links.map((link) => (
                  <li key={link.href}><Link href={link.href}>{link.label}</Link></li>
                ))}
              </ul>
            </FooterGroup>
          ))}
        </nav>
        <FooterChannels />
        <p className="footer-note">Авторынок — поиск и продажа транспорта в Беларуси. Сведения в объявлениях предоставляют продавцы и внешние источники.</p>
        <div className={styles.utilities}>
          <ContactClickConsent />
          <SiteAssistant />
        </div>
      </div>
    </footer>
  );
}
