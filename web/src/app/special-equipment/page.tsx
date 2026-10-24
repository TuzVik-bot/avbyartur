import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";

export const metadata: Metadata = { title: "Спецтехника" };
export default function SpecialEquipmentPage() { return <CategoryLanding slug="special-equipment" />; }
