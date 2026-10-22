# syntax=docker/dockerfile:1

# Targets:
#   runtime (default) - nginx serving the production build and proxying /api to the backend
#   check             - lint, format check, type check and unit tests; the build fails if any fail

FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM deps AS check
COPY . .
RUN npm run lint \
    && npm run format:check \
    && npm run typecheck \
    && npm test

FROM deps AS build
COPY . .
RUN npm run build

FROM nginx:1.29-alpine AS runtime
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
# Where /api is proxied; matches the backend service name in docker-compose.yml.
ENV API_UPSTREAM=http://backend:8000
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/"]
