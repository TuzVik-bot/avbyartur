"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import styles from "./contact-click-consent.module.css";

export type ContactClickConsentValue = "granted" | "denied" | "unknown";
const STORAGE_KEY = "avtorinok.contact_click_consent";
const ConsentContext = createContext<{ consent: ContactClickConsentValue; setConsent: (value: ContactClickConsentValue) => void }>({ consent: "unknown", setConsent: () => undefined });

export function ContactClickConsentProvider({ children }: { children: React.ReactNode }) {
  const [consent, setConsentState] = useState<ContactClickConsentValue>("unknown");
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "granted" || stored === "denied") setConsentState(stored);
  }, []);
  const value = useMemo(() => ({ consent, setConsent: (next: ContactClickConsentValue) => {
    setConsentState(next);
    if (next === "unknown") window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, next);
  } }), [consent]);
  return <ConsentContext.Provider value={value}>{children}</ConsentContext.Provider>;
}

export function useContactClickConsent() {
  return useContext(ConsentContext);
}

export function ContactClickConsent() {
  const { consent, setConsent } = useContactClickConsent();
  return <aside className={styles.root} aria-label="Настройки измерения обращений">
    {consent === "unknown" ? <>
      <strong>Измерять обращения к продавцам?</strong>
      <p>При согласии мы посчитаем переходы к телефону, Telegram, Viber и внутреннему чату. Событие содержит только ID объявления, канал, время и технический ID дедупликации; телефон, аккаунт, текст и URL не записываются.</p>
      <div className={styles.actions}><button className="button button-primary button-small" type="button" data-consent-choice="granted" onClick={() => setConsent("granted")}>Разрешить</button><button className="button button-secondary button-small" type="button" data-consent-choice="denied" onClick={() => setConsent("denied")}>Запретить</button></div>
    </> : <details><summary>Измерение обращений: {consent === "granted" ? "разрешено" : "запрещено"}</summary><p>Настройка хранится только в этом браузере и не связана с условиями регистрации или политикой конфиденциальности.</p><button className="button button-secondary button-small" type="button" data-consent-choice={consent === "granted" ? "denied" : "granted"} onClick={() => setConsent(consent === "granted" ? "denied" : "granted")}>{consent === "granted" ? "Запретить измерение" : "Разрешить измерение"}</button></details>}
  </aside>;
}
