"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, LayoutGrid, LogOut, Menu, Plus, ShieldCheck, UserRound, X } from "lucide-react";
import { CatalogNavigation } from "./catalog-navigation";
import styles from "./site-navigation.module.css";
import { useAuth } from "@/components/auth-provider";
import { CornflowerMark } from "@/components/cornflower-mark";
import { DEFAULT_LOCALE, getMessage, localizedPath } from "@/lib/i18n";

export function SiteHeader() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [panel, setPanel] = useState<"catalog" | "services" | null>(null);
  const headerRef = useRef<HTMLElement>(null);
  const catalogRef = useRef<HTMLDivElement>(null);
  const servicesRef = useRef<HTMLDivElement>(null);
  const catalogButton = useRef<HTMLButtonElement>(null);
  const servicesButton = useRef<HTMLButtonElement>(null);
  function closeNavigation() { setOpen(false); setPanel(null); }
  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (!catalogRef.current?.contains(target) && !servicesRef.current?.contains(target)) setPanel(null);
      if (!headerRef.current?.contains(target)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (panel) (panel === "catalog" ? catalogButton : servicesButton).current?.focus();
      else if (open) headerRef.current?.querySelector<HTMLButtonElement>(".mobile-menu-toggle")?.focus();
      closeNavigation();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("pointerdown", onPointerDown); document.removeEventListener("keydown", onKeyDown); };
  }, [panel, open]);
  const message = (key: Parameters<typeof getMessage>[0]) => getMessage(key, DEFAULT_LOCALE);

  async function onSignOut() {
    setError("");
    closeNavigation();
    try {
      await signOut();
    } catch {
      setError(message("header.signOutError"));
    }
  }

  return (
    <header ref={headerRef} className={`site-header${user && user.role !== "user" ? " staff-header" : ""} ${styles.header}`} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) closeNavigation(); }}>
      <div className={`header-inner page-width ${styles.inner}`}>
        <Link className={`brand ${styles.brand}`} href={localizedPath("/")} onClick={closeNavigation} aria-label={message("header.brandHome")}>
          <span className="brand-mark"><CornflowerMark size={25} /></span>
          <span>авторынок</span>
          <span className="brand-country">BY</span>
        </Link>
        <div ref={catalogRef} className={styles.catalog}>
          <button ref={catalogButton} className={`${styles.catalogButton} ${panel === "catalog" ? styles.selected : ""}`} type="button" aria-label="Разделы объявлений" aria-expanded={panel === "catalog"} aria-controls="catalog-navigation" onClick={() => { setOpen(false); setPanel(panel === "catalog" ? null : "catalog"); }}><LayoutGrid size={19} aria-hidden="true" /><span>Каталог</span><ChevronDown size={15} aria-hidden="true" /></button>
          <div id="catalog-navigation" className={styles.catalogPanel} hidden={panel !== "catalog"}><CatalogNavigation onNavigate={closeNavigation} /></div>
        </div>
        <button className={`icon-button mobile-menu-toggle ${styles.mobileToggle}`} type="button" aria-label={message(open ? "header.closeMenu" : "header.openMenu")} aria-expanded={open} aria-controls="main-navigation" onClick={() => { setPanel(null); setOpen(!open); }}>
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
        <nav id="main-navigation" className={`main-nav ${styles.mainNav} ${open ? "is-open" : ""}`} aria-label={message("header.navigation")}>
          <Link href={localizedPath("/cars")} onClick={closeNavigation}>{message("header.cars")}</Link>
          <Link href={localizedPath("/dealers")} onClick={closeNavigation}>{message("header.companies")}</Link>
          <Link href={localizedPath("/useful-information")} onClick={closeNavigation}>Полезная информация</Link>
          <div ref={servicesRef} className={styles.services}>
            <button ref={servicesButton} className={styles.servicesButton} type="button" aria-expanded={panel === "services"} aria-controls="services-navigation" onClick={() => setPanel(panel === "services" ? null : "services")}>Сервисы<ChevronDown size={14} aria-hidden="true" /></button>
            <div id="services-navigation" className={styles.servicesPanel} hidden={panel !== "services"}>
              <Link href={localizedPath("/customs-calculator")} onClick={closeNavigation}>{message("header.customsCalculator")}</Link>
              <Link href={localizedPath("/currency-converter")} onClick={closeNavigation}>{message("header.currencyConverter")}</Link>
            </div>
          </div>
          {user && user.role !== "user" && <Link className="nav-icon-link" href={localizedPath("/moderation")} onClick={closeNavigation}><ShieldCheck size={17} /> {message("header.moderation")}</Link>}
          {user?.role === "admin" && <Link className="nav-icon-link" href={localizedPath("/admin")} onClick={closeNavigation}><ShieldCheck size={17} /> {message("header.administration")}</Link>}
          {user ? <Link className="nav-icon-link" href={localizedPath("/account")} onClick={closeNavigation}><UserRound size={17} /> {message("header.account")}</Link> : <Link href={localizedPath("/login")} onClick={closeNavigation}>{message("header.signIn")}</Link>}
          {user && <button className="mobile-signout" type="button" onClick={onSignOut}><LogOut size={17} /> {message("header.signOut")}</button>}
        </nav>
        <div className={`header-actions ${styles.actions}`}>
          {user && <button className="icon-button signout-button" type="button" title={message("header.signOut")} aria-label={message("header.signOut")} onClick={onSignOut}><LogOut size={18} /></button>}
          <Link className="button button-primary header-sell" href={localizedPath("/sell")} aria-label={message("header.sellListing")} onClick={closeNavigation}><Plus size={17} /> {message("header.sellListing")}</Link>
        </div>
      </div>
      {error && <p className="header-error" role="alert">{error}</p>}
    </header>
  );
}
