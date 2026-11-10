"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import styles from "./contact-click-consent.module.css";
import { setMeasurementConsent } from "@/lib/funnel-analytics";
import Link from "next/link";

export type ContactClickConsentValue = "granted" | "denied" | "unknown";
const STORAGE_KEY = "avtorinok.contact_click_consent";
const ConsentContext = createContext<{ consent: ContactClickConsentValue; setConsent: (value: ContactClickConsentValue) => void }>({ consent: "unknown", setConsent: () => undefined });

export function ContactClickConsentProvider({ children }: { children: React.ReactNode }) {
  const [consent, setConsentState] = useState<ContactClickConsentValue>("unknown");
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "granted" || stored === "denied") setConsentState(stored);
    } catch { /* Storage may be unavailable. */ }
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY && event.key !== null) return;
      const next = event.newValue === "granted" || event.newValue === "denied" ? event.newValue : "unknown";
      if (next !== "granted") setMeasurementConsent(false);
      setConsentState(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  const value = useMemo(() => ({ consent, setConsent: (next: ContactClickConsentValue) => {
    if (next !== "granted") setMeasurementConsent(false);
    setConsentState(next);
    try {
      if (next === "unknown") window.localStorage.removeItem(STORAGE_KEY);
      else window.localStorage.setItem(STORAGE_KEY, next);
    } catch { /* Keep the choice in memory for this tab. */ }
  } }), [consent]);
  return <ConsentContext.Provider value={value}>{children}</ConsentContext.Provider>;
}

export function useContactClickConsent() {
  return useContext(ConsentContext);
}

export function ContactClickConsent() {
  const { consent, setConsent } = useContactClickConsent();
  return <details className={styles.root} aria-label="Настройки аналитики">
    <summary>Настройки аналитики</summary>
    <div className={styles.content}>
    {consent === "unknown" ? <>
      <strong>Разрешить аналитику использования сайта?</strong>
      <p>С вашего согласия Google Analytics 4 обрабатывает данные о поиске, просмотре объявлений, обращениях, регистрации и публикации. Мы передаём ограниченные параметры событий; Google может обрабатывать технические данные устройства и соединения, в том числе за пределами Беларуси. Вы можете изменить выбор позже.</p>
      <p><Link href="/cookie-policy">Какие данные используются</Link> · <Link href="/privacy-policy">Внешняя обработка и конфиденциальность</Link></p>
      <div className={styles.actions}><button className="button button-primary button-small" type="button" data-consent-choice="granted" onClick={() => setConsent("granted")}>Разрешить</button><button className="button button-secondary button-small" type="button" data-consent-choice="denied" onClick={() => setConsent("denied")}>Запретить</button></div>
    </> : <><p>Аналитика {consent === "granted" ? "разрешена" : "запрещена"}. Выбор сохраняется в этом браузере, если его хранилище доступно. Отказ не ограничивает использование сайта.</p><button className="button button-secondary button-small" type="button" data-consent-choice={consent === "granted" ? "denied" : "granted"} onClick={() => setConsent(consent === "granted" ? "denied" : "granted")}>{consent === "granted" ? "Запретить аналитику" : "Разрешить аналитику"}</button></>}
    </div>
  </details>;
}
