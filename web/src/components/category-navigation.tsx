import Link from "next/link";
import { categories } from "@/lib/listing-categories";
export function CategoryNavigation() {
 return <nav className="page-width section" aria-label="Разделы объявлений"><div className="quick-links">{categories.map(category => <Link className="button button-secondary button-small" key={category.href} href={category.href}>{category.label}</Link>)}</div></nav>;
}
