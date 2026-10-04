import type { Metadata } from "next";
import { AccountNav } from "@/components/account-nav";
import type { DealerAnalytics, DealerTeamMember } from "@/lib/dealer";
import { requireSession } from "@/lib/server";
import { serverApiRequest } from "@/lib/server-api";

export const metadata: Metadata = { title: "Аналитика компании" };

type SearchParams = { from?: string | string[]; to?: string | string[] };
const isoDate = (value: string | string[] | undefined) => {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate && /^\d{4}-\d{2}-\d{2}$/.test(candidate) ? candidate : undefined;
};

export default async function DealerAnalyticsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const session = await requireSession("/account/company/analytics");
  const params = await searchParams;
  const from = isoDate(params.from);
  const to = isoDate(params.to);
  let analytics: DealerAnalytics | null = null;
  let hasCompany = false;
  let failed = false;
  try {
    const team = await serverApiRequest<{ items: DealerTeamMember[] }>("dealer/team");
    hasCompany = team.items.some((member) => member.user_id === session.user.id && member.status === "active");
    if (hasCompany) {
      const query = new URLSearchParams();
      if (from) query.set("from", from);
      if (to) query.set("to", to);
      analytics = await serverApiRequest<DealerAnalytics>(`dealer/analytics${query.size ? `?${query}` : ""}`);
    }
  } catch { failed = true; }

  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Компания</p><h1>Аналитика объявлений</h1><p>Сводные данные по активности компании за выбранный период.</p></header>
    <AccountNav current="/account/company/analytics" />
    <form className="dealer-analytics-period" method="get" aria-label="Период аналитики">
      <label className="field"><span>С</span><input type="date" name="from" defaultValue={from} /></label>
      <label className="field"><span>По</span><input type="date" name="to" defaultValue={to} /></label>
      <button className="button button-secondary button-small" type="submit">Показать</button>
    </form>
    {failed ? <div className="notice" role="alert"><p>Не удалось загрузить аналитику компании.</p><a className="button button-secondary button-small" href="/account/company/analytics">Повторить загрузку</a></div>
      : !hasCompany ? <p className="notice" role="status">Для аккаунта не найдена активная связь с компанией.</p>
      : !analytics ? <p className="notice" role="alert">Аналитика пока недоступна. Попробуйте позже.</p>
      : <>
        <p className="muted">Период: {analytics.period.start || "—"} — {analytics.period.end || "—"}</p>
        <div className="dealer-analytics-totals" aria-label="Сводные показатели">
          <article><span>Объявлений</span><strong>{analytics.totals.listings}</strong></article>
          <article><span>Активных</span><strong>{analytics.totals.active_listings}</strong></article>
          <article><span>Показов телефона</span><strong>{analytics.totals.contact_reveals}</strong></article>
          <article><span>Диалогов</span><strong>{analytics.totals.chats}</strong></article>
          <article><span>Просмотров</span><strong>{analytics.totals.views}</strong></article>
        </div>
        <section className="section" aria-labelledby="dealer-analytics-listings"><div className="section-heading"><h2 id="dealer-analytics-listings">По объявлениям</h2></div>
          {!analytics.items.length ? <p className="muted" role="status">За этот период нет объявлений для отображения.</p> : <div className="info-table-wrap"><table className="info-table"><thead><tr><th>Объявление</th><th>Состояние</th><th>Показы телефона</th><th>Диалоги</th><th>Просмотры</th></tr></thead><tbody>{analytics.items.map((item) => <tr key={item.listing_id}><td>{item.title}</td><td>{item.status}</td><td>{item.contact_reveals}</td><td>{item.chats}</td><td>{item.views}</td></tr>)}</tbody></table></div>}
        </section>
      </>}
  </div>;
}
