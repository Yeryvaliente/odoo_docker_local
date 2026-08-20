import { useEffect, useRef, useState } from 'react';

import { searchRecipients } from '../api.ts';
import type { Recipient } from '../types.ts';

interface RecipientFieldProps {
  recipientId: number | null;
  onChange: (recipientId: number | null) => void;
}

/**
 * `recipient_id` como CAMPO LIBRE, con buscador opcional al lado.
 *
 * Es campo libre a propósito: la tabla de partners tiene cientos de miles de
 * filas, así que ningún desplegable la representa — el caso normal es pegar un
 * id que ya tenés. El buscador está para cuando solo te acordás del nombre, y lo
 * único que hace es escribir el id en el campo.
 */
export function RecipientField({ recipientId, onChange }: RecipientFieldProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [matches, setMatches] = useState<Recipient[]>([]);
  const [searching, setSearching] = useState(false);
  const [chosenLabel, setChosenLabel] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!searchOpen) return;
    const timer = setTimeout(() => {
      setSearching(true);
      searchRecipients(searchTerm)
        .then(setMatches)
        .catch(() => setMatches([]))
        .finally(() => setSearching(false));
    }, 220);
    return () => clearTimeout(timer);
  }, [searchOpen, searchTerm]);

  useEffect(() => {
    if (!searchOpen) return;
    const onClickOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setSearchOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [searchOpen]);

  return (
    <div className="picker" ref={containerRef}>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="number"
          min="1"
          placeholder="pegá el id del partner"
          value={recipientId ?? ''}
          onChange={(event) => {
            setChosenLabel('');
            onChange(Number(event.target.value) || null);
          }}
        />
        <button
          className="ghost"
          style={{ flex: '0 0 auto', padding: '8px 12px' }}
          onClick={() => setSearchOpen((previous) => !previous)}
          title="Buscar por nombre"
        >
          Buscar
        </button>
      </div>
      {chosenLabel && <p className="hint">{chosenLabel}</p>}

      {searchOpen && (
        <div className="picker-pop">
          <input
            autoFocus
            placeholder="Nombre del partner, o un id…"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
          {searching && <p className="hint">buscando…</p>}
          {!searching && matches.length === 0 && (
            <p className="hint">Sin resultados. El campo igual acepta cualquier id.</p>
          )}
          <ul>
            {matches.map((recipient) => (
              <li
                key={recipient.recipientId}
                onClick={() => {
                  onChange(recipient.recipientId);
                  setChosenLabel(
                    `${recipient.name}${recipient.province ? ` · ${recipient.province}` : ''}`,
                  );
                  setSearchOpen(false);
                }}
              >
                <span className="name">
                  {recipient.name}
                  {recipient.province ? ` · ${recipient.province}` : ''}
                </span>
                <span className="id">#{recipient.recipientId}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
