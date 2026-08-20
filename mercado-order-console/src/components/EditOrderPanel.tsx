import { useState } from 'react';

import { applyOrderEdit, fetchEditableLines } from '../api.ts';
import type {
  EditItemPayload,
  EditOrderPayload,
  EditableLine,
  ProxyResponse,
  ReturnDestination,
} from '../types.ts';
import { JsonViewer } from './JsonViewer.tsx';

interface DraftEdit {
  newQuantity: number;
  returnDestination: ReturnDestination;
}

interface EditOrderPanelProps {
  onRecorded: (httpStatus: number, orderReference: string, summary: string) => void;
}

export function EditOrderPanel({ onRecorded }: EditOrderPanelProps) {
  const [mercadoOrderId, setMercadoOrderId] = useState('');
  const [lines, setLines] = useState<EditableLine[]>([]);
  const [drafts, setDrafts] = useState<Record<number, DraftEdit>>({});
  const [reason, setReason] = useState('Cliente cambió el pedido');
  const [globalReturnDestination, setGlobalReturnDestination] = useState<ReturnDestination>('');
  const [createCreditNote, setCreateCreditNote] = useState(false);
  const [result, setResult] = useState<ProxyResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [validationError, setValidationError] = useState('');

  async function loadLines() {
    if (!mercadoOrderId.trim()) return setValidationError('Poné el mercado_order_id.');
    setValidationError('');
    setBusy(true);
    try {
      const response = await fetchEditableLines(mercadoOrderId.trim());
      setResult(response);
      const responseBody = response.body as { data?: { lines?: EditableLine[] } };
      const loadedLines = responseBody.data?.lines ?? [];
      setLines(loadedLines);
      setDrafts(
        Object.fromEntries(
          loadedLines.map((line) => [
            line.line_id,
            { newQuantity: line.original_qty, returnDestination: '' as ReturnDestination },
          ]),
        ),
      );
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  /** Solo viajan las líneas cuya cantidad cambió: el PATCH no es un reemplazo total. */
  const changedItems: EditItemPayload[] = lines
    .filter((line) => drafts[line.line_id]?.newQuantity !== line.original_qty)
    .map((line) => {
      const draft = drafts[line.line_id];
      const payloadItem: EditItemPayload = { line_id: line.line_id, new_qty: draft.newQuantity };
      if (draft.returnDestination) payloadItem.return_destination = draft.returnDestination;
      return payloadItem;
    });

  const payload: EditOrderPayload = {
    reason,
    items: changedItems,
    ...(globalReturnDestination ? { return_destination: globalReturnDestination } : {}),
    ...(createCreditNote ? { create_credit_note: true } : {}),
  };

  async function submit() {
    if (!reason.trim()) return setValidationError('`reason` es requerido por el contrato.');
    if (changedItems.length === 0) {
      return setValidationError('No cambiaste ninguna cantidad — no hay nada que aplicar.');
    }
    setValidationError('');
    setBusy(true);
    try {
      const response = await applyOrderEdit(mercadoOrderId.trim(), payload);
      setResult(response);
      const responseBody = response.body as {
        data?: { lines_modified?: number; amount_difference?: number };
      };
      onRecorded(
        response.httpStatus,
        mercadoOrderId.trim(),
        `${responseBody.data?.lines_modified ?? 0} línea(s), Δ ${
          responseBody.data?.amount_difference ?? 0
        }`,
      );
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

        <div className="line-row">
          <div className="grow">
            <label htmlFor="mercadoOrderId">
              mercado_order_id <span className="req">*</span>
            </label>
            <input
              id="mercadoOrderId"
              placeholder="el order_id numérico con el que se creó"
              value={mercadoOrderId}
              onChange={(event) => setMercadoOrderId(event.target.value)}
            />
          </div>
          <button className="ghost" onClick={loadLines} disabled={busy}>
            GET líneas
          </button>
        </div>

        {lines.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>line_id</th>
                <th>SO</th>
                <th>producto</th>
                <th className="num">original</th>
                <th className="num">entregado</th>
                <th className="num">precio</th>
                <th className="num">new_qty</th>
                <th>return_destination</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line) => {
                const draft = drafts[line.line_id];
                const changed = draft?.newQuantity !== line.original_qty;
                return (
                  <tr key={line.line_id} className={changed ? 'changed' : undefined}>
                    <td>{line.line_id}</td>
                    <td>{line.sale_order_id}</td>
                    <td>{line.product_name}</td>
                    <td className="num">{line.original_qty}</td>
                    <td className="num">{line.delivered_qty}</td>
                    <td className="num">{line.unit_price}</td>
                    <td className="num">
                      <input
                        type="number"
                        min={line.min_qty}
                        step="0.01"
                        style={{ width: 84 }}
                        value={draft?.newQuantity ?? line.original_qty}
                        onChange={(event) =>
                          setDrafts((previous) => ({
                            ...previous,
                            [line.line_id]: {
                              ...previous[line.line_id],
                              newQuantity: Number(event.target.value),
                            },
                          }))
                        }
                      />
                    </td>
                    <td>
                      <select
                        value={draft?.returnDestination ?? ''}
                        onChange={(event) =>
                          setDrafts((previous) => ({
                            ...previous,
                            [line.line_id]: {
                              ...previous[line.line_id],
                              returnDestination: event.target.value as ReturnDestination,
                            },
                          }))
                        }
                      >
                        <option value="">— global —</option>
                        <option value="stock">stock</option>
                        <option value="scrap">scrap</option>
                        <option value="no_return">no_return</option>
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p className="hint">
            Traé las líneas con <strong>GET líneas</strong>. La tabla agrega el parent RD y el
            child Comercial Progreso; la columna <code>SO</code> dice en cuál vive cada línea.
          </p>
        )}

        <div className="field-grid" style={{ marginTop: 20 }}>
          <div>
            <label htmlFor="reason">
              reason <span className="req">*</span>
            </label>
            <input id="reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>
          <div>
            <label htmlFor="globalReturn">return_destination (global)</label>
            <select
              id="globalReturn"
              value={globalReturnDestination}
              onChange={(event) => setGlobalReturnDestination(event.target.value as ReturnDestination)}
            >
              <option value="">— por línea —</option>
              <option value="stock">stock</option>
              <option value="scrap">scrap</option>
              <option value="no_return">no_return</option>
            </select>
          </div>
        </div>

        <div className="actions">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
            <input
              type="checkbox"
              checked={createCreditNote}
              onChange={(event) => setCreateCreditNote(event.target.checked)}
            />
            create_credit_note
          </label>
          <button className="primary" onClick={submit} disabled={busy || changedItems.length === 0}>
            {busy ? 'Enviando…' : `PATCH aplicar (${changedItems.length})`}
          </button>
          <span className="hint">Bajar cantidad genera return según el destino; subir re-reserva.</span>
        </div>
      </div>

      <JsonViewer title="Editar orden" result={result} pendingPreview={payload} busy={busy} />
    </div>
  );
}
