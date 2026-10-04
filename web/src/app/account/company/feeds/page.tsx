import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import { DealerFeeds } from "@/components/dealer-feeds";
import type { DealerFeed, DealerTeamMember } from "@/lib/dealer";
import { requireSession } from "@/lib/server";
import { serverApiRequest } from "@/lib/server-api";

export const metadata: Metadata = { title: "Интеграции компании" };

const TEAM_ROLES = new Set(["owner", "admin", "seller", "viewer"]);

export default async function DealerFeedsPage() {
  const session = await requireSession("/account/company/feeds");
  let team: DealerTeamMember[] = [];
  let feeds: DealerFeed[] | null = null;
  try {
    team = (await serverApiRequest<{ items: DealerTeamMember[] }>("dealer/team")).items;
    const actor = team.find((member) => member.user_id === session.user.id && member.status === "active");
    if (actor && TEAM_ROLES.has(actor.role)) {
      feeds = (await serverApiRequest<{ items: DealerFeed[] }>("dealer/feeds")).items;
    } else {
      feeds = [];
    }
  } catch { /* Render an actionable retry state when the team or feeds API is unavailable. */ }

  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Компания</p><h1>Интеграции и импорт</h1><p>Настраивайте источники данных, проверяйте строки перед применением и просматривайте ошибки загрузки.</p></header>
    <AccountNav current="/account/company/feeds" />
    <DealerFeeds initialFeeds={feeds} initialTeam={team} currentUserId={session.user.id} />
  </div>;
}
