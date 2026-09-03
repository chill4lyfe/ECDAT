FROM node:22-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --no-frozen-lockfile

FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
ARG NEXT_PUBLIC_ECDAT_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_ECDAT_API_BASE_URL=$NEXT_PUBLIC_ECDAT_API_BASE_URL
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-workspace.yaml ./
COPY apps/web ./apps/web
RUN pnpm --filter @ecdat/web build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN corepack enable
COPY --from=build /app/package.json /app/pnpm-workspace.yaml ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/apps/web ./apps/web
EXPOSE 3000
CMD ["pnpm", "--filter", "@ecdat/web", "start", "--hostname", "0.0.0.0", "--port", "3000"]
