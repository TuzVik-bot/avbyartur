import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const title = "Запчасти и автотовары";
const description = "Запчасти, расходники и аксессуары для автомобилей в Беларуси: объявления от продавцов, цены в BYN и USD.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: siteUrl("/parts") },
  openGraph: buildOpenGraph({ title, description, path: "/parts" }),
};

export default function PartsPage() { return <CategoryLanding slug="parts" />; }
