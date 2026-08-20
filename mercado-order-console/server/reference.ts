/**
 * Datos de referencia para poblar los desplegables, leídos de la BD de Odoo.
 *
 * La sesión es READ ONLY a propósito: los cambios de negocio van por la API HTTP
 * (que corre las validaciones, la reserva y la contabilidad), nunca por SQL.
 *
 * Mapeo de los ids del contrato v1_6:
 *   - `mercado_warehouse_id`         -> stock_warehouse.two_mercado_sub_business_id
 *                                       del almacén ESPEJO en Comercial Progreso
 *   - `business_coverage_mercado_id` -> twonary_mercado_business_coverage.mercado_id
 *   - `recipient_id`                 -> res_partner.id
 *   - items[].id                     -> product_product.id (template con two_mercado_ok)
 */

import { Pool } from 'pg';

import type { ConsoleConfig } from './config.ts';

export interface EsquinaWarehouse {
  mercadoWarehouseId: number;
  code: string;
  name: string;
}

export interface PymeCoverage {
  businessCoverageMercadoId: number;
  businessName: string;
  province: string;
}

export interface Recipient {
  recipientId: number;
  name: string;
  province: string;
}

export interface MercadoProduct {
  productId: number;
  name: string;
  listPrice: number;
}

/**
 * Solo las enumeraciones CHICAS y cerradas van precargadas. Los recipients no:
 * son cientos de miles, así que se buscan on demand (ver `searchRecipients`).
 */
export interface ReferenceData {
  esquinaWarehouses: EsquinaWarehouse[];
  pymeCoverages: PymeCoverage[];
}

/** Los campos traducibles de Odoo son jsonb; devuelve algo legible. */
function readTranslated(value: unknown): string {
  if (value && typeof value === 'object') {
    const byLanguage = value as Record<string, string>;
    for (const language of ['es_419', 'es_ES', 'en_US']) {
      if (byLanguage[language]) return byLanguage[language];
    }
    const first = Object.values(byLanguage)[0];
    return first ?? '';
  }
  return typeof value === 'string' ? value : '';
}

export class ReferenceRepository {
  // Campos declarados explícitamente en vez de parameter properties: el modo
  // strip-only de Node (--experimental-strip-types) no soporta esa sintaxis
  // porque requiere transformar el código, no solo borrar los tipos.
  private readonly pool: Pool;
  private readonly config: ConsoleConfig;

  constructor(config: ConsoleConfig) {
    this.config = config;
    // El nombre de BD que viene en la URL puede no ser el de Odoo; se normaliza
    // a `odoo`, igual que hacen los scripts de diagnóstico del equipo.
    const withOdooDatabase = config.databaseUrl.replace(/\/([^/?]+)(\?|$)/, '/odoo$2');
    const parsedUrl = new URL(withOdooDatabase);
    const isLocalDatabase = ['localhost', '127.0.0.1', 'postgres'].includes(
      parsedUrl.hostname,
    );
    // El RDS usa un CA que Node no trae, así que `pg` corta con
    // UNABLE_TO_GET_ISSUER_CERT_LOCALLY. `sslmode=no-verify` mantiene la conexión
    // CIFRADA y solo omite validar la cadena del certificado — el mismo criterio
    // con el que psycopg2 (`sslmode=require`) y DBeaver llegan a este cluster.
    // Va en la URL y no en la opción `ssl` porque el sslmode de la connection
    // string tiene precedencia y pisaría la opción.
    parsedUrl.searchParams.set('sslmode', isLocalDatabase ? 'disable' : 'no-verify');
    this.pool = new Pool({ connectionString: parsedUrl.toString(), max: 4 });
  }

  private async query<T>(sql: string, parameters: unknown[] = []): Promise<T[]> {
    const client = await this.pool.connect();
    try {
      // `SET SESSION CHARACTERISTICS`, no `SET TRANSACTION`: el segundo solo
      // aplica dentro de un bloque de transacción explícito, así que en una
      // conexión con autocommit no garantizaría nada.
      await client.query('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY');
      await client.query("SET statement_timeout = '30s'");
      const result = await client.query(sql, parameters);
      return result.rows as T[];
    } finally {
      client.release();
    }
  }

  async loadReferenceData(): Promise<ReferenceData> {
    const [warehouseRows, coverageRows] = await Promise.all([
      this.query<{ mercado_warehouse_id: number; code: string; name: unknown }>(
        `SELECT two_mercado_sub_business_id AS mercado_warehouse_id, code, name
           FROM stock_warehouse
          WHERE company_id = $1 AND two_mercado_sub_business_id IS NOT NULL
          ORDER BY two_mercado_sub_business_id`,
        [this.config.comercialProgresoCompanyId],
      ),
      // Se excluye La Esquina Caliente: sus órdenes van por el bloque top-level
      // (`mercado_warehouse_id`), y el controller rechaza una pyme mandada como
      // esquina y viceversa.
      this.query<{ mercado_id: number; business: unknown; province: unknown }>(
        `SELECT c.mercado_id, b.name AS business, s.name AS province
           FROM twonary_mercado_business_coverage c
           JOIN twonary_mercado_business b ON b.id = c.business_id
           LEFT JOIN res_country_state s ON s.id = c.state_id
          WHERE c.mercado_id IS NOT NULL AND c.mercado_id > 0
            AND b.name <> $1
          ORDER BY b.name, c.mercado_id`,
        [this.config.esquinaBusinessName],
      ),
    ]);

    return {
      esquinaWarehouses: warehouseRows.map((row) => ({
        mercadoWarehouseId: row.mercado_warehouse_id,
        code: row.code,
        name: readTranslated(row.name),
      })),
      pymeCoverages: coverageRows.map((row) => ({
        businessCoverageMercadoId: row.mercado_id,
        businessName: readTranslated(row.business),
        province: readTranslated(row.province),
      })),
    };
  }

  /**
   * Busca un recipient por nombre o por id exacto.
   *
   * No se precargan: la tabla tiene cientos de miles de partners, así que
   * cualquier lista fija es una muestra engañosa. El campo de la UI es libre y
   * esto es solo la ayuda para encontrar el id.
   */
  async searchRecipients(searchTerm: string, limit = 40): Promise<Recipient[]> {
    const numericId = /^\d+$/.test(searchTerm.trim()) ? Number(searchTerm.trim()) : null;
    const rows = await this.query<{ id: number; name: unknown; province: unknown }>(
      `SELECT p.id, p.name, s.name AS province
         FROM res_partner p
         LEFT JOIN res_country_state s ON s.id = p.state_id
        WHERE p.active
          AND ( ($1::int IS NOT NULL AND p.id = $1::int)
                OR p.name ILIKE $2 )
        ORDER BY (p.id = COALESCE($1::int, -1)) DESC, p.id DESC
        LIMIT $3`,
      [numericId, `%${searchTerm}%`, limit],
    );
    return rows.map((row) => ({
      recipientId: row.id,
      name: readTranslated(row.name),
      province: readTranslated(row.province),
    }));
  }

  /** Busca por nombre o por id exacto entre los productos publicados en Mercado. */
  async searchProducts(searchTerm: string, limit = 40): Promise<MercadoProduct[]> {
    const numericId = /^\d+$/.test(searchTerm.trim()) ? Number(searchTerm.trim()) : null;
    const rows = await this.query<{ id: number; name: unknown; list_price: string }>(
      `SELECT pp.id, t.name, t.list_price
         FROM product_product pp
         JOIN product_template t ON t.id = pp.product_tmpl_id
        WHERE t.two_mercado_ok AND t.sale_ok AND pp.active AND t.active
          AND ( ($1::int IS NOT NULL AND pp.id = $1::int)
                OR t.name->>'en_US' ILIKE $2
                OR t.name->>'es_419' ILIKE $2 )
        ORDER BY pp.id
        LIMIT $3`,
      [numericId, `%${searchTerm}%`, limit],
    );
    return rows.map((row) => ({
      productId: row.id,
      name: readTranslated(row.name),
      listPrice: Number(row.list_price ?? 0),
    }));
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}
