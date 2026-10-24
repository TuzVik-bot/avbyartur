import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";

export const metadata: Metadata = { title: "Сельхозтехника" };
export default function AgriculturalEquipmentPage() { return <CategoryLanding slug="agricultural-equipment" />; }
