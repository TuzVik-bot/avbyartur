"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ApiClientError } from "@/lib/api";
import { clearComparisonIds, removeComparisonId, useComparisonIds } from "@/lib/comparison-state";
import { fetchComparisonListings } from "@/lib/comparison-api";
import { listingHref } from "@/lib/format";
import type { Listing } from "@/lib/types";
import { buildComparisonRows, hasMixedPriceCurrencies, type ComparisonCell } from "./comparison-data";
import styles from "./comparison-view.module.css";

type ListingLoadState =
  | { kind: "loading" }
  | { kind: "loaded"; listing: Listing }
  | { kind: "unavailable"; message: string }
  | { kind: "error" };

function loadFailure(error: unknown): ListingLoadState {
  if (error instanceof ApiClientError && (error.status === 404 || error.status === 410)) {
    return { kind: "unavailable", message: "Объявление больше не доступно. Оно могло быть скрыто, удалено или снято с публикации." };
  }
  if (error instanceof ApiClientError && (error.status === 401 || error.status === 403)) {
    return { kind: "unavailable", message: "Нет публичного доступа к этому объявлению." };
  }
  return { kind: "error" };
}

function stateMessage(state: ListingLoadState) {
  if (state.kind === "loading") return "Загрузка актуальных данных…";
  if (state.kind === "unavailable") return state.message;
  if (state.kind === "error") return "Не удалось загрузить данные. Проверьте соединение и попробуйте снова.";
  if (state.listing.status === "sold") return "Продано";
  if (state.listing.status !== "active") return "Объявление не опубликовано";
  return "Активно";
}

function formatCell(cell: ComparisonCell, loadState: ListingLoadState) {
  if (loadState.kind === "loading") return <span className={styles.mutedCell}>Загружается…</span>;
  if (loadState.kind === "error") return <span className={styles.mutedCell}>Не загружено</span>;
  if (loadState.kind === "unavailable") return <span className={styles.mutedCell}>Недоступно</span>;
  if (!cell) return <span className={styles.missing}>Не указано</span>;
  return (
    <>
      <span>{cell.value}</span>
      {cell.note && <span className={styles.cellNote}>{cell.note}</span>}
    </>
  );
}

export function ComparisonView() {
  const selectedIds = useComparisonIds();
  const selectedKey = selectedIds.join("\u0000");
  const [loadStates, setLoadStates] = useState<Record<string, ListingLoadState>>({});
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let current = true;
    if (selectedIds.length === 0) {
      setLoadStates({});
      return () => { current = false; };
    }
    setLoadStates(Object.fromEntries(selectedIds.map((id) => [id, { kind: "loading" as const }])));
    fetchComparisonListings(selectedIds).then(({ items }) => {
      const byId = new Map(items.map((listing) => [listing.id, listing]));
      const entries = selectedIds.map((id) => {
        const listing = byId.get(id);
        if (listing && listing.status !== "active" && listing.status !== "sold") {
          return [id, { kind: "unavailable", message: "Объявление не опубликовано." } satisfies ListingLoadState] as const;
        }
        return listing
          ? [id, { kind: "loaded", listing } satisfies ListingLoadState] as const
          : [id, { kind: "unavailable", message: "Объявление больше не доступно. Оно могло быть скрыто, удалено или снято с публикации." } satisfies ListingLoadState] as const;
      });
      if (current) setLoadStates(Object.fromEntries(entries));
    }).catch((error: unknown) => {
      const state = loadFailure(error);
      if (current) setLoadStates(Object.fromEntries(selectedIds.map((id) => [id, state])));
    });
    return () => { current = false; };
  }, [selectedKey, retryCount]);

  const listings = useMemo(() => selectedIds.map((id) => {
    const state = loadStates[id];
    return state?.kind === "loaded" ? state.listing : null;
  }), [loadStates, selectedKey]);
  const rows = useMemo(() => buildComparisonRows(listings), [listings]);
  const mixedCurrencies = hasMixedPriceCurrencies(listings);

  if (selectedIds.length === 0) {
    return (
      <section className={`page-width ${styles.page}`} aria-labelledby="comparison-heading">
        <div className={styles.heading}>
          <div><p className="eyebrow">Выбор автомобиля</p><h1 id="comparison-heading">Сравнение автомобилей</h1></div>
        </div>
        <div className={styles.emptyState}>
          <h2>Пока нет объявлений для сравнения</h2>
          <p>Добавьте до четырёх автомобилей на карточках объявлений, чтобы сопоставить характеристики.</p>
          <Link className="button button-primary" href="/cars">Перейти в каталог</Link>
        </div>
      </section>
    );
  }

  return (
    <section className={`page-width ${styles.page}`} aria-labelledby="comparison-heading">
      <div className={styles.heading}>
        <div>
          <p className="eyebrow">Выбрано {selectedIds.length} из 4</p>
          <h1 id="comparison-heading">Сравнение автомобилей</h1>
          <p className={styles.intro}>Добавьте ещё автомобили из каталога или удалите выбранные из списка.</p>
        </div>
        <div className={styles.headingActions}>
          <Link className="button button-secondary" href="/cars">К каталогу</Link>
          <button className="button button-secondary" type="button" onClick={clearComparisonIds}>Очистить список</button>
        </div>
      </div>

      <p className={styles.disclaimer}>
        Сравнение основано на данных публичных объявлений и сведениях продавца. Оно не подтверждает техническое состояние, историю или юридическую чистоту автомобиля.
      </p>
      <p className={styles.legend}>
        Различающиеся характеристики выделены. Цены показаны в валюте каждого объявления; доступный эквивалент BYN указан отдельно с датой курса.
      </p>
      {mixedCurrencies && <p className={styles.currencyNote} role="status">Валюта цены отличается: суммы не выделяются как напрямую сопоставимые.</p>}
      <p className={styles.scrollHint}>На узком экране прокручивайте таблицу по горизонтали.</p>

      <div className={styles.tableScroll} role="region" aria-label="Таблица сравнения автомобилей" tabIndex={0}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.fieldHeader} scope="col">Характеристика</th>
              {selectedIds.map((id) => {
                const state = loadStates[id] || { kind: "loading" as const };
                const listing = state.kind === "loaded" ? state.listing : null;
                return (
                  <th className={styles.vehicleHeader} scope="col" key={id}>
                    <div className={styles.vehicleHeading}>
                      <strong>{listing?.title || (state.kind === "loaded" ? "Объявление" : "Автомобиль")}</strong>
                      <span className={`${styles.status} ${state.kind === "loaded" && state.listing.status === "sold" ? styles.sold : ""}`} role="status">{stateMessage(state)}</span>
                      {listing && <Link className={styles.openLink} href={listingHref(listing)}>Открыть объявление</Link>}
                      {state.kind === "error" && <button className={styles.retry} type="button" onClick={() => setRetryCount((value) => value + 1)}>Загрузить снова</button>}
                      <button className={styles.remove} type="button" aria-label={`Удалить ${listing?.title || "автомобиль"} из сравнения`} onClick={() => removeComparisonId(id)}>Удалить</button>
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} data-comparison-row={row.key} data-differences={row.isDifferent} className={row.isDifferent ? styles.differentRow : undefined}>
                <th className={styles.fieldName} scope="row">{row.label}</th>
                {selectedIds.map((id, index) => {
                  const state = loadStates[id] || { kind: "loading" as const };
                  const cell = row.cells[index];
                  const classes = [styles.valueCell];
                  if (row.isDifferent && cell && state.kind === "loaded") classes.push(styles.differentCell);
                  if (!cell && state.kind === "loaded") classes.push(styles.missingCell);
                  return <td className={classes.join(" ")} key={id}>{formatCell(cell, state)}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
