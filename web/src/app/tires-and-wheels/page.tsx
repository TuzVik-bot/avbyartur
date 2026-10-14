import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Шины и диски" };

export default function TiresAndWheelsPage() {
  return <div className="page-width">
    <h1>Шины и диски</h1>
    <p>Выберите, какие объявления показать.</p>
    <nav aria-label="Шины и диски">
      <ul>
        <li><Link href="/tires">Шины</Link></li>
        <li><Link href="/wheels">Диски</Link></li>
      </ul>
    </nav>
  </div>;
}
