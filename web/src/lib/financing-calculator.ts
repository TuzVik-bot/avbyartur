export type FinancingMode = "credit" | "leasing";

export type FinancingInput = {
  mode: FinancingMode;
  price: number;
  downPayment: number;
  months: number;
  annualRatePercent: number;
  residualPayment: number;
  feesTotal: number;
};

export type FinancingEstimate = {
  monthlyPayment: number;
  totalCost: number;
  interestAndFees: number;
};

function roundMoney(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function calculateFinancing(input: FinancingInput): FinancingEstimate {
  const { mode, price, downPayment, months, annualRatePercent, residualPayment, feesTotal } = input;
  if (!Number.isFinite(price) || price <= 0 || price > 1_000_000_000_000) {
    throw new Error("Укажите корректную стоимость.");
  }
  if (!Number.isFinite(downPayment) || downPayment < 0 || downPayment >= price) {
    throw new Error("Аванс должен быть меньше цены.");
  }
  if (!Number.isInteger(months) || months < 1 || months > 360) {
    throw new Error("Срок должен быть от 1 до 360 месяцев.");
  }
  if (!Number.isFinite(annualRatePercent) || annualRatePercent < 0 || annualRatePercent > 1000) {
    throw new Error("Ставка должна быть от 0 до 1000% годовых.");
  }
  if (!Number.isFinite(feesTotal) || feesTotal < 0) {
    throw new Error("Комиссии не могут быть отрицательными.");
  }
  if (mode === "credit" && residualPayment !== 0) {
    throw new Error("Выкупной платёж укажите только для лизинга.");
  }
  const principal = price - downPayment;
  if (!Number.isFinite(residualPayment) || residualPayment < 0 || residualPayment > principal) {
    throw new Error("Остаточный платёж не может превышать остаток после аванса.");
  }

  const monthlyRate = annualRatePercent / 1200;
  let baseMonthlyPayment: number;
  if (monthlyRate === 0) {
    baseMonthlyPayment = (principal - residualPayment) / months;
  } else {
    const discountFactor = (1 + monthlyRate) ** months;
    const financedPresentValue = principal - residualPayment / discountFactor;
    baseMonthlyPayment = financedPresentValue * monthlyRate / (1 - (1 + monthlyRate) ** -months);
  }

  const monthlyPayment = roundMoney(baseMonthlyPayment + feesTotal / months);
  const totalCost = roundMoney(downPayment + monthlyPayment * months + residualPayment);
  return {
    monthlyPayment,
    totalCost,
    interestAndFees: roundMoney(totalCost - price)
  };
}
