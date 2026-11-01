import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Грузовые автомобили, фургоны и самосвалы в Беларуси: объявления от владельцев и компаний.";
export const metadata: Metadata = {
  title: "Грузовики",
  description,
  alternates: { canonical: siteUrl("/trucks") },
  openGraph: buildOpenGraph({ title: "Грузовики", description, path: "/trucks" }),
};
export default function TrucksPage() { return <CategoryLanding slug="trucks" />; }
