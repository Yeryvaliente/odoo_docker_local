import { useEffect, useState } from 'react';

import { fetchReferenceData, fetchTarget } from './api.ts';
import { CreateOrderPanel } from './components/CreateOrderPanel.tsx';
import { EditOrderPanel } from './components/EditOrderPanel.tsx';
import type { HistoryEntry, ReferenceData } from './types.ts';

type TabKey = 'create' | 'edit';

const EMPTY_REFERENCE: ReferenceData = {
  esquinaWarehouses: [],
  pymeCoverages: [],
};

export function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('create');
  const [reference, setReference] = useState<ReferenceData>(EMPTY_REFERENCE);
  const [targetUrl, setTargetUrl] = useState('');
  const [loadError, setLoadError] = useState('');
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    Promise.all([fetchReferenceData(), fetchTarget()])
      .then(([referenceData, target]) => {
        setReference(referenceData);
        setTargetUrl(target.apiBaseUrl);
      })
      .catch((error: unknown) =>
        setLoadError(error instanceof Error ? error.message : String(error)),
      );
  }, []);

  const recordAction =
    (action: HistoryEntry['action']) =>
    (httpStatus: number, orderReference: string, summary: string) =>
      setHistory((previous) => [
        {
          key: `${Date.now()}-${orderReference}`,
          at: new Date().toLocaleTimeString('es-419'),
          action,
          orderReference,
          httpStatus,
          summary,
        },
        ...previous,
      ]);

  return (
    <>
      <header className="app-header">
        <h1>Consola de órdenes · Mercado v1_6</h1>
        <span className="target">{targetUrl || 'cargando destino…'}</span>
        <span className="spacer" />
        <span className="target">
          {reference.esquinaWarehouses.length} almacenes de esquina ·{' '}
          {reference.pymeCoverages.length} coverages de pymes
        </span>
      </header>

      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'create'}
          onClick={() => setActiveTab('create')}
        >
          Crear
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'edit'}
          onClick={() => setActiveTab('edit')}
        >
          Editar
        </button>
      </div>

      <main>
        <div className="panel">
          {loadError && (
            <div className="banner">
              No pude cargar los datos de referencia: {loadError}. Revisá <code>DATABASE_URL</code>{' '}
              en el <code>.env</code>.
            </div>
          )}

          {activeTab === 'create' ? (
            <CreateOrderPanel reference={reference} onRecorded={recordAction('crear')} />
          ) : (
            <EditOrderPanel onRecorded={recordAction('editar')} />
          )}

          <div className="history">
            <h3>Historial de la sesión</h3>
            {history.length === 0 ? (
              <p className="empty">Todavía no mandaste nada.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>hora</th>
                    <th>acción</th>
                    <th>order</th>
                    <th>HTTP</th>
                    <th>resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((entry) => (
                    <tr key={entry.key}>
                      <td>{entry.at}</td>
                      <td>{entry.action}</td>
                      <td>{entry.orderReference}</td>
                      <td>
                        <span
                          className={`badge ${
                            entry.httpStatus >= 500
                              ? 'err'
                              : entry.httpStatus >= 400
                                ? 'warn'
                                : 'ok'
                          }`}
                        >
                          {entry.httpStatus}
                        </span>
                      </td>
                      <td>{entry.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </main>
    </>
  );
}
