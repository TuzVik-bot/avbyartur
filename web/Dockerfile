# The deployed Alpine/musl runtime repeatedly segfaulted in ld-musl on the VPS
# (exit 139); keep build and runtime on the pinned glibc-based Node image.
FROM node:22.23.3-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate

FROM base AS dependencies
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
COPY --from=dependencies /app/node_modules ./node_modules
COPY web/ .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:22.23.3-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --chown=node:node --from=builder /app/.next/standalone ./
COPY --chown=node:node --from=builder /app/.next/static ./.next/static
COPY --chown=node:node --from=builder /app/public ./public
RUN mkdir -p /app/.next/cache && chown node:node /app /app/.next /app/.next/cache
USER node
EXPOSE 3000
CMD ["node", "server.js"]
