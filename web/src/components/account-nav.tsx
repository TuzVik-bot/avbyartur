import Link from "next/link";
import { BarChart3, Bell, Building2, CreditCard, Heart, Inbox, ListChecks, LayoutDashboard, MessageCircle, Radio, Settings, Users } from "lucide-react";

const tabs = [
  { href: "/account", label: "Обзор", icon: LayoutDashboard },
  { href: "/account/listings", label: "Объявления", icon: ListChecks },
  { href: "/account/messages", label: "Сообщения", icon: MessageCircle },
  { href: "/account/favorites", label: "Избранное", icon: Heart },
  { href: "/account/saved-searches", label: "Сохранённые поиски", icon: Bell },
  { href: "/account/notifications", label: "Уведомления", icon: Inbox },
  { href: "/account/billing", label: "Тарифы и заказы", icon: CreditCard },
  { href: "/account/settings", label: "Настройки", icon: Settings },
  { href: "/account/company", label: "Компания", icon: Building2 },
  { href: "/account/company/team", label: "Команда", icon: Users },
  { href: "/account/company/feeds", label: "Интеграции", icon: Radio },
  { href: "/account/company/analytics", label: "Аналитика", icon: BarChart3 }
];

export function AccountNav({ current }: { current: string }) {
  return <nav className="account-nav account-sidebar" aria-label="Кабинет">{tabs.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={current === href ? "page" : undefined}><Icon size={16} /> {label}</Link>)}</nav>;
}
