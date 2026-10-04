import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { AccountSessions, type AccountSessionList } from "@/components/account-sessions";
import { AccountIdentityControls } from "@/components/account-identity-controls";
import type { ConsentHistoryItem, UserProfile } from "@/lib/api";
import { requireSession } from "@/lib/server";
import { serverApiRequest } from "@/lib/server-api";

export const metadata: Metadata = { title: "Безопасность и сеансы" };

export default async function AccountSettingsPage() {
  await requireSession("/account/settings");
  const [sessionsResult, profileResult, consentsResult] = await Promise.allSettled([
    serverApiRequest<AccountSessionList>("me/sessions"),
    serverApiRequest<{ profile: UserProfile }>("me/profile"),
    serverApiRequest<{ items: ConsentHistoryItem[] }>("me/consents")
  ]);
  const sessions = sessionsResult.status === "fulfilled" ? sessionsResult.value : null;
  const profile = profileResult.status === "fulfilled" ? profileResult.value.profile : null;
  const consents = consentsResult.status === "fulfilled" ? consentsResult.value.items : null;

  return (
    <div className="page-width">
      <header className="page-head">
        <p className="eyebrow">Личный кабинет</p>
        <h1>Безопасность аккаунта</h1>
        <p>Управляйте профилем и контактами, просматривайте историю согласий и завершайте ненужные сеансы.</p>
      </header>
      <AccountNav current="/account/settings" />
      <AccountIdentityControls initialProfile={profile} initialConsents={consents} />
      <AccountSessions initialSessions={sessions?.items ?? null} />
    </div>
  );
}
