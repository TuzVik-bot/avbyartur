import type { Metadata } from "next";
import { CategoryLanding } from "@/components/category-landing";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const title = "Автобусы";
const description = "Городские, междугородние и туристические автобусы в Беларуси: объявления от владельцев и компаний.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: siteUrl("/buses") },
  openGraph: buildOpenGraph({ title, description, path: "/buses" }),
};

export default function BusesPage() { return <CategoryLanding slug="buses" />; }
