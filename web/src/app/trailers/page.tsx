import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const title = "Прицепы";
const description = "Прицепы и полуприцепы в Беларуси: объявления от владельцев и компаний, цены в BYN и USD.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: siteUrl("/trailers") },
  openGraph: buildOpenGraph({ title, description, path: "/trailers" }),
};

export default function TrailersPage() { return <CategoryLanding slug="trailers" />; }
