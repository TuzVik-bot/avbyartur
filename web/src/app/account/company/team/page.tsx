import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { DealerTeam } from "@/components/dealer-team";
import type { DealerTeamMember } from "@/lib/dealer";
import { requireSession } from "@/lib/server";
import { serverApiRequest } from "@/lib/server-api";

export const metadata: Metadata = { title: "Команда компании" };

export default async function DealerTeamPage() {
  const session = await requireSession("/account/company/team");
  let members: DealerTeamMember[] | null = null;
  try {
    const result = await serverApiRequest<{ items: DealerTeamMember[] }>("dealer/team");
    members = result.items;
  } catch { /* The page renders a retry state instead of hiding the failure. */ }

  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Компания</p><h1>Команда компании</h1><p>Управляйте доступом сотрудников к работе с объявлениями компании.</p></header>
    <AccountNav current="/account/company/team" />
    <DealerTeam initialMembers={members} currentUserId={session.user.id} />
  </div>;
}
