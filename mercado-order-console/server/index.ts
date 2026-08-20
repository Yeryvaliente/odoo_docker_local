/**
 * Proxy mínimo de la consola de órdenes Mercado v1_6.
 *
 * Cuatro responsabilidades y nada más:
 *   1. servir el frontend construido (dist/)
 *   2. exponer los datos de referencia de la BD para los desplegables
 *   3. buscar productos publicados en Mercado
 *   4. reenviar create / get-edit / patch-edit a la API de Odoo con el bearer
 *
 * El token NUNCA baja al navegador: el frontend habla con este proxy y el proxy
 * pone el `Authorization`. Por eso el servicio se publica solo en 127.0.0.1.
 *
 * Contrato v1_6: extra-addons/twonary_mercado/notes/v1_6/{create-order,edit}.md
 * (espejado en Confluence, space MAR).
 */

import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import fastifyStatic from '@fastify/static';
import Fastify from 'fastify';

import { loadConfig } from './config.ts';
import { ReferenceRepository } from './reference.ts';

const COMBINED_ORDERS_PATH = '/api/mercado/v1_6/combined-orders';

const config = loadConfig();
const repository = new ReferenceRepository(config);
const app = Fastify({ logger: true });

interface ProxyResult {
  httpStatus: number;
  body: unknown;
}

/** Llama la API de Odoo y devuelve status + body sin interpretarlo. */
async function callOdoo(
  method: 'GET' | 'POST' | 'PATCH',
  path: string,
  payload?: unknown,
): Promise<ProxyResult> {
  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${config.apiBearerToken}`,
        'Content-Type': 'application/json',
      },
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: AbortSignal.timeout(180_000),
    });
  } catch (error) {
    const reason = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    return { httpStatus: 0, body: { transport_error: reason } };
  }
  const rawBody = await response.text();
  try {
    return { httpStatus: response.status, body: JSON.parse(rawBody) };
  } catch {
    return { httpStatus: response.status, body: { raw: rawBody.slice(0, 8000) } };
  }
}

app.get('/api/reference', async () => repository.loadReferenceData());

app.get<{ Querystring: { q?: string } }>('/api/products', async (request) => ({
  products: await repository.searchProducts(request.query.q ?? ''),
}));

app.get<{ Querystring: { q?: string } }>('/api/recipients', async (request) => ({
  recipients: await repository.searchRecipients(request.query.q ?? ''),
}));

app.get('/api/target', async () => ({
  apiBaseUrl: config.apiBaseUrl,
  comercialProgresoCompanyId: config.comercialProgresoCompanyId,
}));

app.post('/api/orders', async (request) => {
  const payload = request.body;
  const proxied = await callOdoo('POST', COMBINED_ORDERS_PATH, payload);
  return { ...proxied, request: payload };
});

app.get<{ Params: { mercadoOrderId: string } }>(
  '/api/orders/:mercadoOrderId/edit',
  async (request) =>
    callOdoo('GET', `${COMBINED_ORDERS_PATH}/${request.params.mercadoOrderId}/edit`),
);

app.patch<{ Params: { mercadoOrderId: string } }>(
  '/api/orders/:mercadoOrderId/edit',
  async (request) => {
    const payload = request.body;
    const proxied = await callOdoo(
      'PATCH',
      `${COMBINED_ORDERS_PATH}/${request.params.mercadoOrderId}/edit`,
      payload,
    );
    return { ...proxied, request: payload };
  },
);

// El frontend construido. En `npm run dev` lo sirve Vite en otro puerto y este
// bloque no aplica, por eso el existsSync.
const serverDirectory = dirname(fileURLToPath(import.meta.url));
const distDirectory = join(serverDirectory, '..', 'dist');
if (existsSync(distDirectory)) {
  await app.register(fastifyStatic, { root: distDirectory });
  app.setNotFoundHandler((request, reply) => {
    if (request.url.startsWith('/api/')) {
      return reply.code(404).send({ error: 'not found' });
    }
    return reply.sendFile('index.html');
  });
} else {
  app.log.warn('dist/ no existe — corré `npm run build`, o usá `npm run dev`.');
}

const shutdown = async () => {
  await app.close();
  await repository.close();
  process.exit(0);
};
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

await app.listen({ host: '0.0.0.0', port: config.port });
app.log.info(`API destino: ${config.apiBaseUrl}`);
