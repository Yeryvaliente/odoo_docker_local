import type { ProxyResponse } from '../types.ts';

function badgeClassFor(httpStatus: number): string {
  if (httpStatus === 0) return 'err';
  if (httpStatus >= 500) return 'err';
  if (httpStatus >= 400) return 'warn';
  if (httpStatus >= 200) return 'ok';
  return 'idle';
}

interface JsonViewerProps {
  title: string;
  result: ProxyResponse | null;
  pendingPreview?: unknown;
  busy?: boolean;
}

/**
 * Muestra el par request/response de la API tal cual, con el código HTTP.
 * Es deliberadamente crudo: además de depurar, sirve para leer el contrato.
 */
export function JsonViewer({ title, result, pendingPreview, busy }: JsonViewerProps) {
  const statusLabel = busy
    ? 'enviando…'
    : result
      ? result.httpStatus === 0
        ? 'sin conexión'
        : `HTTP ${result.httpStatus}`
      : 'sin ejecutar';

  return (
    <div className="json-panel">
      <h3>
        {title} <span className={`badge ${result ? badgeClassFor(result.httpStatus) : 'idle'}`}>
          {statusLabel}
        </span>
      </h3>

      {result?.request !== undefined && (
        <>
          <h3>request</h3>
          <pre>{JSON.stringify(result.request, null, 2)}</pre>
        </>
      )}

      {result ? (
        <>
          <h3>response</h3>
          <pre>{JSON.stringify(result.body, null, 2)}</pre>
        </>
      ) : (
        <>
          <h3>payload que se enviaría</h3>
          <pre>{JSON.stringify(pendingPreview ?? {}, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
