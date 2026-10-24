import type { Metadata } from "next";
import { ComparisonView } from "@/components/comparison/comparison-view";

export const metadata: Metadata = {
  title: "Сравнение автомобилей",
  description: "Сопоставьте до четырёх объявлений Авторынка по опубликованным характеристикам."
};

export default function ComparePage() {
  return <ComparisonView />;
}
