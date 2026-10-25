import type { Metadata } from "next";
import { CustomsCalculator } from "@/components/customs-calculator";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Рассчитайте таможенные платежи за автомобиль в Беларусь: пошлина, НДС, акциз, сборы и льготы для физических и юридических лиц.";
export const metadata: Metadata = {
  title: "Таможенный калькулятор",
  description,
  alternates: { canonical: siteUrl("/customs-calculator") },
  openGraph: buildOpenGraph({ title: "Таможенный калькулятор", description, path: "/customs-calculator" }),
};

export default function CustomsCalculatorPage() {
  return <CustomsCalculator />;
}
