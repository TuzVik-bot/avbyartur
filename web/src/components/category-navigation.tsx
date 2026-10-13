import Link from "next/link";
import { advertisementSections } from "@/lib/advertisement-sections";
import styles from "./advertisement-navigation.module.css";

export function CategoryNavigation() {
  return <nav aria-label="Категории объявлений" className={`page-width section ${styles.categoryNavigation}`}>
    <h2>Объявления</h2>
    <ul className={styles.advertisementList}>
      {advertisementSections.map(({ label, href }) => <li key={href}><Link href={href}>{label}</Link></li>)}
    </ul>
  </nav>;
}
