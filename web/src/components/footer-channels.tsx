import { Instagram, Youtube } from "lucide-react";
import type { ReactNode } from "react";
import styles from "./footer-channels.module.css";

const telegramIcon = <path d="m21 3-4 18-6-5-3 3 1-6 8-7-10 6-5-2Z" />;
const vkIcon = <path d="M3 5h3c.3 5 2 8 4 9V5h3v5c2-1 3-3 4-5h4c-1 3-3 5-5 7 2 1 4 4 5 7h-4c-1-2-2-4-4-5v5h-1C6 19 3 14 3 5Z" />;
const appleIcon = <path d="M16.4 2c.1 1.3-.5 2.6-1.3 3.5-.8.9-2 1.5-3.1 1.4-.2-1.2.4-2.5 1.2-3.3.9-1 2.2-1.6 3.2-1.6ZM20 17c-.5 1.2-.8 1.8-1.5 2.9-.9 1.3-2.1 3-3.6 3-1.3 0-1.7-.8-3.5-.8s-2.3.8-3.5.8c-1.5 0-2.6-1.5-3.5-2.8C2 16.5 1.5 12 3 9.7 4 8 5.7 7 7.3 7c1.4 0 2.5.9 3.6.9 1 0 2.6-1 4.2-1 1.4 0 2.9.8 3.8 2-3.3 1.8-2.8 6.5 1.1 8.1Z" />;

function Glyph({ children }: { children: ReactNode }) {
  return <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">{children}</svg>;
}

// Add approved profile and application URLs here when they are available.
const socialChannels = [
  { label: "Telegram", href: "", icon: <Glyph>{telegramIcon}</Glyph> },
  { label: "Instagram", href: "", icon: <Instagram size={24} aria-hidden="true" /> },
  { label: "VK", href: "", icon: <Glyph>{vkIcon}</Glyph> },
  { label: "YouTube", href: "", icon: <Youtube size={24} aria-hidden="true" /> }
];

const appStores = [
  { label: "Google Play", href: "", icon: <Glyph><path d="M3 2 14 12 3 22Z" fill="#34a853" /><path d="m3 2 14 8-3 2Z" fill="#4285f4" /><path d="m14 12 3-2 5 2-5 2Z" fill="#fbbc04" /><path d="m3 22 11-10 3 2Z" fill="#ea4335" /></Glyph> },
  { label: "App Store", href: "", icon: <Glyph>{appleIcon}</Glyph> }
];

function Channel({ href, label, className, children }: { href: string; label: string; className: string; children: ReactNode }) {
  return href
    ? <a href={href} className={className} aria-label={label} target="_blank" rel="noopener noreferrer">{children}</a>
    : <span className={className} role="link" aria-label={label} aria-disabled="true" title={`${label} — ссылка скоро появится`}>{children}</span>;
}

export function FooterChannels() {
  return (
    <div className={styles.channels}>
      <section aria-labelledby="footer-social-title">
        <h2 className="footer-group-title" id="footer-social-title">Мы в соцсетях</h2>
        <div className={styles.socials}>
          {socialChannels.map(({ label, href, icon }) => <Channel key={label} href={href} label={label} className={styles.social}>{icon}</Channel>)}
        </div>
      </section>
      <section aria-labelledby="footer-apps-title">
        <h2 className="footer-group-title" id="footer-apps-title">Мобильное приложение</h2>
        <div className={styles.stores}>
          {appStores.map(({ label, href, icon }) => (
            <Channel key={label} href={href} label={label} className={styles.store}>
              {icon}<span><span className={styles.caption}>Скоро в</span><span className={styles.storeName}>{label}</span></span>
            </Channel>
          ))}
        </div>
      </section>
    </div>
  );
}
