import type { Metadata } from "next";
import { CustomsCalculator } from "@/components/customs-calculator";

export const metadata: Metadata = { title: "Таможенный калькулятор" };

export default function CustomsCalculatorPage() {
  return <CustomsCalculator />;
}
