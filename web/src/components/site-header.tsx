"use client";

import Link from "next/link";
import { useState } from "react";
import { Heart, LogOut, Menu, Plus, ShieldCheck, UserRound, X } from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { CornflowerMark } from "@/components/cornflower-mark";
import { DEFAULT_LOCALE, getMessage, localizedPath } from "@/lib/i18n";

export function SiteHeader() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const message = (key: Parameters<typeof getMessage>[0]) => getMessage(key, DEFAULT_LOCALE);

  async function onSignOut() {
    setError("");
    setOpen(false);
    try {
      await signOut();
    } catch {
      setError(message("header.signOutError"));
    }
  }

  return (
    <header className="site-header">
      <div className="header-inner page-width">
        <Link className="brand" href={localizedPath("/")} aria-label={message("header.brandHome")}>
          <span className="brand-mark"><CornflowerMark size={25} /></span>
          <span>авторынок</span>
          <span className="brand-country">BY</span>
        </Link>
        <button className="icon-button mobile-menu-toggle" type="button" aria-label={message(open ? "header.closeMenu" : "header.openMenu")} aria-expanded={open} aria-controls="main-navigation" onClick={() => setOpen(!open)}>
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
        <nav id="main-navigation" className={`main-nav ${open ? "is-open" : ""}`} aria-label={message("header.navigation")}>
          <Link href={localizedPath("/cars")} onClick={() => setOpen(false)}>{message("header.cars")}</Link>
          <Link href={localizedPath("/dealers")} onClick={() => setOpen(false)}>{message("header.companies")}</Link>
          <Link href={localizedPath("/customs-calculator")} onClick={() => setOpen(false)}>{message("header.customsCalculator")}</Link>
          {user && user.role !== "user" && <Link className="nav-icon-link" href={localizedPath("/moderation")} onClick={() => setOpen(false)}><ShieldCheck size={17} /> {message("header.moderation")}</Link>}
          {user?.role === "admin" && <Link className="nav-icon-link" href={localizedPath("/admin")} onClick={() => setOpen(false)}><ShieldCheck size={17} /> {message("header.administration")}</Link>}
          <Link className="nav-icon-link" href={localizedPath("/account/favorites")} onClick={() => setOpen(false)}><Heart size={17} /> {message("header.favorites")}</Link>
          {user ? <Link className="nav-icon-link" href={localizedPath("/account")} onClick={() => setOpen(false)}><UserRound size={17} /> {message("header.account")}</Link> : <><Link href={localizedPath("/login")} onClick={() => setOpen(false)}>{message("header.signIn")}</Link><Link href={localizedPath("/register")} onClick={() => setOpen(false)}>{message("header.register")}</Link></>}
          {user && <button className="mobile-signout" type="button" onClick={onSignOut}><LogOut size={17} /> {message("header.signOut")}</button>}
        </nav>
        <div className="header-actions">
          {user && <button className="icon-button signout-button" type="button" title={message("header.signOut")} aria-label={message("header.signOut")} onClick={onSignOut}><LogOut size={18} /></button>}
          <Link className="button button-primary header-sell" href={localizedPath("/sell")} onClick={() => setOpen(false)}><Plus size={17} /> {message("header.sellListing")}</Link>
        </div>
      </div>
      {error && <p className="header-error" role="alert">{error}</p>}
    </header>
  );
}
