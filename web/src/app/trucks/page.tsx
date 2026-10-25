import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const title = "Грузовики";
const description = "Грузовики, фургоны и самосвалы в Беларуси: объявления от владельцев и компаний, цены в BYN и USD.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: siteUrl("/trucks") },
  openGraph: buildOpenGraph({ title, description, path: "/trucks" }),
};

export default function TrucksPage() { return <CategoryLanding slug="trucks" />; }
