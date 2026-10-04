import Link from "next/link";

type FooterLink = { href: string; label: string };

type FooterGroup = {
  id: string;
  title: string;
  links: FooterLink[];
};

const footerGroups: FooterGroup[] = [
  {
    id: "information",
    title: "Информация",
    links: [
      { href: "/about", label: "О нас" },
      { href: "/faq", label: "Часто задаваемые вопросы" },
      { href: "/support", label: "Служба поддержки" },
      { href: "/partner", label: "Информация для рекламодателей" },
      { href: "/help", label: "Помощь и документы" }
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
      { href: "/credit-policy", label: "Согласие на обработку персональных данных для фин. организаций" }
    ]
  },
  {
    id: "sections",
    title: "Разделы",
    links: [
      { href: "/promotion", label: "Продвижение" },
      { href: "/pro-subscription", label: "PRO-подписка" },
      { href: "/dealers", label: "Компании" },
      { href: "/sell", label: "Подать объявление" }
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
            <section className="footer-group" key={group.id} aria-labelledby={`footer-${group.id}`}>
              <h2 className="footer-group-title" id={`footer-${group.id}`}>{group.title}</h2>
              <ul>
                {group.links.map((link) => (
                  <li key={link.href}><Link href={link.href}>{link.label}</Link></li>
                ))}
              </ul>
            </section>
          ))}
        </nav>
        <p className="footer-note">Закрытый пилот. Данные и контакты предназначены для тестирования.</p>
      </div>
    </footer>
  );
}
