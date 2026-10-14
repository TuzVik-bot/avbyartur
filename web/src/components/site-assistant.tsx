"use client";

import { ArrowUp, ArrowUpRight, Mic, RotateCcw, Square, Volume2, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { isPublicAssistantPage, type AssistantFilters, type AssistantPage, type AssistantReply } from "@/lib/assistant";
import { formatMileage, formatMoney, listingHref, vehicleLabel } from "@/lib/format";
import styles from "./site-assistant.module.css";

type Message = { id: number; role: "user" | "assistant"; text: string; reply?: AssistantReply };
type Recognition = { lang: string; continuous: boolean; interimResults: boolean; start(): void; stop(): void; onresult: ((event: { results: { [index: number]: { [index: number]: { transcript: string } } } }) => void) | null; onerror: (() => void) | null; onend: (() => void) | null };
const greeting: Message = { id: 0, role: "assistant", text: "Здравствуйте! Какой автомобиль ищем?" };

function currentPublicPage(): AssistantPage | undefined {
  const path = window.location.pathname;
  if (!isPublicAssistantPage(path)) return;
  const main = document.querySelector("#main-content");
  if (!main) return;
  const copy = main.cloneNode(true) as HTMLElement;
  copy.querySelectorAll("form, input, textarea, select, button, script, style, [hidden], [aria-hidden='true'], [aria-label*='реклам'], [aria-label*='Реклам']").forEach((element) => element.remove());
  const title = main.querySelector("h1")?.textContent?.trim() || document.title;
  const text = [...copy.querySelectorAll("h1, h2, h3, p, li, dt, dd")].map((element) => element.textContent?.replace(/\s+/g, " ").trim()).filter(Boolean).join("\n").slice(0, 6000);
  if (text.length < 30) return;
  return { path, title, text };
}

export function SiteAssistant() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([greeting]);
  const [draft, setDraft] = useState("");
  const [filters, setFilters] = useState<AssistantFilters>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [engine, setEngine] = useState<"basic" | "ai">("basic");
  const [voiceAvailable, setVoiceAvailable] = useState(false);
  const [micAvailable, setMicAvailable] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const sequence = useRef(1);
  const lock = useRef(false);
  const lastRequest = useRef<{ message: string; summary: boolean } | null>(null);
  const Constructor = () => (window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }).SpeechRecognition || (window as unknown as { webkitSpeechRecognition?: new () => Recognition }).webkitSpeechRecognition;

  useEffect(() => {
    setVoiceAvailable("speechSynthesis" in window);
    setMicAvailable(Boolean(Constructor()));
    return () => { controller.current?.abort(); recognition.current?.stop(); if ("speechSynthesis" in window) window.speechSynthesis.cancel(); };
  }, []);
  useEffect(() => {
    if (!open) return;
    const abort = new AbortController();
    fetch("/api/assistant", { signal: abort.signal }).then((r) => r.json()).then((data) => { if (data.engine === "ai" || data.engine === "basic") setEngine(data.engine); }).catch(() => {});
    input.current?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
      if (event.key === "Tab") {
        const items = [...(panel.current?.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], textarea:not(:disabled)") || [])];
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => { abort.abort(); document.removeEventListener("keydown", keyboard); };
  }, [open]);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [messages, busy, error]);
  useEffect(() => { if (speaking) stopVoice(); }, [pathname]);

  function stopVoice() { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); setSpeaking(false); }
  function close() { stopVoice(); recognition.current?.stop(); setOpen(false); launcher.current?.focus(); }
  function speak(text: string) {
    stopVoice();
    if (!voiceAvailable) return;
    const utterance = new SpeechSynthesisUtterance(text.slice(0, 2500));
    utterance.lang = "ru-RU";
    const voice = window.speechSynthesis.getVoices().find((v) => v.lang.startsWith("ru"));
    if (voice) utterance.voice = voice;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => { setSpeaking(false); setError("Озвучивание недоступно в этом браузере. Текст ответа остаётся в чате."); };
    setSpeaking(true); window.speechSynthesis.speak(utterance);
  }
  function startMic() {
    if (listening) { recognition.current?.stop(); return; }
    const Recognizer = Constructor(); if (!Recognizer) return;
    stopVoice(); setError("");
    const recognizer = new Recognizer(); recognition.current = recognizer;
    recognizer.lang = "ru-RU"; recognizer.continuous = false; recognizer.interimResults = false;
    recognizer.onresult = (event) => { setDraft((text) => `${text} ${event.results[0][0].transcript}`.trim().slice(0, 1200)); input.current?.focus(); };
    recognizer.onerror = () => { setListening(false); setError("Не удалось распознать речь. Проверьте разрешение микрофона или введите сообщение."); };
    recognizer.onend = () => setListening(false);
    try { recognizer.start(); setListening(true); } catch { setError("Микрофон недоступен."); }
  }
  async function send(message: string, summary = false, retry = false) {
    if (lock.current || !message.trim()) return;
    const page = summary ? currentPublicPage() : undefined;
    if (summary && !page) { setError("На этой странице нет публичного текста для пересказа."); return; }
    lock.current = true; setBusy(true); setError(""); stopVoice(); recognition.current?.stop();
    lastRequest.current = { message, summary };
    if (!retry) setMessages((items) => [...items, { id: sequence.current++, role: "user", text: summary ? `Кратко расскажи: ${page?.title}` : message }]);
    setDraft("");
    const abort = new AbortController(); controller.current = abort;
    const timer = setTimeout(() => abort.abort(), 35000);
    try {
      const response = await fetch("/api/assistant", { method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal,
        body: JSON.stringify({ message, filters, history: messages.slice(-6).map(({ role, text }) => ({ role, content: text })), listingIds: [...messages].reverse().find((item) => item.reply?.listings.length)?.reply?.listings.slice(0, 3).map((listing) => listing.id) || [], ...(summary ? { action: "summary", page } : {}) }) });
      const reply = await response.json();
      if (!response.ok) throw new Error(reply.message || "Помощник временно недоступен.");
      setFilters(reply.filters); setEngine(reply.engine);
      setMessages((items) => [...items, { id: sequence.current++, role: "assistant", text: reply.text, reply }]);
      if (summary && voiceAvailable) speak(reply.text);
    } catch (problem) { setError(problem instanceof Error && problem.name !== "AbortError" ? problem.message : "Помощник не ответил вовремя. Попробуйте снова."); }
    finally { clearTimeout(timer); lock.current = false; setBusy(false); controller.current = null; input.current?.focus(); }
  }
  function reset() { controller.current?.abort(); stopVoice(); recognition.current?.stop(); setMessages([greeting]); setFilters({}); setError(""); lastRequest.current = null; setDraft(""); }
  const publicPage = isPublicAssistantPage(pathname || "");
  return <>
    <button ref={launcher} className={styles.launcher} onClick={() => setOpen((value) => !value)} aria-label="Открыть помощника Авторынка" aria-expanded={open} aria-controls="site-assistant" title="Помощник Авторынка">
      <img src="/assistant-mascot.png" alt="" width={56} height={56} />
      <span>Помощник</span>
    </button>
    {open && <section ref={panel} id="site-assistant" className={styles.panel} role="dialog" aria-label="Помощник Авторынка">
      <header className={styles.header}>
        <img src="/assistant-mascot.png" alt="" width={48} height={48} />
        <div><strong>Помощник Авторынка</strong><span className={styles.status}><i />{engine === "ai" ? "ИИ · по данным сайта" : "Базовый режим"}</span></div>
        <button className={styles.icon} onClick={reset} disabled={busy} aria-label="Начать новый разговор" title="Начать новый разговор"><RotateCcw size={17} /></button>
        <button className={styles.icon} onClick={close} aria-label="Закрыть помощника" title="Закрыть"><X size={20} /></button>
      </header>
      <div className={styles.thread} role="log" aria-label="Переписка" aria-live="polite" aria-relevant="additions text">
        {messages.map((item) => <div key={item.id} className={item.role === "user" ? styles.userMessage : styles.assistantMessage}>
          <p>{item.text}</p>
          {item.reply?.labels.length ? <div className={styles.labels}>{item.reply.labels.map((label, index) => <span key={`${index}-${label}`}>{label}</span>)}</div> : null}
          {item.reply?.listings.map((listing) => <Link href={listingHref(listing)} key={listing.id} className={styles.listing} onClick={close}>
            {listing.cover_url || listing.photo_urls?.[0] ? <img src={listing.cover_url || listing.photo_urls?.[0]} alt="" width={88} height={72} loading="lazy" /> : <div className={styles.noPhoto}>Нет фото</div>}
            <div><strong>{listing.title || [listing.make?.name, listing.model?.name, listing.year].filter(Boolean).join(" ")}</strong><b>{formatMoney(listing.price)}</b><small>{[listing.year, vehicleLabel(listing.transmission), formatMileage(listing.mileage_km)].filter(Boolean).join(" · ")}</small></div>
          </Link>)}
          {item.reply?.searchHref && <Link className={styles.catalogLink} href={item.reply.searchHref} onClick={close}>Открыть подборку в каталоге <ArrowUpRight size={16} /></Link>}
          {item.reply?.links.map((link) => <Link className={styles.catalogLink} href={link.href} key={link.href} onClick={close}>{link.title}<ArrowUpRight size={16} /></Link>)}
          {item.role === "assistant" && item.id !== 0 && voiceAvailable && <button className={styles.readButton} onClick={() => speak(item.text)} title="Прочитать ответ вслух" aria-label="Прочитать ответ вслух"><Volume2 size={15} /></button>}
        </div>)}
        {messages.length === 1 && <div className={styles.suggestions}>{["Авто до 10 тысяч долларов", "Автомат в Минске", "Как разместить объявление?"].map((text) => <button key={text} disabled={busy} onClick={() => send(text)}>{text}<ArrowUpRight size={15} /></button>)}</div>}
        {busy && <p className={styles.pending} role="status">Ищу ответ<span>…</span></p>}
        {error && <div className={styles.error} role="alert"><p>{error}</p>{lastRequest.current && !busy && <button onClick={() => { const request = lastRequest.current; if (request) void send(request.message, request.summary, true); }}>Повторить</button>}<Link href="/cars" onClick={close}>Открыть каталог</Link></div>}
        <div ref={end} />
      </div>
      <div className={styles.actions}>
        {publicPage && <button disabled={busy} onClick={() => send("Кратко перескажи эту публичную страницу по её тексту.", true)}><Volume2 size={16} />Кратко о странице</button>}
        {speaking && <button onClick={stopVoice} aria-label="Остановить озвучивание" title="Остановить озвучивание"><Square size={14} /></button>}
      </div>
      <form className={styles.composer} onSubmit={(event) => { event.preventDefault(); void send(draft); }}>
        <textarea ref={input} value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={1200} rows={2} disabled={busy} placeholder="Какую машину ищем?" aria-label="Сообщение помощнику" onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(draft); } }} />
        <div>{micAvailable && <button type="button" className={`${styles.icon} ${listening ? styles.listening : ""}`} onClick={startMic} disabled={busy} aria-pressed={listening} aria-label={listening ? "Остановить запись" : "Ввести голосом"} title={listening ? "Остановить запись" : "Ввести голосом"}>{listening ? <Square size={16} /> : <Mic size={19} />}</button>}
          <button type="submit" className={styles.send} disabled={busy || !draft.trim()} aria-label="Отправить сообщение" title="Отправить"><ArrowUp size={20} /></button></div>
      </form>
      <p className={styles.privacy}>Не вводите личные данные. {engine === "ai" ? "Сообщения обрабатывает OpenRouter." : "Поиск без подключённой ИИ-модели."}{micAvailable ? " Голосовой ввод — через сервис браузера." : ""}</p>
    </section>}
  </>;
}
