import Link from "next/link";
import type { Metadata } from "next";
import { AdminNav } from "@/components/admin-nav";
import { adminServerApi } from "@/lib/admin-server";
import { requireSession } from "@/lib/server";

export const metadata: Metadata = { title: "Администрирование" };

const statusLabels: Record<string, string> = {
  active: "Активны", blocked: "Заблокированы", pending_review: "На проверке", draft: "Черновики",
  rejected: "Отклонены", paused: "На паузе", sold: "Проданы", archived: "В архиве",
  succeeded: "Завершены", queued: "В очереди", running: "Выполняются", failed: "С ошибкой"
};

function statusList(values: Record<string, number>) {
  const items = Object.entries(values);
  return items.length ? <ul className="admin-count-list">{items.map(([status, count]) => <li key={status}><span>{statusLabels[status] || status}</span><strong>{count}</strong></li>)}</ul> : <p className="muted">Нет данных по статусам.</p>;
}

export default async function AdminPage() {
  const session = await requireSession("/admin");
  if (session.user.role !== "admin") {
    return <div className="page-width"><header className="page-head"><p className="eyebrow">Администрирование</p><h1>Нет доступа</h1><p>Раздел доступен только администраторам.</p></header><Link className="button button-secondary" href="/account">В кабинет</Link></div>;
  }

  let summary: Awaited<ReturnType<typeof adminServerApi.operations>> | null = null;
  try { summary = await adminServerApi.operations(); } catch { /* Display a retryable state without exposing server details. */ }

  return (
    <div className="page-width">
      <header className="page-head"><p className="eyebrow">Закрытый пилот</p><h1>Администрирование</h1><p>Сводка системы, управление учётными записями и журнал действий.</p></header>
      <AdminNav current="/admin" />
      {!summary ? <p className="notice" role="alert">Не удалось загрузить сводку. Проверьте доступ к API и повторите попытку.</p> : <>
        <section className="admin-summary-grid" aria-label="Сводка по статусам">
          <article className="admin-summary-card"><h2>Пользователи</h2>{statusList(summary.users_by_status)}</article>
          <article className="admin-summary-card"><h2>Объявления</h2>{statusList(summary.listings_by_status)}</article>
          <article className="admin-summary-card"><h2>Фоновые задачи</h2>{statusList(summary.jobs_by_status)}</article>
        </section>
        <section className="section admin-capabilities">
          <div className="section-heading"><h2>Возможности регистрации</h2></div>
          <ul className="admin-count-list">
            <li><span>Вход по SMS</span><strong>{summary.capabilities.sms_login_enabled ? "Вкл." : "Выкл."}</strong></li>
            <li><span>Публичная регистрация</span><strong>{summary.capabilities.public_registration_enabled ? "Вкл." : "Выкл."}</strong></li>
          </ul>
        </section>
      </>}
    </div>
  );
}
