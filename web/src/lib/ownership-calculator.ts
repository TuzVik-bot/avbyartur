export type OwnershipInput = {
  priceByn: number;
  years: number;
  annualKm: number;
  resaleByn: number;
  initialCostsByn: number;
  annualMaintenanceByn: number;
  annualRepairsByn: number;
  annualInsuranceByn: number;
  annualTaxByn: number;
  annualInspectionByn: number;
  annualTyresByn: number;
  monthlyParkingByn: number;
  monthlyWashByn: number;
  fuelLitresPer100Km: number;
  fuelPriceByn: number;
  electricityKwhPer100Km: number;
  homeChargingPercent: number;
  homeElectricityPriceByn: number;
  publicElectricityPriceByn: number;
  chargingLossPercent: number;
  loanAmountByn: number;
  loanAnnualRatePercent: number;
  loanMonths: number;
  energyType: "fuel" | "electric" | "plugin_hybrid";
  electricKmPercent: number;
};

export type OwnershipBreakdownRow = { key: string; label: string; totalByn: number };
export type OwnershipYear = {
  year: number;
  operatingByn: number;
  loanPaymentsByn: number;
  loanInterestByn: number;
  remainingDebtByn: number;
};
export type OwnershipResult = {
  totalOwnershipByn: number;
  averageMonthlyOwnershipByn: number;
  monthlyBudgetByn: number;
  upfrontByn: number;
  costPerKmByn: number | null;
  loanMonthlyPaymentByn: number;
  loanInterestByn: number;
  remainingDebtByn: number;
  saleProceedsByn: number;
  energyAnnualByn: number;
  operatingAnnualByn: number;
  depreciationByn: number;
  breakdown: OwnershipBreakdownRow[];
  yearly: OwnershipYear[];
  warnings: string[];
};

export const defaultOwnershipInput: OwnershipInput = {
  priceByn: 30000,
  years: 3,
  annualKm: 15000,
  resaleByn: 18000,
  initialCostsByn: 1000,
  annualMaintenanceByn: 700,
  annualRepairsByn: 500,
  annualInsuranceByn: 0,
  annualTaxByn: 0,
  annualInspectionByn: 0,
  annualTyresByn: 400,
  monthlyParkingByn: 0,
  monthlyWashByn: 0,
  fuelLitresPer100Km: 8,
  fuelPriceByn: 2.5,
  electricityKwhPer100Km: 18,
  homeChargingPercent: 80,
  homeElectricityPriceByn: 0.25,
  publicElectricityPriceByn: 0.65,
  chargingLossPercent: 10,
  loanAmountByn: 0,
  loanAnnualRatePercent: 0,
  loanMonths: 60,
  energyType: "fuel",
  electricKmPercent: 50
};

const numericFields: (keyof OwnershipInput)[] = [
  "priceByn", "years", "annualKm", "resaleByn", "initialCostsByn",
  "annualMaintenanceByn", "annualRepairsByn", "annualInsuranceByn", "annualTaxByn",
  "annualInspectionByn", "annualTyresByn", "monthlyParkingByn", "monthlyWashByn",
  "fuelLitresPer100Km", "fuelPriceByn", "electricityKwhPer100Km", "homeChargingPercent",
  "homeElectricityPriceByn", "publicElectricityPriceByn", "chargingLossPercent",
  "loanAmountByn", "loanAnnualRatePercent", "loanMonths", "electricKmPercent"
];

export function validateOwnershipInput(input: OwnershipInput): string[] {
  const errors: string[] = [];
  for (const field of numericFields) {
    const value = input[field];
    if (typeof value !== "number" || !Number.isFinite(value)) {
      errors.push(`Поле «${field}» должно быть конечным числом.`);
    } else if (value < 0) {
      errors.push(`Поле «${field}» не может быть отрицательным.`);
    } else if (value > 1_000_000_000) {
      errors.push(`Значение поля «${field}» слишком велико.`);
    }
  }
  if (input.years < 1 || input.years > 10 || !Number.isInteger(input.years)) {
    errors.push("Срок владения должен быть целым числом от 1 до 10 лет.");
  }
  if (input.loanMonths < 1 || input.loanMonths > 120 || !Number.isInteger(input.loanMonths)) {
    errors.push("Срок кредита должен быть целым числом от 1 до 120 месяцев.");
  }
  if (input.loanAmountByn > input.priceByn) {
    errors.push("Сумма кредита не может превышать цену автомобиля.");
  }
  if (input.resaleByn > input.priceByn) {
    errors.push("Ожидаемая цена продажи не может превышать цену покупки.");
  }
  if (input.homeChargingPercent > 100) errors.push("Доля домашней зарядки должна быть от 0 до 100%.");
  if (input.chargingLossPercent >= 100) errors.push("Потери зарядки должны быть меньше 100%.");
  if (input.electricKmPercent > 100) errors.push("Доля электрического пробега должна быть от 0 до 100%.");
  if (input.fuelLitresPer100Km > 1000 || input.electricityKwhPer100Km > 1000) {
    errors.push("Расход энергии выглядит неправдоподобно большим.");
  }
  if (input.annualKm > 1_000_000) errors.push("Годовой пробег выглядит неправдоподобно большим.");
  if (input.loanAnnualRatePercent > 200) errors.push("Годовая ставка кредита выглядит неправдоподобно большой.");
  if (!["fuel", "electric", "plugin_hybrid"].includes(input.energyType)) {
    errors.push("Выберите поддерживаемый тип автомобиля.");
  }
  return errors;
}

function annuityPayment(principal: number, annualRatePercent: number, months: number): number {
  if (principal === 0) return 0;
  const monthlyRate = annualRatePercent / 1200;
  if (monthlyRate === 0) return principal / months;
  const accumulatedRate = Math.expm1(months * Math.log1p(monthlyRate));
  return principal * monthlyRate * (1 + accumulatedRate) / accumulatedRate;
}

function roundMoney(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function calculateOwnership(input: OwnershipInput): OwnershipResult {
  const errors = validateOwnershipInput(input);
  if (errors.length) throw new Error(errors.join(" "));

  const electricShare = input.energyType === "electric" ? 1
    : input.energyType === "plugin_hybrid" ? input.electricKmPercent / 100 : 0;
  const fuelShare = 1 - electricShare;
  const fuelAnnual = input.annualKm * fuelShare / 100 * input.fuelLitresPer100Km * input.fuelPriceByn;
  const electricKwh = input.annualKm * electricShare / 100 * input.electricityKwhPer100Km;
  const homeShare = input.homeChargingPercent / 100;
  const electricAnnual = electricKwh / (1 - input.chargingLossPercent / 100) * (
    homeShare * input.homeElectricityPriceByn + (1 - homeShare) * input.publicElectricityPriceByn
  );
  const energyAnnualByn = fuelAnnual + electricAnnual;
  const otherOperatingAnnual = input.annualMaintenanceByn + input.annualRepairsByn +
    input.annualInsuranceByn + input.annualTaxByn + input.annualInspectionByn +
    input.annualTyresByn + (input.monthlyParkingByn + input.monthlyWashByn) * 12;
  const operatingAnnualByn = energyAnnualByn + otherOperatingAnnual;
  const depreciationByn = input.priceByn - input.resaleByn;
  const loanMonthlyPaymentByn = annuityPayment(input.loanAmountByn, input.loanAnnualRatePercent, input.loanMonths);

  let debt = input.loanAmountByn;
  let loanInterestByn = 0;
  const yearly: OwnershipResult["yearly"] = [];
  for (let year = 1; year <= input.years; year += 1) {
    let yearPayments = 0;
    let yearInterest = 0;
    for (let month = 1; month <= 12; month += 1) {
      const elapsedMonth = (year - 1) * 12 + month;
      if (elapsedMonth > input.loanMonths || debt <= 0) continue;
      const interest = debt * input.loanAnnualRatePercent / 1200;
      const payment = elapsedMonth === input.loanMonths
        ? debt + interest
        : Math.min(debt + interest, loanMonthlyPaymentByn);
      debt = Math.max(0, debt + interest - payment);
      yearPayments += payment;
      yearInterest += interest;
      loanInterestByn += interest;
    }
    yearly.push({
      year,
      operatingByn: roundMoney(operatingAnnualByn),
      loanPaymentsByn: roundMoney(yearPayments),
      loanInterestByn: roundMoney(yearInterest),
      remainingDebtByn: roundMoney(debt)
    });
  }

  const remainingDebtByn = debt;
  const saleProceedsByn = input.resaleByn - remainingDebtByn;
  const upfrontByn = input.priceByn - input.loanAmountByn + input.initialCostsByn;
  const rows: OwnershipResult["breakdown"] = [
    { key: "initial", label: "Первоначальные расходы", totalByn: input.initialCostsByn },
    { key: "energy", label: "Топливо и электроэнергия", totalByn: energyAnnualByn * input.years },
    { key: "maintenance", label: "Техническое обслуживание", totalByn: input.annualMaintenanceByn * input.years },
    { key: "repairs", label: "Ремонт", totalByn: input.annualRepairsByn * input.years },
    { key: "insurance", label: "Страхование", totalByn: input.annualInsuranceByn * input.years },
    { key: "tax", label: "Налог", totalByn: input.annualTaxByn * input.years },
    { key: "inspection", label: "Техосмотр", totalByn: input.annualInspectionByn * input.years },
    { key: "tyres", label: "Шины", totalByn: input.annualTyresByn * input.years },
    { key: "parking", label: "Парковка", totalByn: input.monthlyParkingByn * 12 * input.years },
    { key: "wash", label: "Мойка", totalByn: input.monthlyWashByn * 12 * input.years },
    { key: "depreciation", label: "Потеря стоимости", totalByn: depreciationByn },
    { key: "loan_interest", label: "Проценты по кредиту", totalByn: loanInterestByn }
  ].map(row => ({ ...row, totalByn: roundMoney(row.totalByn) }));
  const totalOwnershipByn = rows.reduce((sum, row) => sum + row.totalByn, 0);
  const warnings: string[] = [];
  if (input.annualInsuranceByn === 0) warnings.push("Страхование не включено: укажите собственную оценку.");
  if (input.annualTaxByn === 0) warnings.push("Налог не включён: укажите собственную оценку.");
  if (input.annualInspectionByn === 0) warnings.push("Техосмотр не включён: укажите собственную оценку.");

  return {
    totalOwnershipByn: roundMoney(totalOwnershipByn),
    averageMonthlyOwnershipByn: roundMoney(totalOwnershipByn / (input.years * 12)),
    monthlyBudgetByn: roundMoney(operatingAnnualByn / 12 + (input.loanAmountByn > 0 ? loanMonthlyPaymentByn : 0)),
    upfrontByn: roundMoney(upfrontByn),
    costPerKmByn: input.annualKm === 0 ? null : Math.round(totalOwnershipByn / (input.annualKm * input.years) * 10000) / 10000,
    loanMonthlyPaymentByn: roundMoney(loanMonthlyPaymentByn),
    loanInterestByn: roundMoney(loanInterestByn),
    remainingDebtByn: roundMoney(remainingDebtByn),
    saleProceedsByn: roundMoney(saleProceedsByn),
    energyAnnualByn: roundMoney(energyAnnualByn),
    operatingAnnualByn: roundMoney(operatingAnnualByn),
    depreciationByn: roundMoney(depreciationByn),
    breakdown: rows,
    yearly,
    warnings
  };
}
