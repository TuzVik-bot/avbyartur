import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AccountNav } from "@/components/account-nav";
import { ApiClientError } from "@/lib/api";
import { requireSession } from "@/lib/server";
import { serverApi } from "@/lib/server-api";
import type { components } from "@/lib/types.generated";

export const metadata: Metadata = { title: "Заказ" };
type Order = components["schemas"]["BillingOrderOut"];
const serviceLabels: Record<Order["service_code"], string> = { bump: "Поднять объявление", highlight: "Выделить объявление", top: "Размещение вверху", dealer_package: "Пакет для компании" };
const statusLabels: Record<Order["status"], string> = { pending: "Ожидает оплаты", paid: "Оплачен", failed: "Не удалось оплатить", cancelled: "Отменён", expired: "Истёк" };

export default async function BillingOrderPage({ params }: { params: Promise<{ orderId: string }> }) {
  await requireSession("/account/billing");
  const { orderId } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(orderId)) notFound();
  let order: Order;
  try { order = await serverApi.billingOrder(orderId); }
  catch (issue) {
    if (issue instanceof ApiClientError && issue.status === 404) notFound();
    return <div className="page-width"><p className="notice" role="alert">Не удалось загрузить заказ. Повторите попытку позже.</p><Link href="/account/billing">К тарифам и заказам</Link></div>;
  }
  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>{serviceLabels[order.service_code]}</h1></header>
    <AccountNav current="/account/billing" />
    <dl className="listing-specs"><div><dt>Тариф</dt><dd>{order.tariff_code} · ревизия {order.tariff_revision}</dd></div><div><dt>Сумма</dt><dd>{Number(order.amount).toLocaleString("ru-BY", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {order.currency}</dd></div><div><dt>Срок услуги</dt><dd>{order.duration_days} дней</dd></div><div><dt>Статус</dt><dd>{statusLabels[order.status]}</dd></div><div><dt>Создан</dt><dd>{new Date(order.created_at).toLocaleString("ru-RU")}</dd></div><div><dt>Действителен до</dt><dd>{new Date(order.expires_at).toLocaleString("ru-RU")}</dd></div></dl>
    <p className="notice" role="status">Данные заказа показываются из неизменяемого снимка тарифа. Обработка оплаты зависит от подключённого платёжного сервиса.</p>
    <Link className="button button-secondary" href="/account/billing">К тарифам и заказам</Link>
  </div>;
}
