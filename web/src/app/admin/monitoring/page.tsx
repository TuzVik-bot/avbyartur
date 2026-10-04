import Link from "next/link";
import { AdminNav } from "@/components/admin-nav";
import { requireSession } from "@/lib/server";
import { serverApiRequest } from "@/lib/server-api";
import type { components } from "@/lib/types.generated";

export const metadata = { title: "Мониторинг · Администрирование" };

type MonitoringSnapshot = components["schemas"]["MonitoringSnapshotOut"];
type AlertCode = components["schemas"]["MonitoringAlertOut"]["code"];
type MetricValue = string | number | boolean | null;
type Metric = { label: string; value: MetricValue };

const alertMessages: Record<AlertCode, string> = {
  worker_failed_jobs: "Есть ошибки фоновых задач",
  worker_backlog: "Очередь задач ожидает обработки",
  worker_expired_leases: "Задачи потеряли исполнителя",
  notification_delivery_failed: "Не доставляются уведомления поиска",
  notification_backlog: "Накопилась очередь уведомлений",
  identity_delivery_failed: "Не доставляются письма подтверждения",
  sms_delivery_failed: "Есть ошибки доставки SMS",
  feed_import_failed: "Есть ошибки импорта дилерских объявлений",
  payment_failed: "Есть неуспешные попытки оплаты",
  payment_pending_aged: "Оплата слишком долго остаётся ожидающей",
  exchange_rate_unavailable: "Курс USD недоступен или устарел",
  runtime_monitor_unavailable: "Проверка сервера недоступна или устарела",
  docker_unhealthy: "Не все контейнеры работают штатно",
  backup_failed: "Последнее резервное копирование завершилось ошибкой",
  backup_stale: "Резервная копия отсутствует или устарела",
  backup_checksum_failed: "Контрольные суммы резервной копии не совпали",
};

const valueLabels: Record<string, string> = {
  action_required: "Требует внимания",
  current: "Актуален",
  failed: "Ошибка",
  never_run: "Ещё не запускался",
  ok: "В норме",
  other: "Другое",
  postgresql: "PostgreSQL",
  same_store: "Основная база данных",
  sqlite: "SQLite",
  stale: "Устарел",
  success: "Успешно",
  unavailable: "Недоступен",
  unconfigured: "Не настроен",
  unknown: "Неизвестно",
};

const severityLabels = { low: "Низкий", medium: "Средний", high: "Высокий" };

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} с`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) return remainingMinutes ? `${hours} ч ${remainingMinutes} мин` : `${hours} ч`;
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours ? `${days} д ${remainingHours} ч` : `${days} д`;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "Нет данных";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-BY", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Minsk",
  }).format(date);
}

function formatValue(value: MetricValue): string {
  if (value === null) return "Нет данных";
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (typeof value === "number") return value.toLocaleString("ru-BY");
  return valueLabels[value] ?? value;
}

function MetricCard({ title, metrics }: { title: string; metrics: Metric[] }) {
  return (
    <section className="admin-summary-card">
      <h2>{title}</h2>
      <ul className="admin-count-list">
        {metrics.map((metric) => (
          <li key={metric.label}>
            <span>{metric.label}</span>
            <strong>{formatValue(metric.value)}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function AdminMonitoringPage() {
  const session = await requireSession("/admin/monitoring");
  if (session.user.role !== "admin") {
    return (
      <div className="page-width">
        <header className="page-head"><h1>Нет доступа</h1></header>
        <Link href="/account">В кабинет</Link>
      </div>
    );
  }

  let snapshot: MonitoringSnapshot | null = null;
  try {
    snapshot = await serverApiRequest<MonitoringSnapshot>("admin/monitoring");
  } catch {
    snapshot = null;
  }

  return (
    <div className="page-width">
      <header className="page-head"><h1>Мониторинг</h1></header>
      <AdminNav current="/admin/monitoring" />
      {!snapshot ? (
        <p role="alert" className="notice">
          Не удалось получить состояние сервисов. <Link href="/admin/monitoring">Повторить</Link>
        </p>
      ) : (
        <>
          <div className="section-heading">
            <div>
              <span className={`status-pill ${snapshot.alerts.length ? "status-pending" : "status-active"}`}>
                {snapshot.alerts.length ? `Предупреждений: ${snapshot.alerts.length}` : "Активных предупреждений нет"}
              </span>
              <p>Сводка формируется при открытии страницы. Для свежих данных откройте её повторно.</p>
            </div>
            <Link href="/admin/monitoring">Обновить</Link>
          </div>

          {snapshot.alerts.length ? (
            <ul className="account-list" aria-label="Активные предупреждения">
              {snapshot.alerts.map((alert) => (
                <li className="account-list-item" key={alert.code}>
                  <div>
                    <h2>{alertMessages[alert.code]}</h2>
                    <p>
                      Приоритет: {severityLabels[alert.severity]}
                      {alert.count !== undefined && alert.count !== null ? ` · Количество: ${alert.count}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="notice" role="status">Активных предупреждений нет.</p>
          )}

          <div className="admin-summary-grid">
            <MetricCard title="Очередь задач" metrics={[
              { label: "Ошибки задач", value: snapshot.queue.failed },
              { label: "Ожидают обработки", value: snapshot.queue.overdue },
              { label: "Возраст старейшей", value: formatDuration(snapshot.queue.oldest_overdue_seconds) },
              { label: "Истёкшие аренды", value: snapshot.queue.expired_leases },
              { label: "Возраст аренды", value: formatDuration(snapshot.queue.oldest_expired_lease_seconds) },
            ]} />
            <MetricCard title="Уведомления" metrics={[
              { label: "Ошибки уведомлений поиска", value: snapshot.notifications.saved_search_failed },
              { label: "Не поддерживаются", value: snapshot.notifications.saved_search_unsupported },
              { label: "Очередь поиска старше 10 мин", value: snapshot.notifications.saved_search_queued_aged },
              { label: "Ошибки писем подтверждения", value: snapshot.notifications.identity_failed },
              { label: "Очередь писем старше 10 мин", value: snapshot.notifications.identity_queued_aged },
              { label: "Возраст старейшей ошибки", value: formatDuration(snapshot.notifications.oldest_failed_seconds) },
            ]} />
            <MetricCard title="SMS · последние 24 часа" metrics={[
              { label: "Отправлено", value: snapshot.sms.sent_24h },
              { label: "Ошибки доставки", value: snapshot.sms.delivery_failed_24h },
              { label: "Подавлено ограничениями", value: snapshot.sms.delivery_suppressed_24h },
            ]} />
            <MetricCard title="Импорт объявлений" metrics={[
              { label: "Ошибки за 24 часа", value: snapshot.imports.failed_24h },
            ]} />
            <MetricCard title="Платежи" metrics={[
              { label: "Неуспешные попытки", value: snapshot.payments.failed },
              { label: "Ожидают более 30 мин", value: snapshot.payments.pending_aged },
              { label: "Возраст старейшей", value: formatDuration(snapshot.payments.oldest_pending_seconds) },
            ]} />
            <MetricCard title="Курс USD" metrics={[
              { label: "Состояние", value: snapshot.exchange_rate.status },
              { label: "Возраст данных", value: snapshot.exchange_rate.age_seconds === null ? null : formatDuration(snapshot.exchange_rate.age_seconds) },
              { label: "Получен", value: formatTimestamp(snapshot.exchange_rate.fetched_at) },
            ]} />
            <MetricCard title="Отправка ошибок" metrics={[
              { label: "Sentry настроен", value: snapshot.error_delivery.configured },
              { label: "Попыток", value: snapshot.error_delivery.attempted },
              { label: "Принято SDK", value: snapshot.error_delivery.accepted },
              { label: "Ошибки отправки", value: snapshot.error_delivery.failed },
            ]} />
            <MetricCard title="Публичный каталог" metrics={[
              { label: "Активные объявления", value: snapshot.public_listing_index.active_public_listings },
              { label: "Хранилище", value: snapshot.public_listing_index.store },
              { label: "Внешний поисковый индекс", value: snapshot.public_listing_index.external_search },
              { label: "Сверка", value: snapshot.public_listing_index.parity },
            ]} />
            <MetricCard title="Сервер и резервные копии" metrics={[
              { label: "Состояние", value: snapshot.backup.status },
              { label: "Контейнеры здоровы", value: snapshot.backup.docker_healthy },
              { label: "Служба резервирования", value: snapshot.backup.backup_service_state },
              { label: "Контрольные суммы верны", value: snapshot.backup.backup_checksums_valid },
              { label: "Проверены", value: formatTimestamp(snapshot.backup.backup_checksums_checked_at) },
              { label: "Последнее успешное копирование", value: formatTimestamp(snapshot.backup.backup_last_success_at) },
              { label: "Снимок создан", value: formatTimestamp(snapshot.backup.snapshot_created_at) },
              { label: "Последняя проверка", value: formatTimestamp(snapshot.backup.checked_at) },
            ]} />
          </div>
        </>
      )}
    </div>
  );
}
