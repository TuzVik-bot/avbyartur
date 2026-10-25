"use client";

import { useState } from "react";
import { api, ApiClientError } from "@/lib/api";

type OrderButtonTariff = {
  id: string;
  name: string;
  amount: string;
  currency: string;
  duration_days: number;
};

export function BillingOrderButton({ tariff, listingId, companyId, ordersEnabled }: { tariff: OrderButtonTariff; listingId: string | null; companyId: string | null; ordersEnabled: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!ordersEnabled) {
    return <button className="button button-secondary button-small" type="button" disabled title="Подключение оплаты и коммерческие условия ещё не утверждены">Оформление закрыто</button>;
  }
  if (!listingId && !companyId) {
    return <button className="button button-secondary button-small" type="button" disabled title="Выберите объявление или компанию для продвижения">Выберите объект продвижения</button>;
  }

  async function order() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const idempotencyKey = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `billing-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const result = await api.createBillingOrder({
        tariff_id: tariff.id,
        listing_id: listingId,
        company_id: companyId,
      }, idempotencyKey);
      if (!result.checkout_url) throw new Error("missing_checkout_url");
      window.location.assign(result.checkout_url);
    } catch (issue) {
      setError(issue instanceof ApiClientError && issue.status === 409
        ? "Эта услуга уже активна или ожидает оплаты."
        : "Не удалось создать заказ. Повторите попытку позже.");
      setBusy(false);
    }
  }

  return <div className="billing-order-cell">
    <button className="button button-primary button-small" type="button" onClick={() => void order()} disabled={busy}>{busy ? "Создаём заказ…" : "Оформить"}</button>
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
