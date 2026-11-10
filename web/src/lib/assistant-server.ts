import { internalApiBase } from "@/lib/api";
import { assistantFilterLabels, parseAssistantSearch, type AssistantFilters, type AssistantLink, type AssistantPage, type AssistantReply } from "@/lib/assistant";
import { assistantModelEnabled, BASIC_MODE_NOTICE, recordModelOutcome, tryModelPlan } from "@/lib/assistant-model";
import { assistantTopics, redactContacts, type Catalog, type HistoryEntry } from "@/lib/assistant-prompt";
import { searchUrl } from "@/lib/search-state";
import { formatMileage, formatMoney, listingHref, vehicleLabel } from "@/lib/format";
import type { CatalogItem, Listing, ListingSummary } from "@/lib/types";

export { assistantModelEnabled } from "@/lib/assistant-model";

const CATALOG_CACHE_MS = 300000;
const API_TIMEOUT_MS = 8000;
const MAX_COMPARED_LISTINGS = 3;
const SEARCH_PAGE_SIZE = 4;
const LISTING_DESCRIPTION_CHARS = 4000;
const SUMMARY_SENTENCES = 5;
const SUMMARY_FALLBACK_CHARS = 1400;
const LISTING_PAGE = /^\/cars\/(?:[^/]+\/){0,2}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

let catalogCache: { value: Catalog; until: number } | undefined;
export async function publicAssistantApi<T>(path: string): Promise<T> {
  const response = await fetch(`${internalApiBase()}/${path}`, { cache: "no-store", signal: AbortSignal.timeout(API_TIMEOUT_MS) });
  if (!response.ok) throw new Error(response.status === 422 ? "search_unavailable" : "catalog_unavailable");
  return response.json() as Promise<T>;
}
async function catalogs(): Promise<Catalog> {
  if (catalogCache && Date.now() < catalogCache.until) return catalogCache.value;
  const [makes, regions] = await Promise.all([publicAssistantApi<{ items: CatalogItem[] }>("catalog/makes?category_code=cars"), publicAssistantApi<{ items: CatalogItem[] }>("locations/regions")]);
  const cities = await Promise.all(regions.items.map((region) => publicAssistantApi<{ items: CatalogItem[] }>(`locations/cities?region_id=${encodeURIComponent(region.id)}`)));
  const value = { makes: makes.items, models: [], cities: cities.flatMap((entry) => entry.items) };
  catalogCache = { value, until: Date.now() + CATALOG_CACHE_MS };
  return { ...value };
}
async function modelsOfMake(makeId: string) {
  return (await publicAssistantApi<{ items: CatalogItem[] }>(`catalog/models?make_id=${encodeURIComponent(makeId)}&category_code=cars`)).items;
}

// Each alternative changes one condition and is checked against public inventory.
async function nearbySearches(filters: AssistantFilters): Promise<AssistantLink[]> {
  const candidates: { filters: AssistantFilters; title: string }[] = [];
  if (filters.price_max && filters.currency) {
    const ceiling = Number(filters.price_max);
    // Keep the increment modest even for small budgets, in the requested currency.
    const increment = Math.min(1000, Math.max(1, Math.round(ceiling * 0.1)));
    if (ceiling + increment <= 999999999) candidates.push({
      filters: { ...filters, price_min: (ceiling + 0.01).toFixed(2), price_max: String(ceiling + increment), sort: "price_asc" },
      title: `До ${increment.toLocaleString("ru")} ${filters.currency} дороже бюджета`
    });
  }
  if (filters.year_min && Number(filters.year_min) > 1886) candidates.push({
    filters: { ...filters, year_min: String(Number(filters.year_min) - 1), year_max: String(Number(filters.year_min) - 1) },
    title: `На год старше — только ${Number(filters.year_min) - 1} г.`
  });
  if (filters.city_id) {
    const nearby = { ...filters };
    delete nearby.city_id;
    candidates.push({ filters: nearby, title: "Те же условия — по всей Беларуси" });
  }
  const results = await Promise.all(candidates.map(async (candidate) => {
    try {
      const params = new URLSearchParams({ ...candidate.filters, page_size: "1" });
      const found = await publicAssistantApi<{ pagination: { total: number } }>(`listings?${params}`);
      return found.pagination.total > 0 ? { title: `${candidate.title} · ${found.pagination.total} объявл.`, href: searchUrl(candidate.filters) } : null;
    } catch { return null; }
  }));
  return results.filter((result): result is AssistantLink => result !== null);
}

// Drops catalog ids the model invented and falls back to the parser's values.
async function reconcileCatalogIds(filters: AssistantFilters, parsed: AssistantFilters, catalog: Catalog) {
  const next: AssistantFilters = { ...filters };
  let dropped = false;
  let unknownMake = false;
  const known = (items: CatalogItem[], id?: string) => Boolean(id && items.some((item) => item.id === id));
  if (next.make_id && !known(catalog.makes, next.make_id)) {
    dropped = true;
    unknownMake = !parsed.make_id;
    if (parsed.make_id) next.make_id = parsed.make_id; else delete next.make_id;
    if (parsed.model_id) next.model_id = parsed.model_id; else delete next.model_id;
  }
  if (next.city_id && !known(catalog.cities, next.city_id)) {
    dropped = true;
    if (parsed.city_id) next.city_id = parsed.city_id; else delete next.city_id;
  }
  if (next.make_id && next.make_id !== parsed.make_id) catalog.models = await modelsOfMake(next.make_id).catch(() => []);
  if (next.model_id && !known(catalog.models, next.model_id)) {
    dropped = true;
    if (parsed.model_id && parsed.make_id === next.make_id) next.model_id = parsed.model_id; else delete next.model_id;
  }
  return { filters: next, dropped, unknownMake };
}

// Combines the model plan with the deterministic parser. Currency is never taken
// from the model alone: it must come from the message or the active filters.
function mergePlanFilters(plan: AssistantFilters, parsed: AssistantFilters, previous: AssistantFilters, relativeApplied: boolean) {
  // The model may read a relative amount as an absolute budget, so the parser's
  // state wins and keys the parser dropped stay dropped.
  const merged: AssistantFilters = relativeApplied ? { ...plan, ...parsed } : { ...parsed, ...plan };
  if (relativeApplied) for (const key of Object.keys(previous)) if (!(key in parsed)) delete (merged as Record<string, string>)[key];
  if (parsed.currency) merged.currency = parsed.currency; else delete merged.currency;
  return merged;
}

async function fetchListings<T>(ids: string[], pick: (listing: Listing) => T) {
  const found = await Promise.all(ids.slice(0, MAX_COMPARED_LISTINGS).map(async (id) => {
    try { return pick((await publicAssistantApi<{ listing: Listing }>(`listings/${encodeURIComponent(id)}`)).listing); }
    catch { return null; }
  }));
  return found.filter((item): item is NonNullable<typeof item> => item !== null);
}
const listingFacts = (listing: ListingSummary) => ({ title: listing.title, year: listing.year, mileage_km: listing.mileage_km, fuel: listing.fuel, transmission: listing.transmission, drive: listing.drive, price: listing.price, city: listing.city?.name, damaged: listing.damaged, parts_only: listing.parts_only });

function listingPageText(listing: Listing) {
  const specs = [
    ["Цена", formatMoney(listing.price)], ["Год", listing.year ? String(listing.year) : ""], ["Пробег", formatMileage(listing.mileage_km)],
    ["Топливо", listing.fuel ? vehicleLabel(listing.fuel) : ""], ["Коробка", listing.transmission ? vehicleLabel(listing.transmission) : ""],
    ["Привод", listing.drive ? vehicleLabel(listing.drive) : ""], ["Кузов", listing.body_type ? vehicleLabel(listing.body_type) : ""],
    ["Объём двигателя, л", listing.engine_volume_l || ""], ["Мощность, л. с.", listing.power_hp ? String(listing.power_hp) : ""],
    ["Цвет", listing.color || ""], ["Город", listing.city?.name || listing.manual_city || ""],
    ["Повреждения", listing.damaged ? "указаны" : ""], ["Только на запчасти", listing.parts_only ? "да" : ""]
  ].filter(([, value]) => value).map(([label, value]) => `${label}: ${value}`);
  const description = redactContacts((listing.description || "").slice(0, LISTING_DESCRIPTION_CHARS));
  return `${specs.join("\n")}${description ? `\n\nОписание продавца:\n${description}` : ""}`;
}

// Listing pages are summarised from the public API by id, never from text the browser sent.
async function resolvePage(page?: AssistantPage): Promise<AssistantPage | undefined> {
  const listingId = page?.path.match(LISTING_PAGE)?.[1];
  if (!page || !listingId) return page;
  try {
    const { listing } = await publicAssistantApi<{ listing: Listing }>(`listings/${encodeURIComponent(listingId)}`);
    return { path: page.path, title: listing.title, text: listingPageText(listing) };
  } catch { return undefined; }
}

type RelativeIncrease = NonNullable<ReturnType<typeof parseAssistantSearch>["relativeBudgetIncrease"]>;
function relativeIncreaseText(relativeIncrease: RelativeIncrease, filters: AssistantFilters) {
  const currencyName = (currency?: string) => currency === "USD" ? "долларах США (USD)" : currency === "BYN" ? "белорусских рублях (BYN)" : "";
  if (relativeIncrease.currencyConflict) return `В исходном поиске бюджет указан в ${currencyName(filters.currency)}, а прибавка — в ${currencyName(relativeIncrease.currency)}. Я сохранил исходную валюту. Укажите прибавку в валюте бюджета или выберите новый бюджет.`;
  if (!filters.price_max) return "Чтобы показать варианты дороже, нужен исходный максимальный бюджет. Например: «до 10 000 BYN, а затем на 1 000 дороже».";
  if (!filters.currency) return "В какой валюте увеличить исходный бюджет — USD или BYN?";
  return "Не удалось рассчитать новый предел бюджета. Укажите желаемую максимальную цену и валюту.";
}

async function comparison(listingIds: string[]): Promise<Pick<AssistantReply, "text" | "links">> {
  const details = await fetchListings(listingIds, (listing) => listing);
  if (!details.length) return { text: "Не удалось получить актуальные данные этих объявлений. Выполните поиск ещё раз.", links: [] };
  const rows = details.map((listing, index) => `${index + 1}. ${listing.title}\n${formatMoney(listing.price)}; ${listing.year || "год не указан"}; ${formatMileage(listing.mileage_km)}; ${vehicleLabel(listing.fuel)}; ${vehicleLabel(listing.transmission)}; ${vehicleLabel(listing.drive)} привод.${listing.damaged ? " Указаны повреждения." : ""}`);
  return {
    text: `Сравнение по актуальным данным объявлений:\n\n${rows.join("\n\n")}\n\nСостояние и историю по этим характеристикам подтвердить нельзя. Проверьте автомобиль и документы перед покупкой.`,
    links: details.map((listing, index) => ({ title: `${index + 1}. Открыть объявление`, href: listingHref(listing) }))
  };
}

function pageSummaryText(page: AssistantPage, modelText: string) {
  if (modelText) return redactContacts(modelText);
  const sentences = page.text.split(/(?<=[.!?])\s+|\n+/).map((s) => s.trim()).filter((s) => s.length > 40 && !/реклам|ваш бренд|синтетическое фото/i.test(s));
  const extract = redactContacts(sentences.slice(0, SUMMARY_SENTENCES).join(" ").slice(0, SUMMARY_FALLBACK_CHARS));
  return `${page.title}\n\n${extract || "На странице мало описательного текста. Здесь можно просмотреть опубликованные сведения и перейти к нужному разделу."}`;
}

async function searchReply(filters: AssistantFilters, budgetIncreased: boolean): Promise<Pick<AssistantReply, "listings" | "total" | "searchHref" | "links" | "text">> {
  const params = new URLSearchParams({ ...filters, page_size: String(SEARCH_PAGE_SIZE) });
  const found = await publicAssistantApi<{ items: ListingSummary[]; pagination: { total: number } }>(`listings?${params}`);
  const total = found.pagination.total;
  const alternatives = total === 0 ? await nearbySearches(filters) : [];
  const budgetChangeNotice = budgetIncreased
    ? `Бюджет увеличен: теперь от ${Number(filters.price_min).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} до ${Number(filters.price_max).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ${filters.currency}. `
    : "";
  const resultText = total ? `По вашим условиям найдено объявлений: ${total}. ${total > SEARCH_PAGE_SIZE ? "Показываю первые четыре." : "Вот подходящие варианты."}` : alternatives.length
    ? "По этим условиям объявлений сейчас нет. Похоже на ваш запрос: ниже реальные объявления по близким условиям. В каждой ссылке указано, что изменено. Выберите ссылку ниже, чтобы открыть подборку в каталоге. Исходные условия поиска сохранены."
    : "По этим условиям опубликованных объявлений сейчас нет. Можно увеличить бюджет, изменить год или убрать город — какие условия изменить?";
  return { listings: found.items, total, searchHref: searchUrl(filters), links: alternatives, text: `${budgetChangeNotice}${resultText}` };
}

function searchProblem(filters: AssistantFilters) {
  if ((filters.price_min || filters.price_max || filters.sort?.startsWith("price_")) && !filters.currency) return "Бюджет в долларах (USD) или белорусских рублях (BYN)?";
  if (filters.price_min && filters.price_max && Number(filters.price_min) > Number(filters.price_max)) return "Минимальная цена выше максимальной. Уточните диапазон бюджета.";
  if (filters.year_min && filters.year_max && Number(filters.year_min) > Number(filters.year_max)) return "Начальный год больше конечного. Уточните диапазон лет.";
  return "";
}

export type AssistantInput = {
  message: string; filters: AssistantFilters; history: HistoryEntry[]; page?: AssistantPage; action?: string; listingIds?: string[];
  // Reserves one model call against the global budget; false means answer in basic mode.
  reserveModelCall?: () => boolean;
};
type ParsedSearch = ReturnType<typeof parseAssistantSearch>;
type ModelStep = { filters: AssistantFilters; intent: string; modelText: string; engine: AssistantReply["engine"]; notice?: string; unknownMake?: boolean };

// Asks the model for a plan; every model failure leaves the parser's result in place.
async function applyModel(input: AssistantInput, parsed: ParsedSearch, catalog: Catalog, page: AssistantPage | undefined): Promise<ModelStep> {
  const isSummary = input.action === "summary";
  const basic: ModelStep = { filters: parsed.filters, intent: isSummary ? "summary" : "", modelText: "", engine: "basic" };
  if (!assistantModelEnabled()) return basic;
  const wantsFacts = /сравн|объявлен|характерист|лучш|вариант/i.test(input.message) && input.listingIds?.length;
  const listings = wantsFacts ? await fetchListings(input.listingIds ?? [], listingFacts) : [];
  const plan = await tryModelPlan(input.reserveModelCall, { message: input.message, filters: parsed.filters, catalog, history: input.history, page, listings });
  if (!plan) return { ...basic, notice: BASIC_MODE_NOTICE };
  const relativeApplied = Boolean(parsed.relativeBudgetIncrease?.applied);
  const intent = isSummary ? "summary" : relativeApplied ? "search" : plan.intent;
  const step: ModelStep = { ...basic, engine: "ai", intent, modelText: plan.text };
  if (intent !== "search" && intent !== "answer") { recordModelOutcome("ok"); return step; }
  const reconciled = await reconcileCatalogIds(mergePlanFilters(plan.filters, parsed.filters, input.filters, relativeApplied), parsed.filters, catalog);
  recordModelOutcome(reconciled.dropped ? "unknown_id" : "ok");
  return { ...step, filters: reconciled.filters, unknownMake: reconciled.unknownMake };
}

async function parseWithModels(input: AssistantInput, catalog: Catalog) {
  const parsed = parseAssistantSearch(input.message, input.filters, catalog);
  if (!parsed.filters.make_id) return parsed;
  catalog.models = await modelsOfMake(parsed.filters.make_id);
  return parseAssistantSearch(input.message, input.filters, catalog);
}

export async function answerAssistant(input: AssistantInput): Promise<AssistantReply> {
  const catalog = { ...await catalogs() };
  const parsed = await parseWithModels(input, catalog);
  type ReplyBase = Pick<ModelStep, "filters" | "engine" | "notice">;
  const reply = (step: ReplyBase, rest: Pick<AssistantReply, "text"> & Partial<AssistantReply>): AssistantReply =>
    ({ filters: step.filters, labels: assistantFilterLabels(step.filters, catalog), listings: [], links: [], engine: step.engine, ...(step.notice ? { notice: step.notice } : {}), ...rest });
  const basic: ReplyBase = { filters: parsed.filters, engine: "basic" };
  const relativeIncrease = parsed.relativeBudgetIncrease;
  if (relativeIncrease && !relativeIncrease.applied) return reply(basic, { text: relativeIncreaseText(relativeIncrease, parsed.filters) });
  if (/сравн/i.test(input.message) && input.listingIds?.length) return reply({ ...basic, engine: assistantModelEnabled() ? "ai" : "basic" }, await comparison(input.listingIds));
  const page = await resolvePage(input.page);
  if (input.action === "summary" && !page) return reply(basic, { text: "Пересказ доступен на публичных страницах с текстом. Откройте объявление, помощь или страницу услуги." });
  const step = await applyModel(input, parsed, catalog, page);
  if (step.unknownMake) return reply(step, { text: "Такой марки нет в каталоге сайта. Проверьте написание или выберите марку из списка.", links: [{ title: "Все марки", href: "/makes" }] });
  const { intent, modelText, filters } = step;
  if (intent === "summary" && page) return reply(step, { labels: [], text: pageSummaryText(page, modelText), links: [{ title: "Текущая страница", href: page.path }] });
  if (/регистр|создать аккаунт|войти|вход|парол/i.test(input.message) && intent !== "search") {
    const capabilities = await publicAssistantApi<{ email_registration?: boolean; password_recovery?: boolean }>("auth/capabilities");
    return reply(step, { text: capabilities.email_registration ? "Регистрация по email доступна на странице входа: выберите «Создать аккаунт» и заполните форму. Условия и согласия указаны в ней." : "Откройте страницу входа: доступные способы авторизации указаны там. Самостоятельная регистрация по email сейчас отключена.", links: [{ title: "Войти / создать аккаунт", href: "/login?next=%2Fsell" }] });
  }
  const topic = assistantTopics.find(({ pattern }) => pattern.test(input.message));
  if (topic && intent !== "search") return reply(step, { text: modelText || topic.text, links: topic.links });
  if (intent === "answer") return reply(step, { text: modelText || "Уточните, что вы хотите узнать по данным сайта." });
  const searchIntent = intent === "search" || parsed.changed || /найд|подбер|покажи|ищу|тачк|машин|автомоб|вариант|дешев|бюджет|доллар|рубл/i.test(input.message);
  if (!searchIntent) return reply(step, { text: modelText || "Могу подобрать объявления по бюджету, марке, году, городу и другим параметрам. Также помогу найти нужный раздел сайта. Что вас интересует?", links: [{ title: "Помощь", href: "/help" }] });
  const problem = searchProblem(filters);
  if (problem) return reply(step, { text: problem });
  return reply(step, await searchReply(filters, Boolean(relativeIncrease?.applied)));
}
