import Link from "next/link";
import { FooterChannels } from "./footer-channels";
import { advertisementSections } from "@/lib/advertisement-sections";
import styles from "./site-footer.module.css";

type FooterLink = { href: string; label: string };

const informationLinks: FooterLink[] = [
      { href: "/about", label: "О нас" },
      { href: "/faq", label: "Часто задаваемые вопросы" },
      { href: "/support", label: "Служба поддержки" },
      { href: "/partner", label: "Информация для рекламодателей" },
      { href: "/help", label: "Помощь и документы" },
      { href: "/useful-information", label: "Полезная информация" },
      { href: "/suggest-topic", label: "Предложить тему редакции" },
      { href: "/commenting-rules", label: "Правила комментирования" },
      { href: "/material-using", label: "Правила использования материалов" },
      { href: "/promotion", label: "Продвижение" },
      { href: "/pro-subscription", label: "PRO-подписка" },
      { href: "/dealers", label: "Компаниям" },
      { href: "/sell", label: "Подать объявление" },
      { href: "/customs-calculator", label: "Таможенный калькулятор" },
      { href: "/currency-converter", label: "Конвертер валют" },
      { href: "/vin-check", label: "Проверка авто по VIN" },
      { href: "/sale-contract", label: "Договор купли-продажи" }
];

const legalLinks: FooterLink[] = [
      { href: "/terms-of-use", label: "Пользовательское соглашение" },
      { href: "/privacy-policy", label: "Политика конфиденциальности" },
      { href: "/cookie-policy", label: "Политика использования cookie-файлов" },
      { href: "/submitting-advert", label: "Правила подачи объявлений" },
      { href: "/credit-policy", label: "Согласие на обработку персональных данных для фин. организаций" }
];

function FooterList({ links }: { links: FooterLink[] }) {
  return <ul>{links.map((link) => <li key={link.href}><Link href={link.href}>{link.label}</Link></li>)}</ul>;
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className={`page-width footer-inner ${styles.inner}`}>
        <Link className="footer-brand" href="/">Авторынок <span>BY</span></Link>
        <nav className={styles.links} aria-label="Дополнительная навигация">
          <section className={`footer-group ${styles.group}`} aria-labelledby="footer-advertisements">
            <h2 className="footer-group-title" id="footer-advertisements">Объявления</h2>
            <FooterList links={[...advertisementSections]} />
          </section>
          <section className={`footer-group ${styles.group}`} aria-labelledby="footer-information">
            <h2 className="footer-group-title" id="footer-information">Информация и разделы</h2>
            <FooterList links={informationLinks} />
          </section>
          <details className={`footer-group ${styles.legal}`}>
            <summary className="footer-group-title">Правовая информация</summary>
            <FooterList links={legalLinks} />
          </details>
        </nav>
        <FooterChannels />
        <p className="footer-note">Закрытый пилот. Данные и контакты предназначены для тестирования.</p>
      </div>
    </footer>
  );
}
