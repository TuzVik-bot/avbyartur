import { NextResponse, type NextRequest } from "next/server";
import { localeAliasResolution } from "@/lib/i18n";

const listingIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function archivedListingHtml() {
  return `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="robots" content="noindex, nofollow" />
    <title>Объявление снято с публикации — Авторынок BY</title>
    <style>
      :root { color-scheme: light; font-family: Inter, Arial, sans-serif; color: #222b3e; background: #f8faff; }
      * { box-sizing: border-box; }
      body { min-height: 100vh; margin: 0; display: grid; place-items: center; padding: 24px; }
      main { width: min(100%, 520px); padding: 32px; border: 1px solid #dfe5ef; border-radius: 8px; background: #fff; }
      .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 28px; color: #2946a5; font-size: 18px; font-weight: 800; }
      .cornflower { width: 32px; height: 32px; padding: 4px; border-radius: 6px; background: #edf2ff; }
      h1 { margin: 0 0 12px; color: #222b3e; font-size: 26px; line-height: 1.2; }
      p { margin: 0 0 24px; color: #69758a; line-height: 1.55; }
      a { min-height: 44px; display: inline-flex; align-items: center; padding: 9px 14px; border-radius: 6px; background: #3f5cc4; color: #fff; font-weight: 700; text-decoration: none; }
      a:focus-visible { outline: 3px solid #365dc5; outline-offset: 2px; }
      a:hover { background: #2946a5; }
      @media (max-width: 480px) { main { padding: 24px; } h1 { font-size: 22px; } }
    </style>
  </head>
  <body>
    <main>
      <div class="brand">
        <svg class="cornflower" viewBox="0 0 24 24" role="img" aria-label="Василёк">
          <g fill="#3470dc">
            <ellipse cx="12" cy="6" rx="2.1" ry="5" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(30 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(60 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(90 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(120 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(150 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(180 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(210 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(240 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(270 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(300 12 12)" />
            <ellipse cx="12" cy="6" rx="2.1" ry="5" transform="rotate(330 12 12)" />
          </g>
          <circle cx="12" cy="12" r="3" fill="#1f4ca6" />
          <circle cx="12" cy="12" r="1" fill="#f1c64f" />
        </svg>
        <span>Авторынок BY</span>
      </div>
      <h1>Объявление снято с публикации</h1>
      <p>Срок размещения этого автомобиля завершён. Посмотрите другие объявления в каталоге.</p>
      <a href="/cars">Перейти к автомобилям</a>
    </main>
  </body>
</html>`;
}

export async function proxy(request: NextRequest) {
  if (request.method !== "GET" && request.method !== "HEAD") return NextResponse.next();

  const url = new URL(request.url);
  const localeAlias = localeAliasResolution(url.pathname, request.url);
  if (localeAlias.kind === "redirect") {
    url.pathname = localeAlias.pathname;
    const response = NextResponse.redirect(url, 308);
    response.headers.set("X-Robots-Tag", "noindex, nofollow, noarchive");
    return response;
  }
  if (localeAlias.kind === "pass") return NextResponse.next();

  const headers = request.headers;
  const isRsc = headers.has("rsc") || headers.has("next-router-state-tree") || headers.has("next-router-prefetch")
    || headers.get("accept")?.includes("text/x-component") || headers.get("purpose") === "prefetch";
  if (isRsc || (request.method === "GET" && !headers.get("accept")?.includes("text/html"))) {
    return NextResponse.next();
  }

  const segments = url.pathname.split("/").filter(Boolean).slice(1);
  const listingId = segments.at(-1);
  if (segments.length < 3 || !listingId || !listingIdPattern.test(listingId)) return NextResponse.next();

  const apiOrigin = (process.env.API_INTERNAL_URL || process.env.API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  try {
    const upstream = await fetch(`${apiOrigin}/api/v1/listings/${encodeURIComponent(listingId)}`, {
      headers: { accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(1000)
    });
    const isGone = upstream.status === 410;
    await upstream.body?.cancel().catch(() => {});
    if (!isGone) return NextResponse.next();

    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      "Content-Type": "text/html; charset=utf-8",
      "X-Robots-Tag": "noindex, nofollow, noarchive"
    });
    return new Response(request.method === "HEAD" ? null : archivedListingHtml(), { status: 410, headers: responseHeaders });
  } catch {
    return NextResponse.next();
  }
}

export const config = { matcher: ["/cars/:path*", "/ru", "/ru/:path*"] };
