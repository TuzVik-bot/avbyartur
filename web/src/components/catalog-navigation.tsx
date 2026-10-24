import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { advertisementSections } from "@/lib/advertisement-sections";
import styles from "./advertisement-navigation.module.css";

export function CatalogNavigation({ onNavigate }: { onNavigate: () => void }) {
  return <nav aria-label="Разделы объявлений" className={styles.catalogContent}>
    <div className={styles.panelHeading}><h2>Объявления</h2><Link href="/cars" onClick={onNavigate}>Все автомобили <ArrowRight size={16} aria-hidden="true" /></Link></div>
    <ul className={styles.advertisementList}>
      {advertisementSections.map(({ label, href }) => <li key={href}>
        <Link href={href} onClick={onNavigate}>{label}<ArrowRight size={15} aria-hidden="true" /></Link>
      </li>)}
    </ul>
  </nav>;
}
