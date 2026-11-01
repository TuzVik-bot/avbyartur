import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Прицепы и полуприцепы для легковых и грузовых автомобилей в Беларуси: объявления от владельцев и компаний.";
export const metadata: Metadata = {
  title: "Прицепы",
  description,
  alternates: { canonical: siteUrl("/trailers") },
  openGraph: buildOpenGraph({ title: "Прицепы", description, path: "/trailers" }),
};
export default function TrailersPage() { return <CategoryLanding slug="trailers" />; }
