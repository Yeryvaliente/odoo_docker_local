import { useEffect, useRef, useState } from 'react';

import { searchProducts } from '../api.ts';
import type { MercadoProduct } from '../types.ts';

interface ProductPickerProps {
  chosen: MercadoProduct | null;
  onChoose: (product: MercadoProduct) => void;
}

/**
 * Buscador con autocompletar sobre los productos publicados en Mercado
 * (`product_template.two_mercado_ok`). Acepta nombre o id exacto — pegar un id
 * del catálogo es el caso más común cuando se reproduce un pedido real.
 */
export function ProductPicker({ chosen, onChoose }: ProductPickerProps) {
  const [open, setOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [matches, setMatches] = useState<MercadoProduct[]>([]);
  const [searching, setSearching] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      setSearching(true);
      searchProducts(searchTerm)
        .then(setMatches)
        .catch(() => setMatches([]))
        .finally(() => setSearching(false));
    }, 220);
    return () => clearTimeout(timer);
  }, [open, searchTerm]);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [open]);

  return (
    <div className="picker" ref={containerRef}>
      <div
        className="picker-chosen"
        role="button"
        tabIndex={0}
        onClick={() => setOpen((previous) => !previous)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') setOpen((previous) => !previous);
        }}
      >
        <span className="name">{chosen ? chosen.name : 'Elegir producto…'}</span>
        <span className="id">{chosen ? `#${chosen.productId} · $${chosen.listPrice}` : '▾'}</span>
      </div>

      {open && (
        <div className="picker-pop">
          <input
            autoFocus
            placeholder="Buscar por nombre o pegar un id…"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
          {searching && <p className="hint">buscando…</p>}
          {!searching && matches.length === 0 && (
            <p className="hint">Sin resultados publicados en Mercado.</p>
          )}
          <ul>
            {matches.map((product) => (
              <li
                key={product.productId}
                onClick={() => {
                  onChoose(product);
                  setOpen(false);
                }}
              >
                <span className="name">{product.name}</span>
                <span className="id">
                  #{product.productId} · ${product.listPrice}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
