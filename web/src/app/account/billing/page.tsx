import type { Metadata } from "next";
import Link from "next/link";
import { AccountNav } from "@/components/account-nav";
import { requireSession } from "@/lib/server";
import { serverApi } from "@/lib/server-api";
import type { components } from "@/lib/types.generated";

export const metadata: Metadata = { title: "Тарифы и заказы" };
type SearchParams = { listing_id?: string | string[] };
type Tariff = components["schemas"]["BillingTariffOut"];
type Order = components["schemas"]["BillingOrderOut"];
const serviceLabels: Record<Tariff["service_code"], string> = { bump: "Поднять объявление", highlight: "Выделить объявление", top: "Размещение вверху", dealer_package: "Пакет для компании" };
const orderStatus: Record<Order["status"], string> = { pending: "Ожидает оплаты", paid: "Оплачен", failed: "Не удалось оплатить", cancelled: "Отменён", expired: "Истёк" };
function money(amount: string, currency: string) { return `${Number(amount).toLocaleString("ru-BY", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`; }

export default async function BillingPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireSession("/account/billing");
  const [params, tariffsResult, ordersResult] = await Promise.all([
    searchParams,
    serverApi.billingTariffs().then((items) => ({ items, error: false })).catch(() => ({ items: [] as Tariff[], error: true })),
    serverApi.billingOrders().then((value) => ({ value, error: false })).catch(() => ({ value: null, error: true }))
  ]);
  const rawListingId = Array.isArray(params.listing_id) ? params.listing_id[0] : params.listing_id;
  const listingId = rawListingId && /^[0-9a-f-]{36}$/i.test(rawListingId) ? rawListingId : null;
  return <div className="page-width">
    <header className="page-head"><p className="eyebrow">Личный кабинет</p><h1>Тарифы и продвижение</h1><p>Состав и стоимость услуг отображаются по активным тарифам, настроенным владельцем пилота.</p></header>
    <AccountNav current="/account/billing" />
    {listingId && <p className="muted">Продвижение для объявления <Link className="text-link" href="/account/listings">выбрано в списке объявлений</Link>; создание заказов сейчас недоступно.</p>}
    <section className="section" aria-labelledby="billing-tariffs-heading"><div className="section-heading"><h2 id="billing-tariffs-heading">Доступные тарифы</h2></div>
      {tariffsResult.error ? <p className="notice" role="alert">Не удалось загрузить тарифы. Повторите попытку позже.</p> : tariffsResult.items.length ? <div className="account-list">{tariffsResult.items.map((tariff) => <article className="account-list-item billing-tariff" key={tariff.id}>
        <div><h3>{tariff.name}</h3><p>{serviceLabels[tariff.service_code]} · {tariff.duration_days} дн.{tariff.listing_quota ? ` · до ${tariff.listing_quota} объявлений` : ""}</p><strong>{money(tariff.amount, tariff.currency)}</strong></div>
        <button className="button button-secondary button-small" type="button" disabled title="Подключение оплаты и коммерческие условия ещё не утверждены">Оформление закрыто</button>
      </article>)}</div> : <div className="empty-state"><h3>Активных тарифов нет</h3><p className="muted">Владелец пилота ещё не настроил и не утвердил стоимость услуг.</p></div>}
      <p className="notice" role="status">Создание заказа и оплата выключены до утверждения коммерческих условий и подключения рабочего платёжного сервиса.</p>
    </section>
    <section className="section" aria-labelledby="billing-orders-heading"><div className="section-heading"><h2 id="billing-orders-heading">История заказов</h2></div>
      {ordersResult.error ? <p className="notice" role="alert">Не удалось загрузить заказы.</p> : !ordersResult.value?.items.length ? <p className="muted">Заказов пока нет.</p> : <div className="account-list">{ordersResult.value.items.map((order) => <article className="account-list-item" key={order.id}><div><h3>{serviceLabels[order.service_code]}</h3><p>{money(order.amount, order.currency)} · {order.duration_days} дн. · {orderStatus[order.status]}</p><time className="muted" dateTime={order.created_at}>{new Date(order.created_at).toLocaleString("ru-RU")}</time></div><Link className="button button-secondary button-small" href={`/account/billing/${encodeURIComponent(order.id)}`}>Подробнее</Link></article>)}</div>}
    </section>
  </div>;
}
