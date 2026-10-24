import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";

export const metadata: Metadata = { title: "Водный транспорт" };
export default function WatercraftPage() { return <CategoryLanding slug="watercraft" />; }
