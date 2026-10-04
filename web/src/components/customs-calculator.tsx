"use client";

import { useEffect, useRef, useState } from "react";
import { ApiClientError } from "@/lib/api";
import {
  calculateCustoms,
  getCustomsCalculatorMeta,
  type CustomsCalculationRequest,
  type CustomsCalculationResult,
  type CustomsCalculatorMeta
} from "@/lib/customs-calculator";
import styles from "./customs-calculator.module.css";

type RequestIssue = { summary: string; fields: Record<string, string> };

const fieldLabels: Record<string, string> = {
  price_amount: "сумму цены",
  currency: "валюту цены",
  manufacture_date: "дату выпуска",
  engine_type: "тип двигателя",
  engine_volume_cc: "объём двигателя",
  personal_use: "подтверждение личного пользования",
  origin_outside_eaeu: "подтверждение ввоза вне ЕАЭС",
  request: "введённые данные"
};

const ageBandLabels: Record<CustomsCalculationResult["age_band"], string> = {
  up_to_3_years: "До 3 лет включительно",
  over_3_to_5_years: "Свыше 3 до 5 лет включительно",
  over_5_years: "Свыше 5 лет"
};

function unavailableMessage(reason: string | null | undefined): string {
  switch (reason) {
    case "customs_rules_unverified":
      return "Публичный расчёт недоступен: контрольные примеры ещё не подтверждены по данным ГТК.";
    case "customs_rates_unavailable":
      return "Официальные курсы НБРБ за сегодняшнюю дату временно недоступны. Попробуйте позже.";
    case "customs_rules_unavailable":
    default:
      return "Для сегодняшней даты нет доступной подтверждённой версии таможенных правил.";
  }
}

function fieldIssueText(field: string): string | null {
  switch (field) {
    case "price_amount": return "Введите положительную цену цифрами и десятичной точкой.";
    case "currency": return "Выберите валюту цены.";
    case "manufacture_date": return "Введите точную дату выпуска автомобиля.";
    case "engine_type": return "Выберите бензиновый или дизельный двигатель.";
    case "engine_volume_cc": return "Введите целый объём двигателя от 1 до 100 000 см³.";
    case "personal_use": return "Подтвердите личное пользование автомобилем.";
    case "origin_outside_eaeu": return "Подтвердите ввоз автомобиля из-за пределов ЕАЭС.";
    case "request": return "Проверьте все введённые данные.";
    default: return null;
  }
}

function issueFor(error: unknown): RequestIssue {
  if (!(error instanceof ApiClientError)) {
    return { summary: "Не удалось связаться с сервисом. Проверьте соединение и повторите расчёт.", fields: {} };
  }

  let summary: string;
  switch (error.code) {
    case "customs_rules_unverified":
      summary = "Публичный расчёт временно недоступен: контрольные примеры ещё не подтверждены по данным ГТК.";
      break;
    case "customs_rates_unavailable":
      summary = "Официальные курсы НБРБ за дату расчёта временно недоступны. Повторите попытку позже.";
      break;
    case "customs_rules_unavailable":
      summary = "Для даты расчёта нет подтверждённой версии таможенных правил. Суммы не показаны.";
      break;
    case "customs_input_invalid":
    case "validation_error":
      summary = "Проверьте введённые данные и повторите расчёт.";
      break;
    case "api_unavailable":
    case "api_invalid_response":
      summary = "Сервис временно недоступен. Проверьте соединение и повторите попытку.";
      break;
    default:
      summary = error.status >= 500
        ? "Расчёт временно недоступен. Повторите попытку позже."
        : "Проверьте введённые данные и повторите расчёт.";
  }

  const fields = Object.fromEntries(
    Object.keys(error.fieldErrors).flatMap((field) => {
      const message = fieldIssueText(field);
      return message ? [[field, message]] : [];
    })
  );
  const knownFieldNames = Object.keys(error.fieldErrors).filter((field) => fieldLabels[field]);
  if ((error.code === "customs_input_invalid" || error.code === "validation_error") && knownFieldNames.length) {
    const readableFields = [...new Set(knownFieldNames.map((field) => fieldLabels[field]))];
    summary = `Проверьте ${readableFields.join(", ")}.`;
  }
  return { summary, fields };
}

function sourceLabel(value: string): string {
  try {
    const host = new URL(value).hostname.toLowerCase();
    if (host === "api.nbrb.by" || host.endsWith(".nbrb.by")) return "Национальный банк Республики Беларусь — курсы валют";
    if (host === "customs.gov.by" || host.endsWith(".customs.gov.by")) return "Государственный таможенный комитет Республики Беларусь";
    if (host === "pravo.by" || host.endsWith(".pravo.by") || host === "etalonline.by" || host.endsWith(".etalonline.by")) return "Официальный правовой портал Республики Беларусь";
    if (host === "eaeunion.org" || host.endsWith(".eaeunion.org")) return "Евразийская экономическая комиссия";
    return host;
  } catch {
    return "Источник";
  }
}

function SourceLinks({ sources, label }: { sources: string[]; label: string }) {
  if (sources.length === 0) return null;
  return (
    <section className={styles.sources} aria-label={label}>
      <h3>{label}</h3>
      <ul>
        {sources.map((source) => (
          <li key={source}>
            <a href={source} target="_blank" rel="noopener noreferrer">{sourceLabel(source)}<span className={styles.visuallyHidden}> — открыть источник в новой вкладке</span></a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function isPositivePrice(value: string): boolean {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return false;
  try {
    const whole = BigInt(match[1]);
    const fractionIsPositive = (match[2] || "").includes("1") || (match[2] || "").includes("2") ||
      (match[2] || "").includes("3") || (match[2] || "").includes("4") || (match[2] || "").includes("5") ||
      (match[2] || "").includes("6") || (match[2] || "").includes("7") || (match[2] || "").includes("8") ||
      (match[2] || "").includes("9");
    return (whole > 0 || fractionIsPositive) && whole <= BigInt("1000000000000000000");
  } catch {
    return false;
  }
}

function getFieldHelpId(field: string): string {
  return `customs-${field}-help`;
}

export function CustomsCalculator() {
  const [meta, setMeta] = useState<CustomsCalculatorMeta | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);
  const [metaError, setMetaError] = useState(false);
  const [metaRetry, setMetaRetry] = useState(0);
  const [result, setResult] = useState<CustomsCalculationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<RequestIssue | null>(null);
  const [price, setPrice] = useState("");
  const formRef = useRef<HTMLFormElement | null>(null);
  const requestVersion = useRef(0);
  const busyRef = useRef(false);

  useEffect(() => {
    let active = true;
    setMetaLoading(true);
    setMetaError(false);
    void getCustomsCalculatorMeta().then((value) => {
      if (active) setMeta(value);
    }).catch(() => {
      if (active) setMetaError(true);
    }).finally(() => {
      if (active) setMetaLoading(false);
    });
    return () => { active = false; };
  }, [metaRetry]);

  function invalidatePreviousRequest() {
    requestVersion.current += 1;
    busyRef.current = false;
    setBusy(false);
    setResult(null);
    setIssue(null);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busyRef.current || !meta?.calculation_available) return;
    const form = event.currentTarget;
    if (!form.reportValidity()) return;

    const data = new FormData(form);
    const rawPrice = String(data.get("price_amount") || "").trim();
    if (!isPositivePrice(rawPrice)) {
      const priceInput = form.elements.namedItem("price_amount");
      if (priceInput instanceof HTMLInputElement) {
        priceInput.setCustomValidity("Введите положительную цену не выше 1 000 000 000 000 000 000.");
        priceInput.reportValidity();
      }
      return;
    }

    const manufactureDate = String(data.get("manufacture_date") || "");
    const engineVolume = Number(String(data.get("engine_volume_cc") || ""));
    if (!Number.isSafeInteger(engineVolume) || engineVolume < 1 || engineVolume > 100_000) return;
    if (data.get("personal_use") !== "yes" || data.get("origin_outside_eaeu") !== "yes") return;

    const payload: CustomsCalculationRequest = {
      price_amount: rawPrice,
      currency: String(data.get("currency")) as CustomsCalculationRequest["currency"],
      manufacture_date: manufactureDate,
      engine_type: String(data.get("engine_type")) as CustomsCalculationRequest["engine_type"],
      engine_volume_cc: engineVolume,
      personal_use: true,
      origin_outside_eaeu: true
    };
    const version = ++requestVersion.current;
    busyRef.current = true;
    setBusy(true);
    setIssue(null);
    setResult(null);

    try {
      const value = await calculateCustoms(payload);
      if (requestVersion.current === version) setResult(value);
    } catch (error) {
      if (requestVersion.current === version) setIssue(issueFor(error));
    } finally {
      if (requestVersion.current === version) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }

  const showUnavailable = meta && !meta.calculation_available;

  return (
    <div className={`page-width ${styles.page}`}>
      <header className="page-head">
        <p className="eyebrow">Справка и расчёт</p>
        <h1>Таможенный калькулятор</h1>
        <p>Предварительная оценка таможенных платежей при ввозе автомобиля в Беларусь.</p>
      </header>

      <div className={styles.layout}>
        <section className={`form-section ${styles.formPanel}`} aria-labelledby="customs-form-title">
          <div className="company-form-heading">
            <div>
              <h2 id="customs-form-title">Данные автомобиля</h2>
              <p className="muted">Заполните точные сведения из документов на автомобиль.</p>
            </div>
          </div>

          {metaLoading && <p className={styles.status} role="status" aria-live="polite">Загружаем сведения о доступности расчёта…</p>}
          {metaError && <div className={`notice ${styles.errorPanel}`} role="alert">
            <p>Не удалось загрузить сведения о правилах. Расчёт пока недоступен.</p>
            <button className="button button-secondary" type="button" onClick={() => setMetaRetry((attempt) => attempt + 1)}>Повторить загрузку</button>
          </div>}
          {showUnavailable && <div className={`notice ${styles.unavailable}`} role="status" aria-live="polite">
            <p>{unavailableMessage(meta.unavailable_reason)}</p>
            {meta.rules_version && <p>Версия правил: <strong>{meta.rules_version}</strong>{meta.verified_on ? ` · сверена ${meta.verified_on}` : ""}</p>}
            <SourceLinks sources={meta.sources} label="Источники правил и проверки" />
          </div>}

          <form ref={formRef} className={styles.form} onSubmit={submit} aria-busy={busy}>
            <div className={styles.fields}>
              <div className="field">
                <label htmlFor="customs-price-amount">Цена покупки автомобиля *</label>
                <input
                  id="customs-price-amount"
                  name="price_amount"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  required
                  maxLength={40}
                  pattern="[0-9]+([.][0-9]+)?"
                  value={price}
                  onChange={(event) => {
                    event.currentTarget.setCustomValidity(isPositivePrice(event.currentTarget.value.trim()) || !event.currentTarget.value ? "" : "Введите положительную цену цифрами и десятичной точкой.");
                    setPrice(event.currentTarget.value);
                    invalidatePreviousRequest();
                  }}
                  aria-describedby={`${getFieldHelpId("price_amount")} ${issue?.fields.price_amount ? "customs-price-amount-error" : ""}`.trim()}
                  aria-invalid={issue?.fields.price_amount ? true : undefined}
                />
                <span className={styles.help} id={getFieldHelpId("price_amount")}>Сумма и десятичная часть через точку; максимум — 1 000 000 000 000 000 000.</span>
                {issue?.fields.price_amount && <span className={styles.fieldError} id="customs-price-amount-error">{issue.fields.price_amount}</span>}
              </div>

              <div className="field">
                <label htmlFor="customs-currency">Валюта цены *</label>
                <select id="customs-currency" name="currency" defaultValue="" required onChange={invalidatePreviousRequest} aria-describedby={issue?.fields.currency ? "customs-currency-error" : undefined} aria-invalid={issue?.fields.currency ? true : undefined}>
                  <option value="">Выберите валюту</option>
                  <option value="EUR">EUR — евро</option>
                  <option value="USD">USD — доллар США</option>
                  <option value="BYN">BYN — белорусский рубль</option>
                  <option value="RUB">RUB — российский рубль</option>
                  <option value="CNY">CNY — китайский юань</option>
                </select>
                {issue?.fields.currency && <span className={styles.fieldError} id="customs-currency-error">{issue.fields.currency}</span>}
              </div>

              <div className="field">
                <label htmlFor="customs-manufacture-date">Точная дата выпуска *</label>
                <input id="customs-manufacture-date" name="manufacture_date" type="date" required onChange={invalidatePreviousRequest} aria-describedby={`${getFieldHelpId("manufacture_date")} ${issue?.fields.manufacture_date ? "customs-manufacture-date-error" : ""}`.trim()} aria-invalid={issue?.fields.manufacture_date ? true : undefined} />
                <span className={styles.help} id={getFieldHelpId("manufacture_date")}>Укажите число, месяц и год по документам. Одного года выпуска недостаточно.</span>
                {issue?.fields.manufacture_date && <span className={styles.fieldError} id="customs-manufacture-date-error">{issue.fields.manufacture_date}</span>}
              </div>

              <fieldset className={styles.engine} aria-describedby={issue?.fields.engine_type ? "customs-engine-error" : undefined}>
                <legend>Тип двигателя *</legend>
                <label className="choice-card"><input name="engine_type" type="radio" value="petrol" required onChange={invalidatePreviousRequest} /> Бензиновый</label>
                <label className="choice-card"><input name="engine_type" type="radio" value="diesel" required onChange={invalidatePreviousRequest} /> Дизельный</label>
                {issue?.fields.engine_type && <span className={styles.fieldError} id="customs-engine-error">{issue.fields.engine_type}</span>}
              </fieldset>

              <div className="field">
                <label htmlFor="customs-engine-volume">Объём двигателя, см³ *</label>
                <input id="customs-engine-volume" name="engine_volume_cc" type="number" inputMode="numeric" min="1" max="100000" step="1" required onChange={invalidatePreviousRequest} aria-describedby={`${getFieldHelpId("engine_volume_cc")} ${issue?.fields.engine_volume_cc ? "customs-engine-volume-error" : ""}`.trim()} aria-invalid={issue?.fields.engine_volume_cc ? true : undefined} />
                <span className={styles.help} id={getFieldHelpId("engine_volume_cc")}>Введите точный целый объём из документов.</span>
                {issue?.fields.engine_volume_cc && <span className={styles.fieldError} id="customs-engine-volume-error">{issue.fields.engine_volume_cc}</span>}
              </div>

              <fieldset className={styles.confirmations}>
                <legend>Подтверждения *</legend>
                <label className="check-field"><input name="personal_use" type="checkbox" value="yes" required onChange={invalidatePreviousRequest} /> Автомобиль ввозится для личного пользования.</label>
                {issue?.fields.personal_use && <span className={styles.fieldError}>{issue.fields.personal_use}</span>}
                <label className="check-field"><input name="origin_outside_eaeu" type="checkbox" value="yes" required onChange={invalidatePreviousRequest} /> Автомобиль ввозится из-за пределов ЕАЭС.</label>
                {issue?.fields.origin_outside_eaeu && <span className={styles.fieldError}>{issue.fields.origin_outside_eaeu}</span>}
              </fieldset>
            </div>

            {issue && <div className={`notice ${styles.errorPanel}`} role="alert" aria-live="assertive">
              <p>{issue.summary}</p>
              <button className="button button-secondary" type="button" disabled={busy} onClick={() => { setIssue(null); formRef.current?.requestSubmit(); }}>Повторить расчёт</button>
            </div>}

            {busy && <p className={styles.status} role="status" aria-live="polite">Выполняем расчёт по официальным данным…</p>}
            <div className={styles.actions}>
              <button className="button button-primary" type="submit" disabled={busy || metaLoading || metaError || !meta?.calculation_available}>
                {busy ? "Выполняем расчёт…" : "Рассчитать платежи"}
              </button>
              {meta && !meta.calculation_available && <span className={styles.help}>Расчёт станет доступен после подтверждения правил и контрольных примеров.</span>}
            </div>
          </form>
        </section>

        <aside className={styles.explainer} aria-labelledby="customs-scope-title">
          <h2 id="customs-scope-title">Для какого случая подходит расчёт</h2>
          {meta && <ul>
            {meta.scope_notes.map((note) => <li key={note}>{note}</li>)}
          </ul>}
          {meta?.rules_version && <p className={styles.provenance}>Версия правил {meta.rules_version}{meta.verified_on ? ` · проверена ${meta.verified_on}` : ""}.</p>}
          {!meta && <ul>
            <li>Физическое лицо ввозит легковой автомобиль категории M1 для личного пользования.</li>
            <li>Автомобиль с бензиновым или дизельным двигателем ввозится из-за пределов ЕАЭС в Беларусь без льгот.</li>
            <li>Электромобили, любые гибриды, ввоз из ЕАЭС, юридические лица и льготы не поддерживаются.</li>
          </ul>}
          <p>Цена покупки служит оценкой таможенной стоимости. Окончательную стоимость определяет таможня. Цена автомобиля, доставка, брокерские услуги и страхование не входят в сумму таможенных платежей.</p>
          <p>Отдельный НДС не прибавляется поверх единой ставки.</p>
          {meta && <SourceLinks sources={meta.sources} label="Источники и дата проверки" />}
        </aside>
      </div>

      {result && <section className={styles.result} aria-labelledby="customs-result-title" aria-live="polite">
        <div className={styles.resultHeading}>
          <div>
            <p className="eyebrow">Результат от сервера</p>
            <h2 id="customs-result-title">Предварительная оценка платежей</h2>
          </div>
          <span className={styles.resultVersion}>Версия правил {result.rules_version}</span>
        </div>
        <dl className={styles.resultFacts}>
          <div><dt>Таможенная стоимость для расчёта</dt><dd>{result.customs_value_eur} EUR</dd></div>
          <div><dt>Возрастная категория по точной дате</dt><dd>{ageBandLabels[result.age_band]}</dd></div>
          <div><dt>Единая пошлина и налоги</dt><dd>{result.duty_eur} EUR · {result.duty_byn} BYN</dd></div>
          <div><dt>Утилизационный сбор</dt><dd>{result.recycling_fee_byn} BYN</dd></div>
          <div><dt>Обязательный сбор за таможенные операции</dt><dd>{result.customs_fee_byn} BYN</dd></div>
          <div className={styles.total}><dt>Итого таможенные платежи</dt><dd>{result.total_byn} BYN</dd></div>
        </dl>
        <p className={styles.priceNote}>Цена покупки — только оценка таможенной стоимости; она не прибавляется к итогу таможенных платежей. Окончательную таможенную стоимость определяет таможня.</p>
        <section className={styles.rateDetails} aria-label="Использованные официальные курсы">
          <h3>Курсы НБРБ на {result.rate_date}</h3>
          <ul>
            {result.rates_used.map((rate) => <li key={rate.currency}>{rate.byn_per_unit} BYN за 1 {rate.currency} · официальный курс {rate.official_rate} / {rate.scale}</li>)}
          </ul>
        </section>
        <p className={styles.priceNote}>Окончательные платежи в BYN рассчитываются по курсу НБРБ на день регистрации пассажирской таможенной декларации.</p>
        {result.warnings.length > 0 && <section className={styles.warnings} aria-label="Предупреждения">
          <h3>Обратите внимание</h3>
          <ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </section>}
        <div className={styles.resultMeta}>Дата расчёта: {result.calculation_date}{meta?.verified_on ? ` · дата сверки правил: ${meta.verified_on}` : ""}</div>
        <SourceLinks sources={result.sources} label="Источники расчёта" />
      </section>}
    </div>
  );
}
