import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";

export const metadata: Metadata = { title: "Шины и диски" };
export default function TiresAndWheelsPage() { return <CategoryLanding slug="tires" />; }
