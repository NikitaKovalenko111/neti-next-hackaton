FROM node:22-bookworm-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund > /tmp/npm-ci.log 2>&1 || { \
    status=$?; \
    cat /tmp/npm-ci.log; \
    if ! grep -q 'code EUSAGE' /tmp/npm-ci.log || ! grep -Eq 'Missing: .+ from lock file|Invalid: lock file' /tmp/npm-ci.log; then exit "$status"; fi; \
    echo 'Warning: package-lock.json is out of sync. Refreshing the lockfile copy inside the image.' >&2; \
    npm install --package-lock-only --ignore-scripts --no-audit --no-fund && npm ci --no-audit --no-fund; \
    }

COPY . .
RUN npm run build

FROM nginx:1.28-alpine

ENV MINIO_BUCKET=images \
    NGINX_ENVSUBST_FILTER=^MINIO_BUCKET$

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist/ /usr/share/nginx/html/
