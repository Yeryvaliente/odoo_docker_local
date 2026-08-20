import { useMemo, useState } from 'react';

import { createOrder } from '../api.ts';
import type {
  CreateOrderPayload,
  DraftBusiness,
  DraftLine,
  MercadoProduct,
  OrderItemPayload,
  ProxyResponse,
  ReferenceData,
} from '../types.ts';
import { JsonViewer } from './JsonViewer.tsx';
import { ProductPicker } from './ProductPicker.tsx';
import { RecipientField } from './RecipientField.tsx';

const newKey = () => Math.random().toString(36).slice(2, 9);
const emptyLine = (): DraftLine => ({ key: newKey(), product: null, quantity: 1 });

interface CreateOrderPanelProps {
  reference: ReferenceData;
  onRecorded: (httpStatus: number, orderReference: string, summary: string) => void;
}

export function CreateOrderPanel({ reference, onRecorded }: CreateOrderPanelProps) {
  const [client, setClient] = useState('CUBALLAMA');
  const [accountId, setAccountId] = useState('ACC-12345');
  const [orderId, setOrderId] = useState(`ORD-${Date.now().toString().slice(-6)}`);
  const [recipientId, setRecipientId] = useState<number | null>(null);
  const [currency, setCurrency] = useState('USD');
  const [shippingCost, setShippingCost] = useState('3.00');
  const [serviceFee, setServiceFee] = useState('1.50');

  const [esquinaWarehouseId, setEsquinaWarehouseId] = useState<number | null>(null);
  const [esquinaLines, setEsquinaLines] = useState<DraftLine[]>([emptyLine()]);
  const [businesses, setBusinesses] = useState<DraftBusiness[]>([]);

  const [result, setResult] = useState<ProxyResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [validationError, setValidationError] = useState('');

  const toItems = (lines: DraftLine[]): OrderItemPayload[] =>
    lines
      .filter((line) => line.product && line.quantity > 0)
      .map((line) => ({ id: line.product!.productId, quantity: line.quantity }));

  const payload = useMemo<CreateOrderPayload>(() => {
    const draft: CreateOrderPayload = {
      client,
      account_id: accountId,
      order_id: orderId,
      recipient_id: recipientId ?? 0,
      currency,
      shipping_cost: Number(shippingCost),
      service_fee: Number(serviceFee),
    };
    const esquinaItems = toItems(esquinaLines);
    if (esquinaWarehouseId && esquinaItems.length) {
      draft.mercado_warehouse_id = esquinaWarehouseId;
      draft.items = esquinaItems;
    }
    const pymeGroups = businesses
      .map((business) => ({
        business_coverage_mercado_id: business.businessCoverageMercadoId ?? 0,
        items: toItems(business.lines),
      }))
      .filter((group) => group.business_coverage_mercado_id && group.items.length);
    if (pymeGroups.length) draft.businesses = pymeGroups;
    return draft;
  }, [
    client, accountId, orderId, recipientId, currency, shippingCost, serviceFee,
    esquinaWarehouseId, esquinaLines, businesses,
  ]);

  const shapeLabel = payload.items && payload.businesses
    ? 'mixto (esquina + pymes)'
    : payload.items
      ? 'solo esquina'
      : payload.businesses
        ? 'solo pymes'
        : 'incompleto';

  async function submit() {
    if (!payload.order_id) return setValidationError('`order_id` es requerido.');
    if (!payload.recipient_id) return setValidationError('Elegí un `recipient_id`.');
    if (!payload.items && !payload.businesses) {
      return setValidationError(
        'Hace falta el bloque de esquina (almacén + productos) y/o al menos un negocio con productos.',
      );
    }
    setValidationError('');
    setBusy(true);
    try {
      const response = await createOrder(payload);
      setResult(response);
      const responseBody = response.body as {
        data?: { order_id?: number; partial?: boolean; already_created?: boolean };
      };
      const summary = responseBody.data?.already_created
        ? 'idempotente: ya existía'
        : responseBody.data?.partial
          ? 'parcial — ver children[]'
          : `SO ${responseBody.data?.order_id ?? '?'}`;
      onRecorded(response.httpStatus, payload.order_id, summary);
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="split">
      <div>
        {validationError && <div className="banner">{validationError}</div>}

        <div className="field-grid">
          <div>
            <label htmlFor="client">client</label>
            <select id="client" value={client} onChange={(event) => setClient(event.target.value)}>
              <option>CUBALLAMA</option>
              <option>ACUBA</option>
            </select>
          </div>
          <div>
            <label htmlFor="accountId">account_id</label>
            <input id="accountId" value={accountId} onChange={(event) => setAccountId(event.target.value)} />
          </div>
          <div>
            <label htmlFor="orderId">
              order_id <span className="req">*</span>
            </label>
            <input id="orderId" value={orderId} onChange={(event) => setOrderId(event.target.value)} />
          </div>
          <div>
            <label htmlFor="recipientId">
              recipient_id <span className="req">*</span>
            </label>
            <RecipientField recipientId={recipientId} onChange={setRecipientId} />
          </div>
          <div>
            <label htmlFor="currency">currency</label>
            <select id="currency" value={currency} onChange={(event) => setCurrency(event.target.value)}>
              <option>USD</option>
              <option>EUR</option>
            </select>
          </div>
          <div>
            <label htmlFor="shippingCost">shipping_cost</label>
            <input id="shippingCost" type="number" step="0.01" value={shippingCost}
              onChange={(event) => setShippingCost(event.target.value)} />
          </div>
          <div>
            <label htmlFor="serviceFee">service_fee</label>
            <input id="serviceFee" type="number" step="0.01" value={serviceFee}
              onChange={(event) => setServiceFee(event.target.value)} />
          </div>
        </div>

        <fieldset>
          <legend>La Esquina Caliente — bloque top-level</legend>
          <div className="line-row">
            <div className="grow">
              <label htmlFor="esquinaWarehouse">mercado_warehouse_id</label>
              <select
                id="esquinaWarehouse"
                value={esquinaWarehouseId ?? ''}
                onChange={(event) => setEsquinaWarehouseId(Number(event.target.value) || null)}
              >
                <option value="">— sin esquina —</option>
                {reference.esquinaWarehouses.map((warehouse) => (
                  <option key={warehouse.mercadoWarehouseId} value={warehouse.mercadoWarehouseId}>
                    {warehouse.mercadoWarehouseId} · {warehouse.code} · {warehouse.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {esquinaLines.map((line) => (
            <LineRow
              key={line.key}
              line={line}
              onChange={(updated) =>
                setEsquinaLines((previous) => previous.map((l) => (l.key === updated.key ? updated : l)))
              }
              onRemove={() =>
                setEsquinaLines((previous) => previous.filter((l) => l.key !== line.key))
              }
            />
          ))}
          <button className="tiny" onClick={() => setEsquinaLines((previous) => [...previous, emptyLine()])}>
            + producto
          </button>
          <p className="hint">
            Solo para La Esquina Caliente. Una pyme mandada por acá la rechaza el controller;
            va en <code>businesses[]</code>.
          </p>
        </fieldset>

        <fieldset>
          <legend>Pymes — businesses[]</legend>
          {businesses.length === 0 && <p className="hint">Sin negocios todavía.</p>}
          {businesses.map((business) => (
            <BusinessBlock
              key={business.key}
              business={business}
              coverages={reference.pymeCoverages}
              onChange={(updated) =>
                setBusinesses((previous) => previous.map((b) => (b.key === updated.key ? updated : b)))
              }
              onRemove={() =>
                setBusinesses((previous) => previous.filter((b) => b.key !== business.key))
              }
            />
          ))}
          <button
            className="tiny"
            onClick={() =>
              setBusinesses((previous) => [
                ...previous,
                { key: newKey(), businessCoverageMercadoId: null, lines: [emptyLine()] },
              ])
            }
          >
            + negocio
          </button>
        </fieldset>

        <div className="actions">
          <button className="primary" onClick={submit} disabled={busy}>
            {busy ? 'Enviando…' : 'POST crear + confirmar'}
          </button>
          <button className="ghost" onClick={() => setResult(null)}>
            Limpiar respuesta
          </button>
          <span className="hint">
            shape: <strong>{shapeLabel}</strong> · idempotencia por <code>MER-{payload.order_id}</code>
          </span>
        </div>
      </div>

      <JsonViewer title="Crear orden" result={result} pendingPreview={payload} busy={busy} />
    </div>
  );
}

function LineRow({
  line,
  onChange,
  onRemove,
}: {
  line: DraftLine;
  onChange: (line: DraftLine) => void;
  onRemove: () => void;
}) {
  return (
    <div className="line-row">
      <div className="grow">
        <label>producto</label>
        <ProductPicker
          chosen={line.product}
          onChoose={(product: MercadoProduct) => onChange({ ...line, product })}
        />
      </div>
      <div className="qty">
        <label>quantity</label>
        <input
          type="number"
          min="1"
          step="1"
          value={line.quantity}
          onChange={(event) => onChange({ ...line, quantity: Number(event.target.value) })}
        />
      </div>
      <button className="tiny" onClick={onRemove} title="quitar línea">
        ×
      </button>
    </div>
  );
}

function BusinessBlock({
  business,
  coverages,
  onChange,
  onRemove,
}: {
  business: DraftBusiness;
  coverages: ReferenceData['pymeCoverages'];
  onChange: (business: DraftBusiness) => void;
  onRemove: () => void;
}) {
  return (
    <fieldset style={{ background: 'transparent' }}>
      <legend>
        negocio
        <button className="tiny" onClick={onRemove}>
          ×
        </button>
      </legend>
      <div className="line-row">
        <div className="grow">
          <label>business_coverage_mercado_id</label>
          <select
            value={business.businessCoverageMercadoId ?? ''}
            onChange={(event) =>
              onChange({ ...business, businessCoverageMercadoId: Number(event.target.value) || null })
            }
          >
            <option value="">— elegir —</option>
            {coverages.map((coverage) => (
              <option
                key={coverage.businessCoverageMercadoId}
                value={coverage.businessCoverageMercadoId}
              >
                {coverage.businessCoverageMercadoId} · {coverage.businessName} · {coverage.province}
              </option>
            ))}
          </select>
        </div>
      </div>
      {business.lines.map((line) => (
        <LineRow
          key={line.key}
          line={line}
          onChange={(updated) =>
            onChange({
              ...business,
              lines: business.lines.map((l) => (l.key === updated.key ? updated : l)),
            })
          }
          onRemove={() =>
            onChange({ ...business, lines: business.lines.filter((l) => l.key !== line.key) })
          }
        />
      ))}
      <button
        className="tiny"
        onClick={() => onChange({ ...business, lines: [...business.lines, emptyLine()] })}
      >
        + producto
      </button>
    </fieldset>
  );
}
