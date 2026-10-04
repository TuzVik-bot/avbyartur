import Link from "next/link";
import { Activity, BookOpenText, FileText, Gauge, ScrollText, Settings2, Users } from "lucide-react";

const tabs = [
  { href: "/admin", label: "Сводка", icon: Gauge },
  { href: "/admin/users", label: "Пользователи", icon: Users },
  { href: "/admin/audit", label: "Аудит", icon: ScrollText },
  { href: "/admin/catalog", label: "Справочники", icon: BookOpenText },
  { href: "/admin/catalog-requests", label: "Запросы каталога", icon: BookOpenText },
  { href: "/admin/settings", label: "Лимиты", icon: Settings2 },
  { href: "/admin/tariffs", label: "Тарифы", icon: FileText },
  { href: "/admin/content", label: "Материалы", icon: FileText },
  { href: "/admin/monitoring", label: "Мониторинг", icon: Activity }
];

export function AdminNav({ current }: { current: string }) {
  return <nav className="account-nav" aria-label="Администрирование">{tabs.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={current === href ? "page" : undefined}><Icon size={16} /> {label}</Link>)}</nav>;
}
