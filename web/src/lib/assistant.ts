import type { CatalogItem, ListingSearch, ListingSummary } from "@/lib/types";

export type AssistantFilters = Pick<ListingSearch, "category_code" | "make_id" | "model_id" | "price_min" | "price_max" | "currency" | "year_min" | "year_max" | "mileage_max" | "fuel" | "transmission" | "drive" | "body_type" | "city_id" | "has_photos" | "damaged" | "parts_only" | "sort">;
export type AssistantLink = { title: string; href: string };
export type AssistantReply = {
  text: string;
  filters: AssistantFilters;
  labels: string[];
  listings: ListingSummary[];
  total?: number;
  searchHref?: string;
  links: AssistantLink[];
  engine: "basic" | "ai";
};
export type AssistantPage = { path: string; title: string; text: string };

const enumFields: Record<string, readonly string[]> = {
  category_code: ["cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires"],
  currency: ["USD", "BYN"], fuel: ["petrol", "diesel", "hybrid", "electric", "lpg"],
  transmission: ["automatic", "manual", "robot", "cvt"], drive: ["front", "rear", "all"],
  body_type: ["sedan", "wagon", "hatchback", "suv", "coupe", "minivan", "pickup", "convertible"],
  has_photos: ["true", "false"], damaged: ["true", "false"], parts_only: ["true", "false"],
  sort: ["newest", "price_asc", "price_desc", "year_desc", "mileage_asc"]
};
export function validateAssistantFilters(value: unknown): AssistantFilters {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, string> = {};
  for (const [key, raw] of Object.entries(value)) {
    const v = typeof raw === "number" ? String(raw) : raw;
    if (typeof v !== "string") continue;
    if (enumFields[key]?.includes(v)) result[key] = v;
    else if (["make_id", "model_id", "city_id"].includes(key) && /^[\w-]{1,80}$/.test(v)) result[key] = v;
    else if (["price_min", "price_max", "mileage_max"].includes(key) && /^\d{1,9}(\.\d{1,2})?$/.test(v) && Number(v) > 0) result[key] = v;
    else if (["year_min", "year_max"].includes(key) && /^\d{4}$/.test(v) && Number(v) >= 1886 && Number(v) <= new Date().getFullYear() + 1) result[key] = v;
  }
  return result as AssistantFilters;
}

export function isPublicAssistantPage(path: string) {
  if (path.split("/").some((part) => part === "." || part === "..") || /%2e|%2f|%5c/i.test(path)) return false;
  return /^\/(?:cars(?:\/[\w%.-]+){0,3}|help|about|support|services|useful-information|vin-check|sale-contract|customs-calculator|currency-converter|makes|dealers(?:\/[\w%.-]+)?|terms-of-use|privacy-policy|registration-terms|registration-privacy)?$/.test(path);
}

const normalize = (text: string) => text.toLocaleLowerCase("ru").replace(/ё/g, "е");
function catalogMatch(text: string, items: CatalogItem[]) {
  const haystack = ` ${normalize(text)} `;
  return items.filter((item) => [item.name, item.slug, ...(item.aliases || [])].some((name) => {
    const needle = normalize(name);
    const index = haystack.indexOf(needle);
    return needle.length >= 2 && index >= 0 && !/[\p{L}\p{N}]/u.test(haystack[index - 1] || "") && !/[\p{L}\p{N}]/u.test(haystack[index + needle.length] || "");
  })).sort((a, b) => b.name.length - a.name.length)[0];
}
function amount(raw: string, unit?: string) {
  const n = Number(raw.replace(/\s/g, "").replace(",", "."));
  return String(n * (unit ? 1000 : 1));
}

export function parseAssistantSearch(message: string, previous: AssistantFilters, catalog: { makes: CatalogItem[]; models: CatalogItem[]; cities: CatalogItem[] }) {
  const text = normalize(message);
  const reset = /заново|сброс|новый поиск/.test(text);
  const filters: AssistantFilters = reset ? { category_code: "cars" } : { category_code: "cars", ...previous };
  const currency = /\$|usd|доллар|бакс/.test(text) ? "USD" : /byn|рубл|белорус|бел\.?\s*руб/.test(text) ? "BYN" : undefined;
  if (currency) filters.currency = currency;
  const budget = text.match(/(?:бюджет(?:ом)?\s*(?:до)?|цена\s*до|стоимост\S*\s*до|до|не дороже|максимум)\s*(\d{1,3}(?:\s\d{3})+|\d+(?:[.,]\d+)?)\s*(тыс\S*|k\b|к\b)?/);
  if (budget && !/^(?:\s*(?:года|год|г\b|км|километр))/.test(text.slice((budget.index || 0) + budget[0].length))) {
    const n = Number(amount(budget[1], budget[2]));
    if (!(n >= 1886 && n <= new Date().getFullYear() + 1 && /год|старше|младше/.test(text))) filters.price_max = String(n);
  }
  const priceRange = text.match(/от\s*(\d+(?:[.,]\d+)?)\s*(тыс\S*)?\s*до\s*(\d+(?:[.,]\d+)?)\s*(тыс\S*)?/);
  if (priceRange && !/год|пробег/.test(text)) {
    filters.price_min = amount(priceRange[1], priceRange[2] || priceRange[4]);
    filters.price_max = amount(priceRange[3], priceRange[4]);
  }
  const yearMin = text.match(/(?:не старше|от|после|с)\s*((?:19|20)\d{2})(?:\s*г\S*)?/);
  const yearMax = text.match(/(?:до|не новее)\s*((?:19|20)\d{2})\s*(?:года|год|г\b)/);
  if (yearMin) filters.year_min = yearMin[1];
  if (yearMax) filters.year_max = yearMax[1];
  const mileage = text.match(/пробег\S*\s*(?:до|не больше)?\s*(\d+(?:\s\d{3})?)\s*(тыс\S*)?/);
  if (mileage) filters.mileage_max = amount(mileage[1], mileage[2]);
  const values: [keyof AssistantFilters, RegExp, string][] = [
    ["transmission", /автомат|акпп/, "automatic"], ["transmission", /механик|мкпп/, "manual"], ["transmission", /вариатор/, "cvt"], ["transmission", /робот/, "robot"],
    ["fuel", /дизел/, "diesel"], ["fuel", /бензин/, "petrol"], ["fuel", /гибрид/, "hybrid"], ["fuel", /электр/, "electric"],
    ["drive", /полн\S*\s*привод|4[хx×]4/, "all"], ["drive", /передн\S*\s*привод/, "front"], ["drive", /задн\S*\s*привод/, "rear"],
    ["body_type", /универсал/, "wagon"], ["body_type", /седан/, "sedan"], ["body_type", /х[еэ]тчб[еэ]к/, "hatchback"], ["body_type", /кроссовер|внедорожник/, "suv"],
    ["has_photos", /с фото/, "true"], ["damaged", /не бит|без поврежден/, "false"], ["sort", /дешев\S*\s*(?:сначала|первыми)|сначала дешев/, "price_asc"]
  ];
  for (const [key, pattern, value] of values) if (pattern.test(text)) (filters as Record<string, string>)[key] = value;
  if (/любая коробка|любой коробк/.test(text)) delete filters.transmission;
  if (/любое топливо|любой мотор/.test(text)) delete filters.fuel;
  if (/любой город|вся беларус|по всей беларус/.test(text)) delete filters.city_id;
  if (/без ограничения (?:цены|бюджета)|любой бюджет/.test(text)) { delete filters.price_min; delete filters.price_max; }
  const make = catalogMatch(text, catalog.makes);
  if (make && make.id !== filters.make_id) { filters.make_id = make.id; delete filters.model_id; }
  const model = catalogMatch(text, catalog.models.filter((item) => !filters.make_id || item.make_id === filters.make_id));
  if (model) { filters.model_id = model.id; if (model.make_id) filters.make_id = model.make_id; }
  const city = catalogMatch(text.replace(/минске/g, "минск").replace(/бресте/g, "брест").replace(/гродно/g, "гродно").replace(/витебске/g, "витебск").replace(/гомеле/g, "гомель").replace(/могилеве/g, "могилев"), catalog.cities);
  if (city) filters.city_id = city.id;
  const validated = validateAssistantFilters(filters);
  const changed = JSON.stringify(validated) !== JSON.stringify(validateAssistantFilters({ category_code: "cars", ...previous }));
  return { filters: validated, changed, needsCurrency: Boolean((validated.price_min || validated.price_max || validated.sort?.startsWith("price_")) && !validated.currency), make };
}

export function assistantFilterLabels(filters: AssistantFilters, catalog: { makes: CatalogItem[]; models: CatalogItem[]; cities: CatalogItem[] }) {
  const labels: string[] = [];
  for (const [key, items] of [["make_id", catalog.makes], ["model_id", catalog.models], ["city_id", catalog.cities]] as const) {
    const item = items.find((entry) => entry.id === filters[key]);
    if (item) labels.push(item.name);
  }
  if (filters.price_min) labels.push(`От ${Number(filters.price_min).toLocaleString("ru")} ${filters.currency || ""}`.trim());
  if (filters.price_max) labels.push(`До ${Number(filters.price_max).toLocaleString("ru")} ${filters.currency || ""}`.trim());
  if (filters.year_min) labels.push(`От ${filters.year_min} г.`);
  if (filters.year_max) labels.push(`До ${filters.year_max} г.`);
  if (filters.mileage_max) labels.push(`Пробег до ${Number(filters.mileage_max).toLocaleString("ru")} км`);
  const names: Record<string, string> = { automatic: "Автомат", manual: "Механика", robot: "Робот", cvt: "Вариатор", petrol: "Бензин", diesel: "Дизель", electric: "Электро", hybrid: "Гибрид", all: "Полный привод", front: "Передний привод", rear: "Задний привод", wagon: "Универсал", sedan: "Седан", hatchback: "Хетчбэк", suv: "Кроссовер / внедорожник" };
  for (const key of ["transmission", "fuel", "drive", "body_type"] as const) if (filters[key]) labels.push(names[filters[key]!] || filters[key]!);
  if (filters.has_photos === "true") labels.push("С фото");
  if (filters.damaged === "false") labels.push("Без повреждений");
  return labels;
}
