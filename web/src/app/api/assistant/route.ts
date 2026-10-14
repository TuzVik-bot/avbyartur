import { createHash } from "node:crypto";
import { answerAssistant, assistantModelEnabled } from "@/lib/assistant-server";
import { isPublicAssistantPage, validateAssistantFilters, type AssistantPage } from "@/lib/assistant";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const buckets = new Map<string, { count: number; until: number }>();
let inFlight = 0;
let hour = { count: 0, until: 0 };
function json(body: unknown, status = 200) { return Response.json(body, { status, headers: { "Cache-Control": "no-store", ...(status === 429 ? { "Retry-After": "60" } : {}) } }); }
export function GET() { return json({ engine: assistantModelEnabled() ? "ai" : "basic" }); }

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  const configuredOrigin = process.env.SITE_ORIGIN ? new URL(process.env.SITE_ORIGIN).origin : new URL(request.url).origin;
  const localOrigin = process.env.NODE_ENV !== "production" && origin && new URL(origin).host === request.headers.get("host");
  if (origin && origin !== configuredOrigin && origin !== new URL(request.url).origin && !localOrigin) return json({ message: "Запрос разрешён только с сайта." }, 403);
  if (request.headers.get("sec-fetch-site") === "cross-site") return json({ message: "Запрос разрешён только с сайта." }, 403);
  if (!request.headers.get("content-type")?.includes("application/json")) return json({ message: "Ожидается JSON." }, 415);
  const now = Date.now();
  if (hour.until <= now) hour = { count: 0, until: now + 3600000 };
  const identity = createHash("sha256").update(request.headers.get("x-real-ip") || request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "shared").digest("hex");
  if (buckets.size > 3000) for (const [key, value] of buckets) if (value.until <= now) buckets.delete(key);
  const bucket = buckets.get(identity);
  if ((bucket && bucket.until > now && bucket.count >= 20) || hour.count >= 200 || inFlight >= 3 || buckets.size > 5000) return json({ message: "Помощник занят. Попробуйте немного позже." }, 429);
  if (!bucket || bucket.until <= now) buckets.set(identity, { count: 1, until: now + 300000 }); else bucket.count++;
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
  inFlight++; hour.count++;
  try { return json(await answerAssistant({ message: body.message.trim(), filters: validateAssistantFilters(body.filters), history, page, action: body.action === "summary" ? "summary" : undefined })); }
  catch (error) {
    const code = error instanceof Error ? error.message : "";
    const message = code === "search_unavailable" ? "Поиск по цене сейчас недоступен: не удалось получить свежий курс валют. Попробуйте позже или откройте каталог." : code.startsWith("model_") ? "ИИ временно не ответил. Попробуйте ещё раз чуть позже; каталог сайта доступен." : "Не удалось получить данные сайта. Попробуйте ещё раз позже.";
    return json({ message }, 503);
  } finally { inFlight--; }
}
