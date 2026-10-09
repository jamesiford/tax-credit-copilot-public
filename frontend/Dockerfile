# OPTIONAL, for local container use only. Platform v2 deploys the web app as
# code to App Service (Node 24 LTS) and serves it with frontend/server/
# (`npm start`), which replaces nginx. Nothing in the deploy path builds this.
#
# Tax Credit Copilot — Web container.
#
# Build strategy: we DO NOT run `npm run build` inside the container.
# esbuild's native binary segfaults under Docker Desktop x86_64 emulation on
# Windows hosts (Go runtime crashes in validateDefines with garbage pointers).
# Instead, azd's `prepackage` hook runs `npm ci && npm run build` on the host
# before docker build; we just package the resulting `dist/` into nginx.

FROM nginx:alpine

# nginx.conf is a template — `envsubst` rewrites ${API_BACKEND_URL} at
# container start. This lets one image work across environments.
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Pre-built bundle from the host.
COPY dist/ /usr/share/nginx/html/

EXPOSE 80

# nginx:alpine's default entrypoint already runs envsubst over /etc/nginx/templates.
CMD ["nginx", "-g", "daemon off;"]
