/**
 * Configuración del servicio, toda por entorno.
 *
 * La allowlist de hosts NO es opcional: esta consola CREA y EDITA órdenes reales.
 * Es una allowlist (permitir explícito), no una denylist, para que un host nuevo
 * tenga que agregarse a mano en vez de colarse por omisión.
 */

const ALLOWED_API_HOSTS = [
  'odoo-test.ecsdev.cubatelefono.com',
  'odoo.localhost',
  'odoo', // nombre del servicio dentro de la red de docker-compose
  'localhost',
  '127.0.0.1',
];

export interface ConsoleConfig {
  readonly apiBaseUrl: string;
  readonly apiBearerToken: string;
  readonly databaseUrl: string;
  readonly port: number;
  readonly comercialProgresoCompanyId: number;
  readonly esquinaBusinessName: string;
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Falta la variable de entorno ${name}. Copiá .env.example a .env y completala.`,
    );
  }
  return value;
}

export function loadConfig(): ConsoleConfig {
  const apiBaseUrl = requireEnv('ODOO_URL').replace(/\/+$/, '');
  const host = new URL(apiBaseUrl).hostname;
  if (!ALLOWED_API_HOSTS.includes(host)) {
    throw new Error(
      `El host '${host}' no está en la allowlist. Esta consola crea y edita ` +
        `órdenes, así que no se apunta a producción. Permitidos: ` +
        `${ALLOWED_API_HOSTS.join(', ')}`,
    );
  }
  return {
    apiBaseUrl,
    // `auth="bearer"` de los controllers es el de Odoo core
    // (base/models/ir_http.py::_auth_method_bearer), que acepta una API key de
    // Odoo como token — la misma que se usa para XML-RPC.
    apiBearerToken: requireEnv('ODOO_API_KEY'),
    databaseUrl: requireEnv('DATABASE_URL'),
    port: Number(process.env.PORT ?? 8900),
    comercialProgresoCompanyId: Number(process.env.CP_COMPANY_ID ?? 472),
    esquinaBusinessName: process.env.ESQUINA_BUSINESS_NAME ?? 'La Esquina Caliente',
  };
}
