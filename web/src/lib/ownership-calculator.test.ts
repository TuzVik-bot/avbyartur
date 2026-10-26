import { describe, expect, it } from "vitest";
import {
  calculateOwnership,
  defaultOwnershipInput,
  validateOwnershipInput
} from "@/lib/ownership-calculator";

describe("ownership calculator", () => {
  it("calculates cash ownership cost without counting purchase price twice", () => {
    const result = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 10000,
      years: 2,
      annualKm: 10000,
      resaleByn: 6000,
      initialCostsByn: 500,
      annualMaintenanceByn: 100,
      annualRepairsByn: 200,
      annualInsuranceByn: 0,
      annualTaxByn: 0,
      annualInspectionByn: 0,
      annualTyresByn: 0,
      monthlyParkingByn: 0,
      monthlyWashByn: 0,
      fuelLitresPer100Km: 0,
      energyType: "fuel"
    });

    expect(result.totalOwnershipByn).toBe(5100);
    expect(result.upfrontByn).toBe(10500);
    expect(result.operatingAnnualByn).toBe(300);
    expect(result.depreciationByn).toBe(4000);
    expect(result.costPerKmByn).toBeCloseTo(0.255);
    expect(result.breakdown.reduce((sum, row) => sum + row.totalByn, 0)).toBeCloseTo(result.totalOwnershipByn);
  });

  it("prices EV charging by home and public mix after charging losses", () => {
    const result = calculateOwnership({
      ...defaultOwnershipInput,
      years: 1,
      annualKm: 10000,
      resaleByn: defaultOwnershipInput.priceByn,
      initialCostsByn: 0,
      annualMaintenanceByn: 0,
      annualRepairsByn: 0,
      annualTyresByn: 0,
      homeChargingPercent: 50,
      homeElectricityPriceByn: 0.2,
      publicElectricityPriceByn: 0.6,
      electricityKwhPer100Km: 20,
      chargingLossPercent: 10,
      energyType: "electric"
    });

    expect(result.energyAnnualByn).toBeCloseTo((2000 / 0.9) * 0.4);
  });

  it("uses electric distance share for a plug-in hybrid", () => {
    const result = calculateOwnership({
      ...defaultOwnershipInput,
      years: 1,
      annualKm: 10000,
      resaleByn: defaultOwnershipInput.priceByn,
      initialCostsByn: 0,
      annualMaintenanceByn: 0,
      annualRepairsByn: 0,
      annualTyresByn: 0,
      fuelLitresPer100Km: 10,
      fuelPriceByn: 2,
      electricityKwhPer100Km: 20,
      homeChargingPercent: 100,
      homeElectricityPriceByn: 0.2,
      chargingLossPercent: 0,
      electricKmPercent: 25,
      energyType: "plugin_hybrid"
    });

    expect(result.energyAnnualByn).toBeCloseTo(1500 + 100);
  });

  it("amortizes zero-interest and 12 percent loans and limits horizon interest", () => {
    const zero = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 12000,
      loanAmountByn: 12000,
      loanAnnualRatePercent: 0,
      loanMonths: 12,
      years: 1,
      annualKm: 0,
      resaleByn: 12000
    });
    expect(zero.loanMonthlyPaymentByn).toBe(1000);
    expect(zero.loanInterestByn).toBe(0);
    expect(zero.remainingDebtByn).toBe(0);

    const interest = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 12000,
      loanAmountByn: 12000,
      loanAnnualRatePercent: 12,
      loanMonths: 24,
      years: 1,
      annualKm: 0,
      resaleByn: 12000
    });
    expect(interest.loanMonthlyPaymentByn).toBeCloseTo(564.88, 2);
    expect(interest.loanInterestByn).toBeCloseTo(1136.37, 0);
    expect(interest.remainingDebtByn).toBeCloseTo(6357.79, 0);
    expect(interest.yearly[0]?.loanPaymentsByn).toBeCloseTo(12 * interest.loanMonthlyPaymentByn, 1);
  });

  it("keeps tiny positive interest finite and pays the balance off in the final scheduled month", () => {
    const tinyRate = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 12000,
      loanAmountByn: 12000,
      loanAnnualRatePercent: 1e-14,
      loanMonths: 12,
      years: 1,
      annualKm: 0,
      resaleByn: 12000
    });
    expect(Number.isFinite(tinyRate.loanMonthlyPaymentByn)).toBe(true);
    expect(tinyRate.loanMonthlyPaymentByn).toBeCloseTo(1000, 2);
    expect(tinyRate.remainingDebtByn).toBe(0);

    const normalRate = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 10000,
      loanAmountByn: 9999,
      loanAnnualRatePercent: 7.3,
      loanMonths: 37,
      years: 4,
      annualKm: 0,
      resaleByn: 10000
    });
    expect(normalRate.remainingDebtByn).toBe(0);
  });

  it("stops monthly loan payments after payoff and allows loans beyond the ownership horizon", () => {
    const early = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 12000,
      loanAmountByn: 12000,
      loanAnnualRatePercent: 0,
      loanMonths: 6,
      years: 2,
      annualKm: 0,
      resaleByn: 12000
    });
    expect(early.yearly[0]?.loanPaymentsByn).toBe(12000);
    expect(early.yearly[1]?.loanPaymentsByn).toBe(0);

    const beyond = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 12000,
      loanAmountByn: 12000,
      loanAnnualRatePercent: 0,
      loanMonths: 36,
      years: 1,
      annualKm: 0,
      resaleByn: 12000
    });
    expect(beyond.remainingDebtByn).toBe(8000);
    expect(beyond.saleProceedsByn).toBe(4000);
  });

  it("reconciles ownership cost separately from cash budget and yearly cashflows", () => {
    const result = calculateOwnership({
      ...defaultOwnershipInput,
      priceByn: 10000,
      loanAmountByn: 5000,
      loanAnnualRatePercent: 12,
      loanMonths: 24,
      years: 1,
      annualKm: 10000,
      resaleByn: 8000,
      initialCostsByn: 500,
      annualMaintenanceByn: 100,
      annualRepairsByn: 100,
      annualInsuranceByn: 0,
      annualTaxByn: 0,
      annualInspectionByn: 0,
      annualTyresByn: 0,
      fuelLitresPer100Km: 0
    });

    expect(result.totalOwnershipByn).toBeCloseTo(500 + 200 + 2000 + result.loanInterestByn);
    expect(result.monthlyBudgetByn).toBeCloseTo(result.operatingAnnualByn / 12 + result.loanMonthlyPaymentByn, 1);
    expect(result.yearly[0]?.loanPaymentsByn).toBeCloseTo(result.loanMonthlyPaymentByn * 12, 1);
    expect(result.averageMonthlyOwnershipByn).toBeCloseTo(result.totalOwnershipByn / 12);
  });

  it("returns no per-kilometer cost for zero distance and identical comparison inputs stay equal", () => {
    const zeroDistance = calculateOwnership({ ...defaultOwnershipInput, annualKm: 0 });
    expect(zeroDistance.costPerKmByn).toBeNull();

    const first = calculateOwnership({ ...defaultOwnershipInput, energyType: "electric" });
    const second = calculateOwnership({ ...defaultOwnershipInput, energyType: "electric" });
    expect(second.totalOwnershipByn).toBe(first.totalOwnershipByn);
    expect(second.yearly).toEqual(first.yearly);
  });

  it.each([
    ["NaN", { annualKm: Number.NaN }],
    ["infinity", { priceByn: Number.POSITIVE_INFINITY }],
    ["negative values", { annualRepairsByn: -1 }],
    ["loan exceeding purchase price", { priceByn: 1000, loanAmountByn: 1001 }],
    ["fractional ownership years", { years: 1.5 }],
    ["loan duration over limit", { loanMonths: 121 }],
    ["charging percentage over 100", { homeChargingPercent: 101 }],
    ["electric share below zero", { electricKmPercent: -1 }],
    ["resale above purchase price", { resaleByn: 30001 }]
  ])("rejects %s", (_label, changes) => {
    const errors = validateOwnershipInput({ ...defaultOwnershipInput, ...changes });
    expect(errors.length).toBeGreaterThan(0);
    expect(() => calculateOwnership({ ...defaultOwnershipInput, ...changes })).toThrow();
  });
});
