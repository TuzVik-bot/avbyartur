import { isIP } from "node:net";
import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const apiOrigin = () => (process.env.API_INTERNAL_URL || process.env.API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const API_PREFIX = "/api/v1/";
const FORWARDED_REQUEST_HEADERS = ["accept", "content-type", "cookie", "x-csrf-token", "x-guest-contact-token", "idempotency-key"];

const invalidPathResponse = () => Response.json({ message: "Неверный адрес запроса." }, { status: 400 });

function decodeSegment(part: string): string | null {
  try {
    return decodeURIComponent(part);
  } catch {
    return null;
  }
}

/** Reject empty, dot and dot-dot segments, including their percent-encoded forms. */
function isSafeSegment(part: string): boolean {
  const decoded = decodeSegment(part);
  if (decoded === null) return false;
  return ![part, decoded].some((value) => value === "" || value === "." || value === "..");
}

/**
 * nginx overwrites X-Real-IP and X-Forwarded-For with $remote_addr, so only a
 * single address is trusted; client-supplied multi-hop chains are never relayed.
 */
function clientIp(request: NextRequest): string | null {
  const candidate = request.headers.get("x-real-ip")?.trim() || request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return candidate && isIP(candidate) ? candidate : null;
}

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (!path.length || !path.every(isSafeSegment)) return invalidPathResponse();
  const suffix = path.map((part) => encodeURIComponent(part)).join("/");
  const incomingUrl = new URL(request.url);
  const target = `${apiOrigin()}${API_PREFIX}${suffix}${incomingUrl.search}`;
  if (!new URL(target).pathname.startsWith(API_PREFIX)) return invalidPathResponse();
  const headers = new Headers();
  for (const key of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  const ip = clientIp(request);
  if (ip) {
    headers.set("x-forwarded-for", ip);
    headers.set("x-real-ip", ip);
  }
  if (path.length === 4 && path[0] === "dealer" && path[1] === "feeds" && path[3] === "api-imports") {
    const feedToken = request.headers.get("x-dealer-feed-token");
    if (feedToken) headers.set("x-dealer-feed-token", feedToken);
    const authorization = request.headers.get("authorization");
    if (authorization && /^Bearer\s/i.test(authorization)) headers.set("authorization", authorization);
  }

  try {
    const method = request.method.toUpperCase();
    const body = method === "GET" || method === "HEAD" ? undefined : request.body;
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      ...(body ? { duplex: "half" } : {})
    } as RequestInit & { duplex?: "half" });

    const responseHeaders = new Headers();
    for (const key of ["content-type", "cache-control", "vary", "www-authenticate", "x-request-id", "x-guest-contact-token"]) {
      const value = upstream.headers.get(key);
      if (value) responseHeaders.set(key, value);
    }
    const setCookies = (upstream.headers as Headers & { getSetCookie?: () => string[] }).getSetCookie?.();
    if (setCookies?.length) {
      for (const cookie of setCookies) responseHeaders.append("set-cookie", cookie);
    } else {
      const cookie = upstream.headers.get("set-cookie");
      if (cookie) responseHeaders.set("set-cookie", cookie);
    }
    const responseBody = upstream.status === 204 || method === "HEAD" ? null : upstream.body;
    return new Response(responseBody, { status: upstream.status, headers: responseHeaders });
  } catch {
    return Response.json({ code: "api_unavailable", message: "Сервис временно недоступен", field_errors: {}, request_id: "" }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
