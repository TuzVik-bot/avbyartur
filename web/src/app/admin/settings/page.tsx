import Link from "next/link";
import type { Metadata } from "next";
import { AdminNav } from "@/components/admin-nav";
import { AdminRuntimeSetting } from "@/components/admin-runtime-setting";
import { adminServerApi } from "@/lib/admin-server";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Лимиты · Администрирование" };

export default async function AdminSettingsPage() {
  const session = await requireSession("/admin/settings");
  if (session.user.role !== "admin") return <div className="page-width"><header className="page-head"><h1>Нет доступа</h1><p>Изменение runtime-лимитов доступно только администраторам.</p></header><Link className="button button-secondary" href="/account">В кабинет</Link></div>;

  let settings: Awaited<ReturnType<typeof adminServerApi.settings>> | null = null;
  try { settings = await adminServerApi.settings(); } catch { /* Provide a visible state rather than presenting stale values. */ }
  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Runtime-конфигурация</p><h1>Лимиты приложения</h1><p>Администраторские изменения требуют повторной проверки пароля, причины и подтверждения. Каждое изменение фиксируется в аудите.</p></header>
    <AdminNav current="/admin/settings" />
    {!settings ? <p className="notice" role="alert">Не удалось загрузить лимиты. Проверьте подключение к API и повторите попытку.</p> : <div className="admin-runtime-settings">{settings.items.length ? settings.items.map((setting) => <AdminRuntimeSetting key={setting.key} initialSetting={setting} />) : <p className="muted">Runtime-лимиты не настроены.</p>}</div>}
  </div>;
}
