# ClimateAdapt Lab frontend: static build served by nginx.
# Node 22 LTS (Vite 8 requires >= 20.19). The API base URL is baked at build
# time from VITE_API_BASE_URL (Vite semantics: VITE_* are build-time only).
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=http://127.0.0.1:8000
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
