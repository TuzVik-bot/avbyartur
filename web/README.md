# Авторынок BY frontend

Next.js App Router frontend for the private pilot. All pages and HTTP responses carry `noindex` controls. Nginx Basic Auth is the pilot-wide access barrier; application sessions and server roles still protect account and moderation actions.

The browser uses same-origin `/api/v1`. `src/app/api/v1/[...path]/route.ts` forwards requests, cookies, CSRF headers and multipart uploads to `API_INTERNAL_URL`. Set `API_INTERNAL_URL=http://api:8000` in Compose. For local development with FastAPI on port 8000, run the web app with `API_INTERNAL_URL=http://127.0.0.1:8000`.

Install and run locally:

```sh
corepack pnpm install
API_INTERNAL_URL=http://127.0.0.1:8000 corepack pnpm dev
```

`/vehicles/silver-wagon.png` is an original synthetic placeholder used only when an API listing has no photo. The UI labels it as synthetic and does not create demo listings. Real cards use API media URLs.
