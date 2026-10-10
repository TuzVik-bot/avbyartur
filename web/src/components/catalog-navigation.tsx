import Link from "next/link";
import { ArrowRight, CarFront, Truck, Wrench } from "lucide-react";
import styles from "./site-navigation.module.css";

const groups = [
  { title: "Автомобили", Icon: CarFront, links: [
    ["С пробегом", "/cars?condition=used"], ["Новые", "/cars?condition=new"], ["Электромобили", "/cars?fuel=electric"]
  ] },
  { title: "Транспорт и техника", Icon: Truck, links: [
    ["Грузовики", "/trucks"], ["Автобусы", "/buses"], ["Мототехника", "/motorcycles"],
    ["Спецтехника", "/special-equipment"], ["Сельхозтехника", "/agricultural-equipment"],
    ["Прицепы", "/trailers"], ["Водный транспорт", "/watercraft"]
  ] },
  { title: "Запчасти и колёса", Icon: Wrench, links: [
    ["Запчасти", "/parts"], ["Диски", "/wheels"], ["Шины", "/tires"]
  ] }
];

export function CatalogNavigation({ onNavigate }: { onNavigate: () => void }) {
  return <nav aria-label="Разделы объявлений" className={styles.catalogContent}>
    <div className={styles.panelHeading}><h2>Разделы объявлений</h2><Link href="/cars" onClick={onNavigate}>Все автомобили <ArrowRight size={16} aria-hidden="true" /></Link></div>
    <div className={styles.groups}>{groups.map(({ title, Icon, links }) => <section key={title} className={styles.group}>
      <h3><span className={styles.groupIcon}><Icon size={20} aria-hidden="true" /></span>{title}</h3>
      <ul>{links.map(([label, href]) => <li key={href}><Link href={href} onClick={onNavigate}>{label}<ArrowRight size={15} aria-hidden="true" /></Link></li>)}</ul>
    </section>)}</div>
  </nav>;
}
