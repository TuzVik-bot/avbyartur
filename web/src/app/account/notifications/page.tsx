import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { NotificationPreferences } from "@/components/notification-preferences";
import { NotificationsInbox } from "@/components/notifications-inbox";
import { requireSession } from "@/lib/server";
import { serverApi } from "@/lib/server-api";
import type { UserNotificationList } from "@/lib/types";

export const metadata: Metadata = { title: "Уведомления" };

export default async function NotificationsPage() {
  await requireSession("/account/notifications");
  const [notificationsResult, preferencesResult] = await Promise.allSettled([
    serverApi.notifications({ limit: 50 }), serverApi.notificationPreferences()
  ]);
  const data: UserNotificationList | null = notificationsResult.status === "fulfilled" ? notificationsResult.value : null;
  const preferences = preferencesResult.status === "fulfilled" ? preferencesResult.value.preferences : null;

  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Уведомления</h1><p>Следите за новыми объявлениями, которые подходят вашим сохранённым поискам.</p></header>
    <AccountNav current="/account/notifications" />
    <NotificationPreferences initialPreferences={preferences} />
    <NotificationsInbox initialItems={data?.items ?? []} initialUnreadCount={data?.unread_count ?? 0} initialLoadError={data === null} />
  </div>;
}
