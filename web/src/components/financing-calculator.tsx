"use client";

import { useState } from "react";
import { calculateFinancing, type FinancingEstimate, type FinancingMode } from "@/lib/financing-calculator";

const currencies = ["BYN", "USD", "EUR"] as const;
type Currency = typeof currencies[number];

export function FinancingCalculator({
  initialPrice = "",
  initialCurrency = "BYN",
  initialMode = "credit"
}: {
  initialPrice?: string;
  initialCurrency?: Currency;
  initialMode?: FinancingMode;
}) {
  const [mode, setMode] = useState<FinancingMode>(initialMode);
  const [price, setPrice] = useState(initialPrice);
  const [currency, setCurrency] = useState<Currency>(initialCurrency);
  const [downPayment, setDownPayment] = useState("");
  const [months, setMonths] = useState("");
  const [rate, setRate] = useState("");
  const [residual, setResidual] = useState("0");
  const [fees, setFees] = useState("0");
  const [estimate, setEstimate] = useState<FinancingEstimate | null>(null);
  const [error, setError] = useState("");

  function recalculate() {
    setError("");
    setEstimate(null);
    if (!price.trim() || !downPayment.trim() || !months.trim() || !rate.trim()) {
      setError("Заполните стоимость, аванс, срок и ставку.");
      return;
    }
    try {
      setEstimate(calculateFinancing({
        mode,
        price: Number(price),
        downPayment: Number(downPayment),
        months: Number(months),
        annualRatePercent: Number(rate),
        residualPayment: mode === "leasing" ? Number(residual || 0) : 0,
        feesTotal: Number(fees || 0)
      }));
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : "Проверьте введённые параметры.");
    }
  }

  const money = (amount: number) => new Intl.NumberFormat("ru-BY", {
    style: "currency", currency, maximumFractionDigits: 2
  }).format(amount);

  return (
    <main className="page-width financing-page">
      <p className="eyebrow">Сервисы</p>
      <h1>Подбор кредита или лизинга</h1>
  <p className="muted financing-lead">Рассчитайте примерный платёж по условиям, которые введёте сами. Ставки банков не подставляются, заявка не создаётся. Данные формы никуда не отправляются.</p>

      <section className="financing-form section" aria-label="Расчёт кредита или лизинга">
        <div className="form-grid">
          <label className="field"><span>Способ финансирования</span><select value={mode} onChange={(event) => { setMode(event.target.value as FinancingMode); setEstimate(null); }}>
            <option value="credit">Кредит</option>
            <option value="leasing">Лизинг</option>
          </select></label>
          <label className="field"><span>Валюта</span><select value={currency} onChange={(event) => { setCurrency(event.target.value as Currency); setEstimate(null); }}>
            {currencies.map((item) => <option key={item} value={item}>{item}</option>)}
          </select></label>
          <label className="field"><span>Стоимость транспорта</span><input inputMode="decimal" type="number" min="0.01" step="0.01" required value={price} onChange={(event) => { setPrice(event.target.value); setEstimate(null); }} /></label>
          <label className="field"><span>Аванс</span><input inputMode="decimal" type="number" min="0" step="0.01" required value={downPayment} onChange={(event) => { setDownPayment(event.target.value); setEstimate(null); }} /></label>
          <label className="field"><span>Срок, месяцев</span><input inputMode="numeric" type="number" min="1" max="360" step="1" required value={months} onChange={(event) => { setMonths(event.target.value); setEstimate(null); }} /></label>
          <label className="field"><span>Ставка в год, %</span><input inputMode="decimal" type="number" min="0" max="1000" step="0.01" required value={rate} onChange={(event) => { setRate(event.target.value); setEstimate(null); }} /></label>
          {mode === "leasing" && <label className="field"><span>Выкупной платёж <small className="muted">если предусмотрен</small></span><input inputMode="decimal" type="number" min="0" step="0.01" value={residual} onChange={(event) => { setResidual(event.target.value); setEstimate(null); }} /></label>}
          <label className="field"><span>Известные комиссии за весь срок <small className="muted">распределяются по платежам равномерно</small></span><input inputMode="decimal" type="number" min="0" step="0.01" value={fees} onChange={(event) => { setFees(event.target.value); setEstimate(null); }} /></label>
        </div>
        <div className="form-actions"><span className="muted">Все суммы рассчитываются в выбранной валюте, без конвертации.</span><button className="button button-primary" type="button" onClick={recalculate}>Рассчитать платёж</button></div>
        <p className="muted">Расчёт делит введённую годовую ставку на 12 и использует аннуитетную схему. Известные комиссии распределяются поровну по месяцам. Платёж округляется до копеек. Последний платёж корректируется так, чтобы сохранить общую сумму расчёта; при малой сумме регулярный платёж уменьшается, чтобы последний не стал отрицательным. В кредитных и лизинговых договорах могут применяться другие правила.</p>
        {error && <p className="inline-error" role="alert">{error}</p>}
        {estimate && <section className="financing-result" aria-live="polite" aria-label="Результат расчёта">
          <h2>Предварительный расчёт</h2>
          <dl>
            <div><dt>{Number(months) === 1 ? "Единственный платёж" : `Платёж в первые ${Number(months) - 1} мес.`}</dt><dd>{money(estimate.monthlyPayment)}</dd></div>
            {Number(months) > 1 && <div><dt>Последний платёж без выкупного</dt><dd>{money(estimate.lastMonthlyPayment)}</dd></div>}
            {mode === "leasing" && Number(residual) > 0 && <div><dt>Выкупной платёж в конце срока</dt><dd>{money(Number(residual))}</dd></div>}
            <div><dt>Всего с авансом, платежами и выкупом</dt><dd>{money(estimate.totalCost)}</dd></div>
            <div><dt>Сверх цены транспорта</dt><dd>{money(estimate.interestAndFees)}</dd></div>
          </dl>
          <p className="muted">Это расчёт по введённым параметрам, а не предложение или одобрение банка/лизинговой организации. Фактические условия и дополнительные платежи уточняйте у организации.</p>
        </section>}
      </section>

      <p className="notice financing-unavailable">Подбор предложения через партнёров пока не подключён. Не передавайте через эту страницу контактные или банковские данные.</p>
    </main>
  );
}
