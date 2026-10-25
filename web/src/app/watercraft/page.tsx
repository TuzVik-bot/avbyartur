import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Лодки, лодочные моторы и гидроциклы в Беларуси: объявления от владельцев и дилеров.";
export const metadata: Metadata = {
  title: "Водный транспорт",
  description,
  alternates: { canonical: siteUrl("/watercraft") },
  openGraph: buildOpenGraph({ title: "Водный транспорт", description, path: "/watercraft" }),
};
export default function WatercraftPage() { return <CategoryLanding slug="watercraft" />; }
