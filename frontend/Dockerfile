# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS base

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 cortexa \
    && useradd --system --uid 10001 --gid cortexa --create-home --home-dir /home/cortexa --shell /usr/sbin/nologin cortexa \
    && mkdir -p /app /home/cortexa /opt/frontend-deps /opt/frontend-deps/node_modules \
    && chown -R cortexa:cortexa /app /home/cortexa /opt/frontend-deps

COPY package.json /opt/frontend-deps/package.json
WORKDIR /opt/frontend-deps
RUN npm install

WORKDIR /app
COPY --chown=cortexa:cortexa . .

RUN cat <<'EOF' > /usr/local/bin/frontend-entrypoint.sh
#!/bin/sh
set -eu

mkdir -p /app/node_modules /app/.next

if [ ! -f /app/node_modules/.cortexa_deps_ready ]; then
  rm -rf /app/node_modules/*
  cp -R /opt/frontend-deps/node_modules/. /app/node_modules/
  touch /app/node_modules/.cortexa_deps_ready
fi

rm -rf /app/.next/*

chown -R cortexa:cortexa /app /home/cortexa /app/node_modules /app/.next
exec gosu cortexa "$@"
EOF

RUN chmod +x /usr/local/bin/frontend-entrypoint.sh

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:3000/ || exit 1

# Development command for local Compose with bind-mounted source and isolated
# container-owned node_modules/.next volumes. Production multi-stage build comes later.
ENTRYPOINT ["/usr/local/bin/frontend-entrypoint.sh"]
CMD ["npm", "run", "dev"]
