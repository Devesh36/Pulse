FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN --mount=type=secret,id=cloud_ca \
    set -eu; if [ -s /run/secrets/cloud_ca ]; then cp /run/secrets/cloud_ca /tmp/cloud-ca.pem; chmod 644 /tmp/cloud-ca.pem; export NODE_EXTRA_CA_CERTS=/tmp/cloud-ca.pem; fi; npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
