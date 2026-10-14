import { MessageCircle, Phone } from "lucide-react";
import type { ListingMessengerChannel } from "@/lib/api";

function safeMessengerUri(channel: ListingMessengerChannel["channel"], rawUri: string) {
  try {
    const url = new URL(rawUri);
    if (url.protocol !== "https:" || url.username || url.password || url.port || url.search || url.hash) return null;
    const host = url.hostname.toLowerCase();
    if (channel === "telegram" && (host === "t.me" || host === "telegram.me") && url.pathname.length > 1) return url.toString();
    if (channel === "viber" && (host === "viber.me" || host === "viber.com" || host.endsWith(".viber.com")) && url.pathname.length > 1) return url.toString();
  } catch { /* Invalid provider data is omitted. */ }
  return null;
}

export function ListingContactActions({
  active, guestContactRevealEnabled, phone, busy, error, onReveal, messengers = []
}: {
  active: boolean;
  guestContactRevealEnabled: boolean;
  phone: string;
  busy: boolean;
  error: string;
  onReveal: () => void;
  messengers?: ListingMessengerChannel[];
}) {
  if (!active) return <p className="muted">Контакт недоступен для проданного автомобиля.</p>;
  const channels = phone ? messengers.flatMap((item) => {
    if (item.opted_in !== true) return [];
    const href = safeMessengerUri(item.channel, item.uri);
    return href ? [{ ...item, href }] : [];
  }) : [];

  return <>
    {!phone && !busy && guestContactRevealEnabled && <p className="muted">Телефон можно посмотреть без входа в аккаунт.</p>}
    {phone ? <div className="phone-revealed"><strong>{phone}</strong><span className="muted">Контакт продавца</span></div> : <button className="button button-primary contact-reveal" type="button" aria-busy={busy} disabled={busy} onClick={onReveal}><Phone size={17} /> {busy ? "Загружаем телефон…" : "Показать телефон"}</button>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    {channels.map((item) => <a className="button button-secondary" href={item.href} key={item.channel} target="_blank" rel="noopener noreferrer">
      <MessageCircle size={17} aria-hidden="true" /> {item.channel === "telegram" ? "Telegram" : "Viber"}
    </a>)}
  </>;
}
