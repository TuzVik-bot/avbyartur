import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Городские, междугородние и туристические автобусы в Беларуси: объявления от владельцев и компаний.";
export const metadata: Metadata = {
  title: "Автобусы",
  description,
  alternates: { canonical: siteUrl("/buses") },
  openGraph: buildOpenGraph({ title: "Автобусы", description, path: "/buses" }),
};
export default function BusesPage() { return <CategoryLanding slug="buses" />; }
