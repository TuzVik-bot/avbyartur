import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Тракторы, сеялки, уборочные комбайны и другая сельхозтехника в Беларуси для фермеров и хозяйств.";
export const metadata: Metadata = {
  title: "Сельхозтехника",
  description,
  alternates: { canonical: siteUrl("/agricultural-equipment") },
  openGraph: buildOpenGraph({ title: "Сельхозтехника", description, path: "/agricultural-equipment" }),
};
export default function AgriculturalEquipmentPage() { return <CategoryLanding slug="agricultural-equipment" />; }
