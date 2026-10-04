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
  lastMonthlyPayment: number;
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
  if (!Number.isFinite(feesTotal) || feesTotal < 0 || feesTotal > 1_000_000_000_000) {
    throw new Error("Комиссии должны быть от 0 до 1 000 000 000 000.");
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
    const discountExponent = -months * Math.log1p(monthlyRate);
    const financedPresentValue = principal - residualPayment * Math.exp(discountExponent);
    baseMonthlyPayment = financedPresentValue * monthlyRate / -Math.expm1(discountExponent);
  }

  // Round the exact instalment total once. Rounding each monthly payment first
  // would change the cost and can invent negative interest at a zero rate.
  const instalmentTotal = roundMoney(baseMonthlyPayment * months + feesTotal);
  const roundedMonthlyPayment = roundMoney(baseMonthlyPayment + feesTotal / months);
  // Usually the regular payment is rounded to the nearest cent. For very small
  // financed amounts, cap it so the final adjustment can never become negative.
  const monthlyPayment = months === 1 ? instalmentTotal : Math.min(roundedMonthlyPayment,
    Math.floor(instalmentTotal / (months - 1) * 100) / 100);
  const lastMonthlyPayment = roundMoney(Math.max(0, instalmentTotal - monthlyPayment * (months - 1)));
  const totalCost = roundMoney(downPayment + instalmentTotal + residualPayment);
  if (![monthlyPayment, lastMonthlyPayment, totalCost].every(Number.isFinite)) {
    throw new Error("Не удалось рассчитать платёж. Проверьте введённые параметры.");
  }
  return {
    monthlyPayment,
    lastMonthlyPayment,
    totalCost,
    interestAndFees: roundMoney(Math.max(0, totalCost - price))
  };
}
