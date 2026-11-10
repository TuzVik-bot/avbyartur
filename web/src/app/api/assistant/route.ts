import { createHash } from "node:crypto";
import { answerAssistant, assistantModelEnabled } from "@/lib/assistant-server";
import { isPublicAssistantPage, validateAssistantFilters, type AssistantPage } from "@/lib/assistant";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const HOUR_MS = 3600000;
const DAY_MS = 24 * HOUR_MS;
const PER_IP_REQUESTS_PER_HOUR = 10;
const PER_IP_REQUESTS_PER_DAY = 30;
const GLOBAL_MODEL_CALLS_PER_HOUR = 200;
// Free OpenRouter accounts get about 50 requests a day without credits.
const DEFAULT_DAILY_MODEL_BUDGET = 45;
const MAX_IN_FLIGHT = 3;
const MAX_TRACKED_CLIENTS = 5000;
const PRUNE_TRACKED_CLIENTS_AT = 3000;

type Window = { count: number; until: number };
const buckets = new Map<string, { hour: Window; day: Window }>();
let inFlight = 0;
let modelHour: Window = { count: 0, until: 0 };
let modelDay: Window = { count: 0, until: 0 };
const roll = (window: Window, now: number, length: number): Window => window.until <= now ? { count: 0, until: now + length } : window;
function json(body: unknown, status = 200, retryAfterSeconds = 60) { return Response.json(body, { status, headers: { "Cache-Control": "no-store", ...(status === 429 ? { "Retry-After": String(retryAfterSeconds) } : {}) } }); }
function dailyModelBudget() {
  const configured = Number(process.env.ASSISTANT_DAILY_MODEL_BUDGET);
  return Number.isInteger(configured) && configured >= 0 ? configured : DEFAULT_DAILY_MODEL_BUDGET;
}
// Only real model calls spend the global budget; when it is exhausted the
// assistant answers with the basic engine instead of rejecting the request.
function reserveModelCall() {
  const now = Date.now();
  modelHour = roll(modelHour, now, HOUR_MS);
  modelDay = roll(modelDay, now, DAY_MS);
  if (modelHour.count >= GLOBAL_MODEL_CALLS_PER_HOUR || modelDay.count >= dailyModelBudget()) return false;
  modelHour.count++; modelDay.count++;
  return true;
}
// Returns seconds to wait when the client is over its limit, otherwise counts the request.
function takeClientSlot(identity: string, now: number) {
  if (buckets.size > PRUNE_TRACKED_CLIENTS_AT) for (const [key, value] of buckets) if (value.day.until <= now) buckets.delete(key);
  const current = buckets.get(identity);
  const hour = roll(current?.hour ?? { count: 0, until: 0 }, now, HOUR_MS);
  const day = roll(current?.day ?? { count: 0, until: 0 }, now, DAY_MS);
  if (day.count >= PER_IP_REQUESTS_PER_DAY) return Math.ceil((day.until - now) / 1000);
  if (hour.count >= PER_IP_REQUESTS_PER_HOUR) return Math.ceil((hour.until - now) / 1000);
  buckets.set(identity, { hour: { ...hour, count: hour.count + 1 }, day: { ...day, count: day.count + 1 } });
  return 0;
}
export function GET() { return json({ engine: assistantModelEnabled() ? "ai" : "basic" }); }

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  const configuredOrigin = process.env.SITE_ORIGIN ? new URL(process.env.SITE_ORIGIN).origin : new URL(request.url).origin;
  const localOrigin = process.env.NODE_ENV !== "production" && origin && new URL(origin).host === request.headers.get("host");
  if (origin && origin !== configuredOrigin && origin !== new URL(request.url).origin && !localOrigin) return json({ message: "Запрос разрешён только с сайта." }, 403);
  if (request.headers.get("sec-fetch-site") === "cross-site") return json({ message: "Запрос разрешён только с сайта." }, 403);
  if (!request.headers.get("content-type")?.includes("application/json")) return json({ message: "Ожидается JSON." }, 415);
  const now = Date.now();
  const identity = createHash("sha256").update(request.headers.get("x-real-ip") || request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "shared").digest("hex");
  if (inFlight >= MAX_IN_FLIGHT || (buckets.size > MAX_TRACKED_CLIENTS && !buckets.has(identity))) return json({ message: "Помощник занят. Попробуйте немного позже." }, 429);
  const waitSeconds = takeClientSlot(identity, now);
  if (waitSeconds > 0) return json({ message: "Помощник занят. Попробуйте немного позже." }, 429, waitSeconds);
  let body: Record<string, unknown>;
  try {
    // Bound bytes even when Content-Length is absent or forged.
    const reader = request.body?.getReader();
    if (!reader) return json({ message: "Введите сообщение." }, 400);
    const chunks: Uint8Array[] = []; let size = 0;
    for (;;) { const { done, value } = await reader.read(); if (done) break; size += value.byteLength; if (size > 20000) { await reader.cancel(); return json({ message: "Сообщение слишком длинное." }, 413); } chunks.push(value); }
    body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (!body || typeof body !== "object" || Array.isArray(body)) return json({ message: "Неверный запрос." }, 400);
  } catch { return json({ message: "Неверный запрос." }, 400); }
  if (typeof body.message !== "string" || !body.message.trim() || body.message.length > 1200) return json({ message: "Введите сообщение до 1200 символов." }, 400);
  const history = Array.isArray(body.history) ? body.history.slice(-6).filter((entry) => entry && (entry.role === "user" || entry.role === "assistant") && typeof entry.content === "string").map((entry) => ({ role: entry.role, content: entry.content.slice(0, 1200) })) : [];
  let page: AssistantPage | undefined;
  if (body.page && typeof body.page === "object") {
    const p = body.page as Record<string, unknown>;
    if (typeof p.path === "string" && isPublicAssistantPage(p.path) && typeof p.title === "string" && typeof p.text === "string") page = { path: p.path, title: p.title.slice(0, 160), text: p.text.slice(0, 6000) };
  }
  inFlight++;
  const listingIds = Array.isArray(body.listingIds) ? body.listingIds.filter((id) => typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)).slice(0, 3) : [];
  try { return json(await answerAssistant({ message: body.message.trim(), filters: validateAssistantFilters(body.filters), history, page, listingIds, reserveModelCall, action: body.action === "summary" ? "summary" : undefined })); }
  catch (error) {
    const code = error instanceof Error ? error.message : "";
    const message = code === "search_unavailable" ? "Поиск по цене сейчас недоступен: не удалось получить свежий курс валют. Попробуйте позже или откройте каталог." : code.startsWith("model_") ? "ИИ временно не ответил. Попробуйте ещё раз чуть позже; каталог сайта доступен." : "Не удалось получить данные сайта. Попробуйте ещё раз позже.";
    return json({ message }, 503);
  } finally { inFlight--; }
}
