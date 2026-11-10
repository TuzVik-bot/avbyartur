"use client";

import { useMemo, useState, type ChangeEvent } from "react";
import { api } from "@/lib/api";
import {
  calculateOwnership,
  defaultOwnershipInput,
  validateOwnershipInput,
  type OwnershipInput,
  type OwnershipResult
} from "@/lib/ownership-calculator";
import { ownershipNeedsCurrentRate, ownershipSeedFromListing, parseOwnershipListingId, type OwnershipCustomsRates } from "@/lib/ownership-listing";
import styles from "./ownership-calculator.module.css";

export type OwnershipVehicleSeed = {
  id: string;
  title: string;
  listingHref?: string;
  input: Partial<OwnershipInput>;
  provenance: string[];
  missingFields?: FieldKey[];
};

type Props = { initialVehicles?: OwnershipVehicleSeed[]; notices?: string[] };
type VehicleState = { seed?: OwnershipVehicleSeed; title: string; values: Record<keyof OwnershipInput, string> };
type FieldKey = keyof OwnershipInput;

const fieldNames: Record<FieldKey, string> = {
  priceByn: "Цена автомобиля", years: "Срок владения", annualKm: "Пробег в год",
  resaleByn: "Цена продажи", initialCostsByn: "Первоначальные расходы",
  annualMaintenanceByn: "Обслуживание в год", annualRepairsByn: "Ремонт в год",
  annualInsuranceByn: "Страховка", annualTaxByn: "Налог", annualInspectionByn: "Техосмотр",
  annualTyresByn: "Шины в год", monthlyParkingByn: "Парковка в месяц", monthlyWashByn: "Мойка в месяц",
  fuelLitresPer100Km: "Расход топлива, л / 100 км", fuelPriceByn: "Цена топлива за литр",
  electricityKwhPer100Km: "Расход электричества, кВт·ч / 100 км", homeChargingPercent: "Зарядка дома",
  homeElectricityPriceByn: "Домашний тариф за кВт·ч", publicElectricityPriceByn: "Публичный тариф за кВт·ч",
  chargingLossPercent: "Потери при зарядке", loanAmountByn: "Сумма кредита", loanAnnualRatePercent: "Ставка кредита",
  loanMonths: "Срок кредита, месяцев", energyType: "Тип двигателя", electricKmPercent: "Доля пробега на электричестве"
};

const detailFields: { title: string; fields: FieldKey[] }[] = [
  { title: "Расходы на содержание", fields: ["annualMaintenanceByn", "annualRepairsByn", "annualInsuranceByn", "annualTaxByn", "annualInspectionByn", "annualTyresByn", "monthlyParkingByn", "monthlyWashByn"] },
  { title: "Топливо и зарядка", fields: ["fuelLitresPer100Km", "fuelPriceByn", "electricityKwhPer100Km", "homeChargingPercent", "homeElectricityPriceByn", "publicElectricityPriceByn", "chargingLossPercent", "electricKmPercent"] },
  { title: "Кредит", fields: ["loanAmountByn", "loanAnnualRatePercent", "loanMonths"] }
];

function numberText(value: number): string {
  return new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 2 }).format(value);
}

function money(value: number | null): string {
  return value === null ? "—" : `${numberText(value)} BYN`;
}

function yearLabel(years: number): string {
  const lastTwo = years % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return `${years} лет`;
  if (years % 10 === 1) return `${years} год`;
  if (years % 10 >= 2 && years % 10 <= 4) return `${years} года`;
  return `${years} лет`;
}

function makeVehicle(seed?: OwnershipVehicleSeed, title = "Пример расчёта"): VehicleState {
  const input = { ...defaultOwnershipInput, ...seed?.input };
  const values = Object.fromEntries(Object.entries(input).map(([key, value]) => [key, String(value)])) as Record<FieldKey, string>;
  if (seed && seed.input.priceByn === undefined) {
    values.priceByn = "";
    values.resaleByn = "";
  }
  for (const field of seed?.missingFields ?? []) values[field] = "";
  return {
    seed,
    title: seed?.title ?? title,
    values
  };
}

function inactiveEnergyFields(energyType: OwnershipInput["energyType"]): FieldKey[] {
  if (energyType === "fuel") return ["electricityKwhPer100Km", "homeChargingPercent", "homeElectricityPriceByn", "publicElectricityPriceByn", "chargingLossPercent", "electricKmPercent"];
  if (energyType === "electric") return ["fuelLitresPer100Km", "fuelPriceByn", "electricKmPercent"];
  return [];
}

function toInput(vehicle: VehicleState, shared: Pick<OwnershipInput, "years" | "annualKm">): OwnershipInput {
  const input: Record<string, string | number> = { ...vehicle.values, ...shared };
  const inactive = new Set(inactiveEnergyFields(vehicle.values.energyType as OwnershipInput["energyType"]));
  for (const [key, value] of Object.entries(input)) {
    if (key === "energyType") continue;
    const normalized = String(value).trim().replace(",", ".");
    input[key] = normalized === "" ? (inactive.has(key as FieldKey) ? defaultOwnershipInput[key as FieldKey] as number : Number.NaN) : Number(normalized);
  }
  return input as unknown as OwnershipInput;
}

function fieldUnit(key: FieldKey): string {
  if (key.endsWith("Byn")) return "BYN";
  if (key === "years") return "лет";
  if (key === "annualKm") return "км / год";
  if (key === "loanMonths") return "мес.";
  if (key === "fuelLitresPer100Km") return "л / 100 км";
  if (key === "electricityKwhPer100Km") return "кВт·ч / 100 км";
  if (key.toLowerCase().includes("percent")) return "%";
  return "";
}

function Field({ field, value, onChange, shared = false, name }: { field: FieldKey; value: string; onChange: (value: string) => void; shared?: boolean; name?: string }) {
  const id = `${shared ? "shared" : "field"}-${field}-${name ?? ""}`;
  if (field === "energyType") return null;
  return <label className={styles.field} htmlFor={id}>
    <span>{fieldNames[field]}</span>
    <span className={styles.inputWrap}>
      <input id={id} name={name ?? (shared ? `shared-${field}` : undefined)} type="text" inputMode="decimal" value={value} onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)} aria-label={fieldNames[field]} />
      <small>{fieldUnit(field)}</small>
    </span>
  </label>;
}

function resultFor(vehicle: VehicleState, shared: Pick<OwnershipInput, "years" | "annualKm">): { result: OwnershipResult | null; errors: string[] } {
  const inactive = new Set(inactiveEnergyFields(vehicle.values.energyType as OwnershipInput["energyType"]));
  const emptyFields = (Object.keys(vehicle.values) as FieldKey[]).filter((field) => field !== "energyType" && !inactive.has(field) && !vehicle.values[field].trim());
  if (emptyFields.length) return { result: null, errors: emptyFields.map((field) => field === "priceByn" ? "Введите цену автомобиля." : `Введите значение: ${fieldNames[field].toLowerCase()}.`) };
  const input = toInput(vehicle, shared);
  const errors = validateOwnershipInput(input).map((error) => error.replace(/Поле «([^»]+)»/g, (_match, field: string) => `Поле «${fieldNames[field as FieldKey] ?? field}»`));
  if (errors.length) return { result: null, errors };
  try { return { result: calculateOwnership(input), errors: [] }; }
  catch { return { result: null, errors: ["Не удалось выполнить расчёт. Проверьте введённые значения."] }; }
}

function VehicleEditor({ vehicle, index, onField, onTitle, onRemove, canRemove, shared, showResult = true }: {
  vehicle: VehicleState; index: number; onField: (field: FieldKey, value: string) => void; onTitle: (value: string) => void;
  onRemove: () => void; canRemove: boolean; shared: Pick<OwnershipInput, "years" | "annualKm">; showResult?: boolean;
}) {
  const { result, errors } = resultFor(vehicle, shared);
  const feedback = errors.length > 0 && <ul className={styles.errors} role="alert">{errors.map((error) => <li key={error}>{error}</li>)}</ul>;
  return <section className={styles.vehicle} aria-label={`Автомобиль ${index + 1}`}>
    <div className={styles.vehicleHeading}>
      <label className={styles.titleField}><span>{index === 0 ? "Автомобиль" : "Сравнить с"}</span><input aria-label={`Название автомобиля ${index + 1}`} value={vehicle.title} onChange={(event) => onTitle(event.target.value)} /></label>
      {!vehicle.seed && <span className={styles.exampleTag}>Пример расчёта</span>}
      {vehicle.seed && <span className={styles.sourceTag}>Данные объявления</span>}
      {canRemove && <button type="button" className={styles.removeButton} onClick={onRemove}>Убрать</button>}
    </div>
    {vehicle.seed?.provenance?.length ? <><p className={styles.provenance}>{vehicle.seed.provenance.join(" · ")}</p><p className={styles.exampleNote}>Расход энергии, тарифы и расходы на содержание не указаны в объявлении — здесь стоят примерные значения, уточните их.</p></> : <p className={styles.exampleNote}>Примерные значения — измените их под свой автомобиль.</p>}
    <div className={styles.fieldGrid}>
      <Field field="priceByn" name={`vehicle-${index}-priceByn`} value={vehicle.values.priceByn} onChange={(value) => onField("priceByn", value)} />
      <Field field="resaleByn" name={`vehicle-${index}-resaleByn`} value={vehicle.values.resaleByn} onChange={(value) => onField("resaleByn", value)} />
      <Field field="initialCostsByn" name={`vehicle-${index}-initialCostsByn`} value={vehicle.values.initialCostsByn} onChange={(value) => onField("initialCostsByn", value)} />
      <label className={styles.field}>
        <span>{fieldNames.energyType}</span>
        <select id={`vehicle-${index}-energyType`} name={`vehicle-${index}-energyType`} value={vehicle.values.energyType} onChange={(event) => onField("energyType", event.target.value)}>
          <option value="fuel">Бензин / дизель</option><option value="electric">Электромобиль</option><option value="plugin_hybrid">Подключаемый гибрид</option>
        </select>
      </label>
    </div>
    <div className={styles.details}>
      {detailFields.map((group) => <details key={group.title}>
        <summary>{group.title}</summary>
        <div className={styles.fieldGrid}>{group.fields.filter((field) => {
          if (vehicle.values.energyType === "fuel") return !field.startsWith("electric") && !["homeChargingPercent", "homeElectricityPriceByn", "publicElectricityPriceByn", "chargingLossPercent"].includes(field);
          if (vehicle.values.energyType === "electric") return !field.startsWith("fuel");
          return true;
        }).map((field) => <Field key={field} field={field} name={`vehicle-${index}-${field}`} value={vehicle.values[field]} onChange={(value) => onField(field, value)} />)}</div>
      </details>)}
    </div>
    {showResult === false ? feedback : <section className={styles.vehicleResult} id={index === 0 ? "ownership-results" : `ownership-results-${index}`} tabIndex={-1} aria-label={`Результат расчёта автомобиля ${index + 1}`}>
      {feedback}
      {result && <ResultPanel result={result} index={index} />}
    </section>}
  </section>;
}

function ResultPanel({ result, index }: { result: OwnershipResult; index: number }) {
  return <div className={styles.result}>
    <div className={styles.metrics}>
      <div className={styles.primaryMetric}><span>Бюджет в месяц</span><strong data-result={index === 0 ? "monthly" : `monthly-${index}`}>{money(result.monthlyBudgetByn)}</strong><small>на время кредита и эксплуатации</small></div>
      <div className={styles.metric}><span>На старте</span><strong>{money(result.upfrontByn)}</strong><small>взнос и расходы при покупке</small></div>
      <div className={styles.metric}><span>За весь срок</span><strong data-result={index === 0 ? "total" : `total-${index}`}>{money(result.totalOwnershipByn)}</strong><small>с учётом продажи</small></div>
      <div className={styles.metric}><span>Среднее в месяц</span><strong>{money(result.averageMonthlyOwnershipByn)}</strong><small>за {yearLabel(result.yearly.length)} владения</small></div>
      <div className={styles.metric}><span>Стоимость километра</span><strong>{money(result.costPerKmByn)}</strong><small>весь срок владения</small></div>
    </div>
    <p className={styles.loanNote}>В месячном бюджете учтён полный платёж по кредиту: <strong>{money(result.loanMonthlyPaymentByn)} / мес.</strong><br />Расходы на эксплуатацию после погашения кредита: <strong>{money(result.operatingAnnualByn / 12)} / мес.</strong></p>
    <h3>Из чего складывается сумма</h3>
    <div className={styles.tableScroll}><table><thead><tr><th>Расход</th><th>За срок владения</th></tr></thead><tbody>
      {result.breakdown.map((row) => <tr key={row.key}><th scope="row">{row.label}</th><td>{money(row.totalByn)}</td></tr>)}
      <tr className={styles.totalRow}><th scope="row">Итого с учётом продажи</th><td>{money(result.totalOwnershipByn)}</td></tr>
    </tbody></table></div>
    <details className={styles.schedule}><summary>Расходы и остаток долга по годам</summary><div className={styles.tableScroll}><table><thead><tr><th>Год</th><th>Эксплуатация</th><th>Платежи</th><th>Проценты</th><th>Долг на конец года</th></tr></thead><tbody>{result.yearly.map((year) => <tr key={year.year}><th scope="row">{year.year}</th><td>{money(year.operatingByn)}</td><td>{money(year.loanPaymentsByn)}</td><td>{money(year.loanInterestByn)}</td><td>{money(year.remainingDebtByn)}</td></tr>)}</tbody></table></div><p>Ожидаемая выручка от продажи после погашения остатка долга: <strong>{money(result.saleProceedsByn)}</strong></p></details>
  </div>;
}

export function OwnershipCalculator({ initialVehicles, notices = [] }: Props) {
  const seeds = (initialVehicles ?? []).slice(0, 2);
  const [vehicles, setVehicles] = useState<VehicleState[]>(seeds.length ? seeds.map((seed) => makeVehicle(seed)) : [makeVehicle()]);
  const [sharedText, setSharedText] = useState({ years: String(seeds[0]?.input.years ?? defaultOwnershipInput.years), annualKm: String(seeds[0]?.input.annualKm ?? defaultOwnershipInput.annualKm) });
  const [listing, setListing] = useState("");
  const [listingLoading, setListingLoading] = useState(false);
  const [listingError, setListingError] = useState("");
  const [listingNotice, setListingNotice] = useState("");
  const shared = useMemo(() => ({ years: sharedText.years.trim() ? Number(sharedText.years.replace(",", ".")) : Number.NaN, annualKm: sharedText.annualKm.trim() ? Number(sharedText.annualKm.replace(",", ".")) : Number.NaN }), [sharedText]);

  const updateVehicle = (index: number, update: Partial<VehicleState> | { field: FieldKey; value: string }) => setVehicles((current) => current.map((vehicle, position) => {
    if (position !== index) return vehicle;
    if ("field" in update) return { ...vehicle, values: { ...vehicle.values, [update.field]: update.value } };
    return { ...vehicle, ...update };
  }));

  const loadComparisonListing = async () => {
    const id = parseOwnershipListingId(listing, window.location.origin);
    if (!id) {
      setListingError("Введите UUID или ссылку на объявление этого сайта формата /cars/марка/модель/UUID.");
      setListingNotice("");
      return;
    }
    if (vehicles.some((vehicle) => vehicle.seed?.id === id)) {
      setListingError("Это объявление уже добавлено к сравнению.");
      return;
    }
    setListingLoading(true);
    setListingError("");
    setListingNotice("");
    try {
      const { listing: publicListing } = await api.listing(id);
      let rates: OwnershipCustomsRates | null = null;
      if (ownershipNeedsCurrentRate(publicListing)) {
        try {
          const response = await fetch("/api/v1/customs-calculator/rates", { credentials: "same-origin", cache: "no-store" });
          if (response.ok) rates = await response.json() as OwnershipCustomsRates;
        } catch { /* The seed remains unpriced until the user supplies BYN. */ }
      }
      const seed = ownershipSeedFromListing(publicListing, rates);
      setVehicles((current) => current.length < 2 ? [...current, makeVehicle(seed)] : current);
      if (ownershipNeedsCurrentRate(publicListing) && !rates) setListingNotice("Не удалось получить актуальный курс. Цена объявления в USD не подставлена; укажите сумму в BYN вручную.");
      setListing("");
    } catch {
      setListingError("Не удалось загрузить публичное объявление. Проверьте ссылку и попробуйте ещё раз.");
    } finally {
      setListingLoading(false);
    }
  };
  const comparisonResults = vehicles.map((vehicle) => resultFor(vehicle, shared).result);
  const excludedLabels = [
    ["annualInsuranceByn", "страховка"], ["annualTaxByn", "транспортный налог"], ["annualInspectionByn", "техосмотр"]
  ] as const;
  const excluded = [...new Set(vehicles.flatMap((vehicle) => excludedLabels
    .filter(([field]) => { const value = Number(vehicle.values[field].trim().replace(",", ".")); return !Number.isFinite(value) || value <= 0; })
    .map(([, label]) => label)))];
  const cheaperVehicleTitle = comparisonResults[0] && comparisonResults[1]
    ? vehicles[comparisonResults[0].totalOwnershipByn < comparisonResults[1].totalOwnershipByn ? 0 : 1].title
    : "";
  const comparisonDifference = comparisonResults[0] && comparisonResults[1]
    ? Math.abs(comparisonResults[0].totalOwnershipByn - comparisonResults[1].totalOwnershipByn)
    : 0;

  return <div className={styles.calculator}>
    <section className={styles.summary} aria-label="Краткий результат расчёта">
      <div className={styles.summaryValues}>{vehicles.map((vehicle, index) => <div className={styles.summaryValue} key={vehicle.seed?.id ?? index}>
        <span>{vehicles.length === 1 ? "Бюджет в месяц" : vehicle.title}</span>
        {comparisonResults[index] ? <><output aria-label={`Месячный бюджет: ${vehicle.title}`}>{money(comparisonResults[index].monthlyBudgetByn)}</output><small>на время кредита и эксплуатации</small></> : <strong>Уточните данные</strong>}
      </div>)}</div>
      <a className={styles.resultJump} href="#ownership-results">{comparisonResults[0] ? "Подробный расчёт ↓" : "Проверить данные ↓"}</a>
    </section>
    <div className={styles.shared}><div><strong>Общие условия сравнения</strong><p>Одинаковые срок владения и пробег для всех автомобилей.</p></div><Field field="years" value={sharedText.years} shared onChange={(value) => setSharedText((current) => ({ ...current, years: value }))} /><Field field="annualKm" value={sharedText.annualKm} shared onChange={(value) => setSharedText((current) => ({ ...current, annualKm: value }))} /></div>
    {notices.length > 0 && <aside className={styles.notice}>{notices.map((notice) => <p key={notice}>{notice}</p>)}</aside>}
    {vehicles.length > 1 && <h2 className={styles.comparisonTitle}>Сравнение автомобилей</h2>}
    {vehicles.length === 1 ? <div className={styles.singleLayout}>
      <VehicleEditor vehicle={vehicles[0]} index={0} shared={shared} canRemove={false} showResult={false} onField={(field, value) => updateVehicle(0, { field, value })} onTitle={(title) => updateVehicle(0, { title })} onRemove={() => undefined} />
      <section className={styles.singleResults} id="ownership-results" tabIndex={-1} aria-label="Результат расчёта">
        {comparisonResults[0] ? <ResultPanel result={comparisonResults[0]} index={0} /> : <p className={styles.resultHint}>Заполните подсвеченные поля, чтобы увидеть стоимость владения.</p>}
      </section>
    </div> : <div className={styles.vehicleList}>{vehicles.map((vehicle, index) => <VehicleEditor key={vehicle.seed?.id ?? index} vehicle={vehicle} index={index} shared={shared} canRemove={vehicles.length > 1} onField={(field, value) => updateVehicle(index, { field, value })} onTitle={(title) => updateVehicle(index, { title })} onRemove={() => setVehicles((current) => current.filter((_, position) => position !== index))} />)}</div>}
    {vehicles.length === 2 && comparisonResults[0] && comparisonResults[1] && comparisonDifference > 0 && <p className={styles.comparisonNote} data-comparison-delta>По введённым данным владение автомобилем «{cheaperVehicleTitle}» обходится на {money(comparisonDifference)} дешевле за выбранный срок.</p>}
    {vehicles.length < 2 && <div className={styles.addCar}><button type="button" className={styles.secondaryButton} data-action="add-vehicle" onClick={() => setVehicles((current) => [...current, makeVehicle(undefined, "Второй автомобиль")])}>+ Добавить автомобиль для сравнения</button><form onSubmit={(event) => { event.preventDefault(); void loadComparisonListing(); }}><label htmlFor="compare-listing">Или сравнить с объявлением</label><div><input id="compare-listing" value={listing} onChange={(event) => { setListing(event.target.value); setListingError(""); }} placeholder="Вставьте ссылку или ID объявления" /><button type="submit" disabled={listingLoading}>{listingLoading ? "Загружаем…" : "Загрузить"}</button></div>{listingError && <p className={styles.formError} role="alert">{listingError}</p>}</form></div>}
    {listingNotice && <p className={styles.formNotice} role="status">{listingNotice}</p>}
    {excluded.length > 0 && <div className={styles.assumptions}><strong>Что пока не включено</strong><p>{excluded.map((label) => `${label}: не включено — уточните сумму`).join("; ")} для каждого автомобиля отдельно в разделе расходов на содержание.</p></div>}
    <details className={styles.how}><summary>Как рассчитана стоимость владения</summary><p>Стоимость владения = цена покупки − ожидаемая цена продажи + первоначальные расходы + эксплуатация + проценты по кредиту. Погашение основного долга уже учтено в разнице между покупкой и продажей, поэтому сумма кредита не прибавляется второй раз. При продаже выручка уменьшена на остаток долга.</p><p>Средняя стоимость в месяц — итог за срок, разделённый на количество месяцев. Месячный бюджет во время кредита показывает эксплуатационные расходы и полный платёж по кредиту; после погашения остаются только расходы на эксплуатацию. Энергия, содержание и остаточная цена — ваши оценки, а значения из объявления отмечены источником.</p></details>
  </div>;
}
