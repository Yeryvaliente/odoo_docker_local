/** Tipos del contrato v1_6 y de la API del proxy. */

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
 * Solo las enumeraciones chicas y cerradas se precargan. Los recipients se
 * buscan on demand: son cientos de miles y cualquier lista fija engaña.
 */
export interface ReferenceData {
  esquinaWarehouses: EsquinaWarehouse[];
  pymeCoverages: PymeCoverage[];
}

/** Una línea del formulario: producto + cantidad. */
export interface DraftLine {
  key: string;
  product: MercadoProduct | null;
  quantity: number;
}

/** Un grupo de pyme del payload (`businesses[]`). */
export interface DraftBusiness {
  key: string;
  businessCoverageMercadoId: number | null;
  lines: DraftLine[];
}

/** `items[]` tal como viaja en el payload. */
export interface OrderItemPayload {
  id: number;
  quantity: number;
}

export interface CreateOrderPayload {
  client: string;
  account_id: string;
  order_id: string;
  recipient_id: number;
  currency: string;
  shipping_cost: number;
  service_fee: number;
  mercado_warehouse_id?: number;
  items?: OrderItemPayload[];
  businesses?: { business_coverage_mercado_id: number; items: OrderItemPayload[] }[];
}

/** Línea editable que devuelve `GET .../{id}/edit`. */
export interface EditableLine {
  line_id: number;
  sale_order_id: number;
  product_id: number;
  product_name: string;
  sub_order: string;
  original_qty: number;
  delivered_qty: number;
  min_qty: number;
  unit_price: number;
}

export type ReturnDestination = '' | 'stock' | 'scrap' | 'no_return';

export interface EditItemPayload {
  line_id: number;
  new_qty: number;
  return_destination?: Exclude<ReturnDestination, ''>;
}

export interface EditOrderPayload {
  reason: string;
  items: EditItemPayload[];
  return_destination?: Exclude<ReturnDestination, ''>;
  create_credit_note?: boolean;
}

/** Lo que devuelve el proxy: status HTTP + body crudo (+ el request enviado). */
export interface ProxyResponse<TBody = unknown> {
  httpStatus: number;
  body: TBody;
  request?: unknown;
}

/** Entrada del historial de la sesión. */
export interface HistoryEntry {
  key: string;
  at: string;
  action: 'crear' | 'editar';
  orderReference: string;
  httpStatus: number;
  summary: string;
}
