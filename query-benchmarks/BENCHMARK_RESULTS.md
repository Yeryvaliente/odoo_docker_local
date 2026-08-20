# ODOO-1393 — Benchmark de optimizaciones de queries

- **Fecha:** 2026-07-07
- **Rama:** feature/ODOO-1393-optimize-high-traffic-queries
- **BD:** local `odoo_18` (localhost:5432)
- **Seed:** `setseed(0.42)` → dataset sintético determinista (reproducible entre corridas)
- **Método:** cada harness ejecuta la SQL real de cada query N veces (p50 de 15 runs, 3-5 warmups)

> NOTA CLAVE: estos harness prueban las queries **directamente** (la SQL, no el código
> del addon vía ORM), y en cada corrida miden AMBOS lados de la optimización. Por eso:
>   - la columna **"antes / SIN"** == el estado de **main** (sin optimizar)
>   - la columna **"después / CON"** == esta rama (optimizada)
> Correr el mismo harness estando en main da los mismos números (el harness no depende
> de la rama de git). La comparación optimizado-vs-main ya está en estas tablas.

---

## Optimización 1 — twonary_mercado: reescribir `_compute_catalog_stock_by_variant`

Anti-join a `stock_picking` (excluir vendor receipts) → filtro directo por `stock_move.picking_type_id`.

- **Dataset:** ~2.5M `stock_move` (480k incoming pendientes + 96k outgoing pendientes + 1.92M done), 6 almacenes, 400 productos. Proporción 80/20 done/pending (prod-like).
- **Comando:** `python3 stock_query_stress.py full --reset --runs 15`
- **Correctitud:** `verify` → 84 y 2400 filas IDÉNTICAS entre original y reescrita.

| forma | main (original) p50 | rama (rewrite) p50 | mejora |
|---|---|---|---|
| query grande (400 productos) | 740.4 ms | 269.2 ms | **2.8× / −64%** |
| query 14 productos (kits) | 24.1 ms | 10.3 ms | **2.4× / −57%** |

(Añadir índices a la reescritura solo aporta ~3-4% marginal → descartado.)

---

## Optimización 2 — twonary_envios: `index=True` en `sale_order.two_parent_id`

Query #4: `WHERE two_parent_id IN (...) ORDER BY date_order DESC, id DESC` (búsqueda de órdenes hijas).

- **Dataset:** 300.000 `sale_order` sintéticas.
- **Comando:** `python3 sale_order_index_stress.py --rows 300000 --runs 15`

| query | main (sin índice) p50 | rama (con índice) p50 | mejora |
|---|---|---|---|
| #4 two_parent_id | 16.7 ms (Seq Scan) | 2.1 ms (Bitmap Heap Scan) | **8×** |

Bonus: el índice también acelera el `ondelete='set null'` en cascada (verificación FK).

---

## Optimización 3 — twonary_inter_company_rules: `index=True` en `sale_order.auto_purchase_order_id`

Query #5: `WHERE auto_purchase_order_id IN (...) AND state='sale' ORDER BY date_order DESC, id DESC`.

- **Dataset:** mismas 300.000 `sale_order` sintéticas.
- **Comando:** `python3 sale_order_index_stress.py --rows 300000 --runs 15`

| query | main (sin índice) p50 | rama (con índice) p50 | mejora |
|---|---|---|---|
| #5 auto_purchase_order_id | 13.3 ms (Seq Scan) | 1.4 ms (Bitmap Heap Scan) | **9×** |

---

## Resumen

| Optimización | main | rama | mejora |
|---|---|---|---|
| #1 stock catálogo (400 prod) | 740 ms | 269 ms | 2.8× |
| #1 stock catálogo (14 prod) | 24 ms | 10 ms | 2.4× |
| #2 index two_parent_id | 16.7 ms | 2.1 ms | 8× |
| #3 index auto_purchase_order_id | 13.3 ms | 1.4 ms | 9× |

En prod la mejora de #1 puede ser mayor (allá el anti-join usa hash+seq-scan sobre
`stock_picking` de ~1M filas; en local fue nested-loop). #2 y #3 escalan con el tamaño
real de `sale_order`.

---

## Corrida contra la BD de test (read-only, datos reales) — 2026-07-07

Comando: `python3 test_readonly_bench.py --runs 20`. Test: ~67k `stock_move`, ~3.2k `sale_order`.

- **Correctitud Opt 1:** original vs reescrita → **400 filas IDÉNTICAS** sobre datos
  reales de test. Confirma la equivalencia con datos de producción, incluidos los
  4 moves con `picking_type_id` desincronizado (no afectan el resultado del catálogo).
- **Divergencia Opt 1:** moves entrantes pendientes sin albarán con tipo incoming = **0**;
  moves con albarán y `picking_type_id` desincronizado = **4** (irrelevantes: la
  correctitud fila-por-fila da idéntico).
- **Plan #4/#5:** ambas hacen **Seq Scan** en test (sin índice), como se esperaba.

**Los tiempos contra test NO son representativos del peso** (bajo volumen + latencia
de VPN ~100ms que domina): Opt 1 dio ~120ms en ambas variantes, y #4/#5 ~105ms
(mayormente red). El peso real está en las tablas de arriba (seed local con volumen)
y se confirmará en prod con EXPLAIN. Valor de test = correctitud + plan, no cronómetro.
