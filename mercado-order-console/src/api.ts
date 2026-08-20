/** Cliente del proxy local. El bearer vive en el backend, nunca acá. */

import type {
  CreateOrderPayload,
  EditOrderPayload,
  MercadoProduct,
  ProxyResponse,
  Recipient,
  ReferenceData,
} from './types.ts';

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`El proxy respondió ${response.status} en ${response.url}`);
  }
  return (await response.json()) as T;
}

export async function fetchReferenceData(): Promise<ReferenceData> {
  return readJson<ReferenceData>(await fetch('/api/reference'));
}

export async function fetchTarget(): Promise<{ apiBaseUrl: string }> {
  return readJson<{ apiBaseUrl: string }>(await fetch('/api/target'));
}

export async function searchRecipients(searchTerm: string): Promise<Recipient[]> {
  const payload = await readJson<{ recipients: Recipient[] }>(
    await fetch(`/api/recipients?q=${encodeURIComponent(searchTerm)}`),
  );
  return payload.recipients;
}

export async function searchProducts(searchTerm: string): Promise<MercadoProduct[]> {
  const payload = await readJson<{ products: MercadoProduct[] }>(
    await fetch(`/api/products?q=${encodeURIComponent(searchTerm)}`),
  );
  return payload.products;
}

export async function createOrder(payload: CreateOrderPayload): Promise<ProxyResponse> {
  return readJson<ProxyResponse>(
    await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchEditableLines(mercadoOrderId: string): Promise<ProxyResponse> {
  return readJson<ProxyResponse>(
    await fetch(`/api/orders/${encodeURIComponent(mercadoOrderId)}/edit`),
  );
}

export async function applyOrderEdit(
  mercadoOrderId: string,
  payload: EditOrderPayload,
): Promise<ProxyResponse> {
  return readJson<ProxyResponse>(
    await fetch(`/api/orders/${encodeURIComponent(mercadoOrderId)}/edit`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  );
}
