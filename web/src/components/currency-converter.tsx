"use client";

import { useMemo, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { convertCurrencyAmount } from "@/lib/format";
import type { components } from "@/lib/types.generated";

type CurrencyRates = components["schemas"]["CustomsRatesResponse"];

const currencyNames: Record<string, string> = {
  BYN: "Белорусский рубль",
  EUR: "Евро",
  USD: "Доллар США",
  RUB: "Российский рубль",
  CNY: "Китайский юань"
};

function formatConvertedAmount(value: string, currency: string) {
  const [whole, fraction] = value.split(".");
  return `${new Intl.NumberFormat("ru-BY").format(BigInt(whole))},${fraction} ${currency}`;
}

export function CurrencyConverter({ rates }: { rates: CurrencyRates }) {
  const [amount, setAmount] = useState("1");
  const [from, setFrom] = useState("BYN");
  const [to, setTo] = useState("USD");
  const converted = useMemo(
    () => convertCurrencyAmount(amount, from, to, rates.rates),
    [amount, from, to, rates.rates]
  );
  const sourceUrl = `https://api.nbrb.by/exrates/rates?${new URLSearchParams({ periodicity: "0", ondate: rates.rate_date })}`;
  const hasAmount = amount.trim().length > 0;

  return (
    <section className="currency-converter-form" aria-label="Конвертер валют">
      <div className="currency-converter-fields">
        <div className="currency-converter-side">
          <label className="field">
            <span>Сумма</span>
            <input
              name="amount"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              maxLength={28}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Из валюты</span>
            <select value={from} onChange={(event) => setFrom(event.target.value)}>
              {rates.rates.map((rate) => <option key={rate.currency} value={rate.currency}>{rate.currency} · {currencyNames[rate.currency] || rate.currency}</option>)}
            </select>
          </label>
        </div>
        <button
          className="icon-button currency-converter-swap"
          type="button"
          title="Поменять валюты местами"
          aria-label="Поменять валюты местами"
          onClick={() => {
            setFrom(to);
            setTo(from);
          }}
        >
          <ArrowLeftRight size={18} aria-hidden="true" />
        </button>
        <div className="currency-converter-side currency-converter-to">
          <label className="field">
            <span>В валюту</span>
            <select value={to} onChange={(event) => setTo(event.target.value)}>
              {rates.rates.map((rate) => <option key={rate.currency} value={rate.currency}>{rate.currency} · {currencyNames[rate.currency] || rate.currency}</option>)}
            </select>
          </label>
          {hasAmount && converted === null && <p className="inline-error" role="alert">Проверьте сумму и выбранные валюты.</p>}
          {converted !== null && <div className="currency-converter-result" aria-live="polite">
            <span>Результат</span>
            <output>{formatConvertedAmount(converted, to)}</output>
          </div>}
        </div>
      </div>
      <p className="currency-converter-source">Официальный курс НБРБ на {rates.rate_date}. Сумма ориентировочная. <a className="text-link" href={sourceUrl} target="_blank" rel="noreferrer">Источник курса</a></p>
    </section>
  );
}
