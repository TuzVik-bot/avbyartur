import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Мотоциклы, скутеры, квадроциклы и снегоходы в Беларуси: объявления от владельцев и дилеров.";
export const metadata: Metadata = {
  title: "Мототехника",
  description,
  alternates: { canonical: siteUrl("/motorcycles") },
  openGraph: buildOpenGraph({ title: "Мототехника", description, path: "/motorcycles" }),
};
export default function MotorcyclesPage() { return <CategoryLanding slug="motorcycles" />; }
