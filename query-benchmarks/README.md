# query-benchmarks — ODOO-1393

Bancos de prueba para las optimizaciones de queries de alto tráfico (ODOO-1393):

1. **Opt 1** — reescritura de la query de stock del catálogo (`twonary_mercado`,
   `_compute_catalog_stock_by_variant`): anti-join a `stock_picking` → filtro por
   `stock_move.picking_type_id`.
2. **Opt 2** — `index=True` en `sale_order.two_parent_id` (`twonary_envios`).
3. **Opt 3** — `index=True` en `sale_order.auto_purchase_order_id` (`twonary_inter_company_rules`).

## Archivos

| Archivo | BD | Escribe | Qué hace |
|---|---|---|---|
| `stock_query_stress.py` | local `odoo_18` | **SÍ** (seed/índices/borra) | A/B de la Opt 1 con datos sintéticos prod-like |
| `sale_order_index_stress.py` | local `odoo_18` | **SÍ** (seed/índices/borra) | A/B de las Opt 2 y 3 con 300k SO sintéticas |
| `test_readonly_bench.py` | **test** | NO (read-only) | Mide sobre datos reales de test + verifica correctitud |
| `BENCHMARK_RESULTS.md` | — | — | Resultados registrados |

## Requisitos

- Python con `psycopg2` (ya disponible en el entorno).
- Los scripts **locales** apuntan a `localhost:5432/odoo_18` (override con `LOCAL_DB_URL`).
  Siembran datos sintéticos marcados y los limpian al terminar; seguros en local.
- El script de **test** usa `$ODOO_TEST_DATABASE_URL` (corrige el dbname a `odoo`,
  igual que el comando `/bd-test`) y **requiere VPN activa**. Es estrictamente
  read-only: sesión `readonly=True`, sin seed, sin índices, sin delete.

  ```bash
  source ~/.claude/secrets.env   # carga ODOO_TEST_DATABASE_URL
  ```

## Uso

```bash
# Opt 1 (local, siembra ~2.5M moves prod-like, A/B baseline vs rewrite):
python3 stock_query_stress.py full --reset --runs 15
python3 stock_query_stress.py compare            # ver el A/B guardado

# Opt 2 y 3 (local, siembra 300k SO, A/B sin índice vs con índice):
python3 sale_order_index_stress.py --rows 300000 --runs 15

# Contra test (read-only, datos reales, requiere VPN):
python3 test_readonly_bench.py --runs 20

# Limpieza manual del seed de stock (si quedó puesto):
python3 stock_query_stress.py cleanup --drop-indexes
```

## Nota sobre medir contra test

Test tiene **poco volumen** (decenas de miles de moves, ~3k SO) y se accede **por
VPN**. Por eso los tiempos absolutos contra test están dominados por la latencia de
red y no reflejan el peso real de las queries. Contra test lo valioso es:
- **correctitud** (que la reescritura devuelva filas idénticas sobre datos reales), y
- **confirmar el plan** (que #4/#5 hacen Seq Scan sin índice).

El **peso** (la mejora en ms) se ve con volumen: los scripts locales con seed
sintético prod-like, o midiendo en prod con `EXPLAIN (ANALYZE, BUFFERS)`.

Semilla del seed sintético: `setseed(0.42)` → dataset determinista y reproducible.
