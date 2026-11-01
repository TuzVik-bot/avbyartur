import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Запчасти, расходники и аксессуары для автомобилей в Беларуси: предложения от частных продавцов и компаний.";
export const metadata: Metadata = {
  title: "Запчасти и автотовары",
  description,
  alternates: { canonical: siteUrl("/parts") },
  openGraph: buildOpenGraph({ title: "Запчасти и автотовары", description, path: "/parts" }),
};
export default function PartsPage() { return <CategoryLanding slug="parts" />; }
