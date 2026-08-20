# Consola de órdenes Mercado v1_6.
#
# Un solo servicio: Fastify sirve el frontend ya construido y hace de proxy a la
# API de Odoo. El frontend se buildea acá dentro, así la imagen no depende de que
# haya un dist/ en el host.
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY server ./server
RUN npm run build


FROM node:22-alpine

WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json* ./
# Solo runtime: fastify, @fastify/static y pg. Vite / React / tsx quedan afuera.
RUN npm install --omit=dev && npm cache clean --force

COPY --from=build /app/dist ./dist
COPY server ./server

EXPOSE 8900

# `--experimental-strip-types` deja correr los .ts del server sin build previo.
CMD ["node", "--experimental-strip-types", "server/index.ts"]
