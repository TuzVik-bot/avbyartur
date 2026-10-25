import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Летние, зимние и всесезонные шины, литые и кованые колёсные диски в Беларуси.";
export const metadata: Metadata = {
  title: "Шины и диски",
  description,
  alternates: { canonical: siteUrl("/tires-and-wheels") },
  openGraph: buildOpenGraph({ title: "Шины и диски", description, path: "/tires-and-wheels" }),
};
export default function TiresAndWheelsPage() { return <CategoryLanding slug="tires" />; }
