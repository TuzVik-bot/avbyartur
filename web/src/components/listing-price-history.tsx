"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ListingPriceHistoryItem } from "@/lib/types";
import styles from "./listing-price-history.module.css";

type HistoryState =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "error" }
  | { kind: "ready"; items: ListingPriceHistoryItem[] };

const eventLabels: Record<ListingPriceHistoryItem["event_type"], string> = {
  baseline: "Цена зафиксирована",
  published: "Цена при публикации",
  added: "Цена указана",
  changed: "Цена изменена",
  removed: "Цена снята"
};

function originalPrice(amount: string | null, currency: ListingPriceHistoryItem["currency"]) {
  if (amount === null || currency === null) return "Цена не указана";
  const numericAmount = Number(amount);
  const displayAmount = Number.isFinite(numericAmount)
    ? new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 2 }).format(numericAmount)
    : amount;
  return `${displayAmount} ${currency}`;
}

export function ListingPriceHistory({ listingId }: { listingId: string }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<HistoryState>({ kind: "loading" });

  useEffect(() => {
    let current = true;
    setState({ kind: "loading" });
    api.listingPriceHistory(listingId)
      .then(({ items }) => {
        if (current) setState(items.length ? { kind: "ready", items } : { kind: "empty" });
      })
      .catch(() => {
        if (current) setState({ kind: "error" });
      });
    return () => { current = false; };
  }, [attempt, listingId]);

  return <section className={styles.history} data-testid="listing-price-history" aria-labelledby="listing-price-history-title" aria-busy={state.kind === "loading"}>
    <div className={styles.heading}><h2 id="listing-price-history-title">История цены</h2></div>
    {state.kind === "loading" && <p className={styles.message} role="status">Загружаем историю цены…</p>}
    {state.kind === "empty" && <p className={styles.message} role="status">Изменений цены пока нет.</p>}
    {state.kind === "error" && <div className={styles.error}>
      <p role="alert">Не удалось загрузить историю цены.</p>
      <button className="button button-secondary button-small" type="button" onClick={() => setAttempt((value) => value + 1)}>Повторить</button>
    </div>}
    {state.kind === "ready" && <ol className={styles.entries}>
      {state.items.map((item) => <li className={styles.entry} key={item.id}>
        <div className={styles.entryLabel}>
          <strong>{eventLabels[item.event_type]}</strong>
          <time className={styles.date} dateTime={item.recorded_at}>{formatDate(item.recorded_at)}</time>
        </div>
        <p className={styles.amount}>
          {item.previous_amount !== null || item.previous_currency !== null
            ? <><span className="sr-only">Было: </span><span>{originalPrice(item.previous_amount, item.previous_currency)}</span><span aria-hidden="true"> → </span><span className="sr-only">Стало: </span></>
            : <span className="sr-only">Цена: </span>}
          <strong>{originalPrice(item.amount, item.currency)}</strong>
        </p>
      </li>)}
    </ol>}
  </section>;
}
