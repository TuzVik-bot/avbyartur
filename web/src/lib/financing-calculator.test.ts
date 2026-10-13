import { describe, expect, it } from "vitest";
import { calculateFinancing } from "@/lib/financing-calculator";

describe("calculateFinancing", () => {
  it("calculates an interest-free loan from the entered assumptions", () => {
    expect(calculateFinancing({
      mode: "credit",
      price: 120000,
      downPayment: 24000,
      months: 48,
      annualRatePercent: 0,
      residualPayment: 0,
      feesTotal: 0
    })).toEqual({ monthlyPayment: 2000, lastMonthlyPayment: 2000, totalCost: 120000, interestAndFees: 0 });
  });

  it("settles the rounding remainder in the last instalment without negative interest", () => {
    const estimate = calculateFinancing({ mode: "credit", price: 1, downPayment: 0, months: 3,
      annualRatePercent: 0, residualPayment: 0, feesTotal: 0 });
    expect(estimate).toEqual({ monthlyPayment: 0.33, lastMonthlyPayment: 0.34, totalCost: 1, interestAndFees: 0 });
  });

  it("keeps the last payment nonnegative when rounded regular payments would exceed the principal", () => {
    const estimate = calculateFinancing({ mode: "credit", price: 2, downPayment: 0, months: 360,
      annualRatePercent: 0, residualPayment: 0, feesTotal: 0 });
    expect(estimate.lastMonthlyPayment).toBeGreaterThanOrEqual(0);
    expect(estimate.totalCost).toBe(2);
    expect(estimate.monthlyPayment * 359 + estimate.lastMonthlyPayment).toBeCloseTo(2, 2);
  });

  it("keeps a very small positive interest rate finite", () => {
    const estimate = calculateFinancing({ mode: "credit", price: 1, downPayment: 0, months: 3,
      annualRatePercent: 1e-30, residualPayment: 0, feesTotal: 0 });
    expect(estimate.totalCost).toBe(1);
    expect(estimate.interestAndFees).toBe(0);
  });

  it("rejects extreme finite fees before they can yield an infinite estimate", () => {
    expect(() => calculateFinancing({ mode: "credit", price: 1, downPayment: 0, months: 1,
      annualRatePercent: 0, residualPayment: 0, feesTotal: Number.MAX_VALUE })).toThrow("Комиссии должны быть от 0 до 1 000 000 000 000.");
  });

  it("calculates equal monthly instalments at a positive annual rate", () => {
    expect(calculateFinancing({
      mode: "credit",
      price: 100000,
      downPayment: 0,
      months: 12,
      annualRatePercent: 12,
      residualPayment: 0,
      feesTotal: 0
    }).monthlyPayment).toBe(8884.88);
  });

  it("includes the leasing residual payment and entered fees in the estimate", () => {
    expect(calculateFinancing({
      mode: "leasing",
      price: 120000,
      downPayment: 24000,
      months: 48,
      annualRatePercent: 0,
      residualPayment: 48000,
      feesTotal: 1200
    })).toEqual({ monthlyPayment: 1025, lastMonthlyPayment: 1025, totalCost: 121200, interestAndFees: 1200 });
  });

  it("rejects a residual payment that exceeds the amount after down payment", () => {
    expect(() => calculateFinancing({
      mode: "leasing",
      price: 100000,
      downPayment: 20000,
      months: 36,
      annualRatePercent: 8,
      residualPayment: 80001,
      feesTotal: 0
    })).toThrow("Остаточный платёж не может превышать остаток после аванса.");
  });

  it("rejects invalid terms instead of returning a misleading payment", () => {
    expect(() => calculateFinancing({
      mode: "credit",
      price: 100000,
      downPayment: 20000,
      months: 0,
      annualRatePercent: 8,
      residualPayment: 0,
      feesTotal: 0
    })).toThrow("Срок должен быть от 1 до 360 месяцев.");
  });

  it("requires some amount to remain financed", () => {
    expect(() => calculateFinancing({
      mode: "credit",
      price: 100000,
      downPayment: 100000,
      months: 36,
      annualRatePercent: 8,
      residualPayment: 0,
      feesTotal: 0
    })).toThrow("Аванс должен быть меньше цены.");
  });
});
