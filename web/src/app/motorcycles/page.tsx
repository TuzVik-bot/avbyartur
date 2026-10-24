import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";

export const metadata: Metadata = { title: "Мототехника" };
export default function MotorcyclesPage() { return <CategoryLanding slug="motorcycles" />; }
