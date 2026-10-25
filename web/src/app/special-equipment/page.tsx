import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Экскаваторы, погрузчики, краны и дорожная техника в Беларуси: объявления от владельцев и компаний.";
export const metadata: Metadata = {
  title: "Спецтехника",
  description,
  alternates: { canonical: siteUrl("/special-equipment") },
  openGraph: buildOpenGraph({ title: "Спецтехника", description, path: "/special-equipment" }),
};
export default function SpecialEquipmentPage() { return <CategoryLanding slug="special-equipment" />; }
