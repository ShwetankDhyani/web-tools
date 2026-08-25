# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS deps
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg ca-certificates \
  && pip3 install --break-system-packages --no-cache-dir yt-dlp \
  && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS builder
WORKDIR /app
COPY . .
RUN npm run build

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=4321
ENV HOSTNAME=0.0.0.0
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg ca-certificates \
  && pip3 install --break-system-packages --no-cache-dir yt-dlp \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --uid 10001 webtools

COPY --from=builder /app/package.json /app/package-lock.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/src ./src

RUN mkdir -p /app/data/prices /app/data/downloads \
  && chown -R webtools:webtools /app

USER webtools
EXPOSE 4321
CMD ["npm", "run", "start"]
