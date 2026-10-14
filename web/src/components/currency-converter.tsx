"use client";

import { useEffect, useMemo, useState } from "react";
import type { components } from "@/lib/types.generated";
import styles from "./currency-converter.module.css";

type CurrencyRates = components["schemas"]["CustomsRatesResponse"];
type RateHistory = components["schemas"]["CustomsRateHistoryResponse"];
type CurrencyCode = "BYN" | "USD" | "RUB" | "EUR";
type HistoryCurrency = RateHistory["currency"];
type HistoryPeriod = RateHistory["period"];

const currencies: { code: CurrencyCode; name: string }[] = [
  { code: "BYN", name: "Белорусский рубль" },
  { code: "USD", name: "Доллар США" },
  { code: "RUB", name: "Российский рубль" },
  { code: "EUR", name: "Евро" }
];

const historyCurrencies: { code: HistoryCurrency; label: string; amount: number }[] = [
  { code: "USD", label: "USD", amount: 1 },
  { code: "RUB", label: "100 RUB", amount: 100 },
  { code: "EUR", label: "EUR", amount: 1 }
];

const historyPeriods: { value: HistoryPeriod; label: string }[] = [
  { value: "30d", label: "1 месяц" },
  { value: "90d", label: "3 месяца" },
  { value: "180d", label: "6 месяцев" },
  { value: "365d", label: "1 год" }
];

function parseAmount(value: string): number | null {
  const normalized = value.trim().replace(/\s/g, "").replace(",", ".");
  if (!normalized || !/^\d{0,18}(?:\.\d{0,8})?$/.test(normalized)) return null;
  const amount = Number(normalized);
  return Number.isFinite(amount) && amount <= 1e18 ? amount : null;
}

function formatAmount(value: number, fractionDigits = 2) {
  return new Intl.NumberFormat("ru-BY", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    useGrouping: false
  }).format(value);
}

function formatRate(value: number) {
  return new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 4 }).format(value);
}

function formatDate(value: string, style: "long" | "short" = "long") {
  const parsed = new Date(`${value.slice(0, 10)}T12:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("ru-BY", style === "long"
      ? { day: "numeric", month: "long", year: "numeric" }
      : { day: "2-digit", month: "short" }
    ).format(parsed);
}

function ExchangeHistoryChart({ history, currencyLabel, amount }: { history: RateHistory; currencyLabel: string; amount: number }) {
  const points = history.points.map((point) => ({
    date: point.rate_date,
    value: Number(point.byn_per_unit) * amount
  })).filter((point) => Number.isFinite(point.value) && point.value > 0);
  if (!points.length) return null;

  const width = 960;
  const height = 300;
  const left = 76;
  const right = 18;
  const top = 18;
  const bottom = 40;
  const rawMin = Math.min(...points.map((point) => point.value));
  const rawMax = Math.max(...points.map((point) => point.value));
  const spread = rawMax - rawMin || rawMax * 0.02 || 0.02;
  const min = rawMin - spread * 0.1;
  const max = rawMax + spread * 0.1;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const position = (index: number, value: number) => ({
    x: left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth),
    y: top + ((max - value) / (max - min)) * plotHeight
  });
  const line = points.map((point, index) => {
    const { x, y } = position(index, point.value);
    return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const ticks = [0, 0.5, 1].map((ratio) => max - (max - min) * ratio);
  const markerStep = Math.max(1, Math.ceil(points.length / 36));
  const markerIndexes = points.map((_, index) => index)
    .filter((index) => index % markerStep === 0 || index === points.length - 1);
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <div className={styles.chartWrap}>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`История курса ${currencyLabel} по данным НБРБ с ${formatDate(first.date, "short")} по ${formatDate(last.date, "short")}`}
      >
        <title>Курс {currencyLabel} в белорусских рублях</title>
        {ticks.map((tick, index) => {
          const y = top + index * (plotHeight / 2);
          return <g key={index}>
            <line className={styles.gridLine} x1={left} x2={width - right} y1={y} y2={y} />
            <text className={styles.axisLabel} x={left - 10} y={y + 4} textAnchor="end">{formatRate(tick)}</text>
          </g>;
        })}
        <path className={styles.chartLine} d={line} />
        {markerIndexes.map((index) => {
          const { x, y } = position(index, points[index].value);
          return <circle className={styles.chartMarker} key={points[index].date} cx={x} cy={y} r="3.5">
            <title>{formatDate(points[index].date)}: {formatRate(points[index].value)} BYN</title>
          </circle>;
        })}
        <text className={styles.axisLabel} x={left} y={height - 8}>{formatDate(first.date, "short")}</text>
        <text className={styles.axisLabel} x={width - right} y={height - 8} textAnchor="end">{formatDate(last.date, "short")}</text>
      </svg>
    </div>
  );
}

export function CurrencyConverter({ rates, initialHistory }: { rates: CurrencyRates; initialHistory: RateHistory | null }) {
  const [baseCurrency, setBaseCurrency] = useState<CurrencyCode>("USD");
  const [amount, setAmount] = useState("1");
  const [historyCurrency, setHistoryCurrency] = useState<HistoryCurrency>("USD");
  const [period, setPeriod] = useState<HistoryPeriod>("90d");
  const [history, setHistory] = useState<RateHistory | null>(initialHistory);
  const [historyState, setHistoryState] = useState<"loading" | "ready" | "error">(initialHistory ? "ready" : "loading");
  const [retryVersion, setRetryVersion] = useState(0);
  const ratesByCurrency = useMemo(
    () => Object.fromEntries(rates.rates.map((rate) => [rate.currency, rate])) as Record<string, CurrencyRates["rates"][number]>,
    [rates.rates]
  );
  const parsedAmount = parseAmount(amount);
  const baseRate = Number(ratesByCurrency[baseCurrency]?.byn_per_unit);
  const amounts = useMemo(() => Object.fromEntries(currencies.map(({ code }) => {
    if (code === baseCurrency) return [code, amount];
    const targetRate = Number(ratesByCurrency[code]?.byn_per_unit);
    if (parsedAmount === null || !Number.isFinite(baseRate) || !Number.isFinite(targetRate) || targetRate <= 0) {
      return [code, ""];
    }
    return [code, formatAmount(parsedAmount * baseRate / targetRate)];
  })) as Record<CurrencyCode, string>, [amount, baseCurrency, baseRate, parsedAmount, ratesByCurrency]);

  useEffect(() => {
    if (initialHistory?.currency === historyCurrency && initialHistory.period === period) {
      setHistory(initialHistory);
      setHistoryState("ready");
      return;
    }

    const controller = new AbortController();
    const query = new URLSearchParams({ currency: historyCurrency, period }).toString();
    setHistory(null);
    setHistoryState("loading");
    fetch(`/api/v1/customs-calculator/rates/history?${query}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("History request failed");
        return await response.json() as RateHistory;
      })
      .then((result) => {
        if (result.currency !== historyCurrency || result.period !== period || !Array.isArray(result.points)) {
          throw new Error("History response did not match the request");
        }
        setHistory(result);
        setHistoryState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setHistoryState("error");
      });

    return () => controller.abort();
  }, [historyCurrency, initialHistory, period, retryVersion]);

  function focusCurrency(code: CurrencyCode) {
    if (code === baseCurrency) return;
    setBaseCurrency(code);
    setAmount(amounts[code] || "");
  }

  const activeHistoryCurrency = historyCurrencies.find((item) => item.code === historyCurrency)!;
  const historicalRates = history?.points.map((point) => Number(point.byn_per_unit) * activeHistoryCurrency.amount) ?? [];
  const change = historicalRates.length >= 2
    ? historicalRates.at(-1)! - historicalRates[0]
    : null;
  const percentChange = historicalRates.length >= 2
    ? (historicalRates.at(-1)! / historicalRates[0] - 1) * 100
    : null;

  return (
    <div className={styles.converterPage}>
      <section className={styles.rateSection} aria-labelledby="current-rates-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className="eyebrow">Официальные курсы</p>
            <h2 id="current-rates-title">НБРБ на {formatDate(rates.rate_date)}</h2>
          </div>
          <time className={styles.rateDate} dateTime={rates.rate_date}>{formatDate(rates.rate_date)}</time>
        </div>
        <div className={styles.currencyFields}>
          {currencies.map(({ code, name }) => {
            const rate = ratesByCurrency[code];
            const rateAmount = rate?.scale || 1;
            return <label className={styles.currencyField} htmlFor={`currency-${code}`} key={code}>
              <span className={styles.currencyLabel}><strong>{code}</strong><span>{name}</span></span>
              <input
                id={`currency-${code}`}
                name={code}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                maxLength={28}
                value={amounts[code]}
                onFocus={() => focusCurrency(code)}
                onChange={(event) => {
                  setBaseCurrency(code);
                  setAmount(event.target.value);
                }}
                aria-label={`Сумма в ${code}`}
              />
              <span className={styles.rateHint}>
                {rate ? `${rateAmount} ${code} = ${formatRate(Number(rate.official_rate))} BYN` : "Курс недоступен"}
              </span>
            </label>;
          })}
        </div>
        {amount.trim() && parsedAmount === null && <p className={styles.inputError} role="alert">Введите сумму числом, используя запятую или точку.</p>}
        <p className={styles.sourceNote}>
          Суммы пересчитываются по официальному курсу НБРБ. Банковские курсы покупки и продажи могут отличаться.
          {" "}<a href={`https://api.nbrb.by/exrates/rates?periodicity=0&ondate=${rates.rate_date}`} target="_blank" rel="noreferrer">Источник НБРБ</a>
        </p>
      </section>

      <section className={styles.historySection} aria-labelledby="rate-history-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className="eyebrow">Официальная динамика</p>
            <h2 id="rate-history-title">История курса валют</h2>
          </div>
          {change !== null && percentChange !== null && <p className={`${styles.changeSummary} ${change > 0 ? styles.increase : change < 0 ? styles.decrease : ""}`}>
            <span aria-hidden="true">{change > 0 ? "↑" : change < 0 ? "↓" : "→"}</span>
            {change > 0 ? "+" : ""}{formatRate(change)} BYN ({percentChange > 0 ? "+" : ""}{formatAmount(percentChange)}%) за период
          </p>}
        </div>

        <div className={styles.chartToolbar}>
          <div className={styles.currencyTabs} role="group" aria-label="Валюта для графика">
            {historyCurrencies.map((item) => <button
              className={`${styles.tab} ${historyCurrency === item.code ? styles.activeTab : ""}`}
              type="button"
              key={item.code}
              aria-pressed={historyCurrency === item.code}
              onClick={() => setHistoryCurrency(item.code)}
            >{item.label}</button>)}
          </div>
          <div className={styles.periodTabs} role="group" aria-label="Период графика">
            {historyPeriods.map((item) => <button
              className={`${styles.periodTab} ${period === item.value ? styles.activePeriod : ""}`}
              type="button"
              key={item.value}
              aria-pressed={period === item.value}
              onClick={() => setPeriod(item.value)}
            >{item.label}</button>)}
          </div>
        </div>

        <div className={styles.chartCard}>
          <div className={styles.chartTitle}>
            <h3>{activeHistoryCurrency.label} к белорусскому рублю</h3>
            <span>BYN за {activeHistoryCurrency.amount} {historyCurrency}</span>
          </div>
          {historyState === "loading" && <p className={styles.chartMessage} role="status">Загружаем историю курсов НБРБ…</p>}
          {historyState === "error" && <div className={styles.chartMessage} role="status">
            <p>Историю курса сейчас не удалось загрузить.</p>
            <button className="button button-secondary button-small" type="button" onClick={() => setRetryVersion((current) => current + 1)}>Повторить</button>
          </div>}
          {historyState === "ready" && history && history.points.length > 0 && <ExchangeHistoryChart history={history} currencyLabel={activeHistoryCurrency.label} amount={activeHistoryCurrency.amount} />}
          {historyState === "ready" && history && history.points.length === 0 && <p className={styles.chartMessage} role="status">За выбранный период НБРБ не опубликовал данные для графика.</p>}
          {history && historyState === "ready" && <p className={styles.historySource}>
            Данные за {formatDate(history.start_date, "short")} — {formatDate(history.end_date, "short")} · <a href={history.source_url} target="_blank" rel="noreferrer">Источник НБРБ</a>
          </p>}
        </div>
      </section>
    </div>
  );
}
