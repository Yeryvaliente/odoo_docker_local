#!/usr/bin/env python3
"""Banco de pruebas para las Optimizaciones 2 y 3 de ODOO-1393: índices en
sale_order.two_parent_id y sale_order.auto_purchase_order_id.

Reproduce en la BD local el peso de las dos búsquedas ORM (queries nº4 y nº5),
que hoy hacen Seq Scan por falta de índice, y mide el antes/después de crear los
índices — con los nombres EXACTOS que Odoo generará vía index=True
(<tabla>_<columna>_index), de modo que lo medido aquí sea lo que pasará en prod.

Todo lo sembrado se marca en sale_order.name con STRESS_TAG y se borra al final
(salvo --keep). Conexión: localhost:5432 db=odoo_18 (override con LOCAL_DB_URL).
"""

import argparse
import os
import statistics
import time

import psycopg2

DEFAULT_LOCAL_DB_URL = "postgresql://odoo:odoo@localhost:5432/odoo_18"
STRESS_TAG = "STRESSTEST_ODOO1393"

# Nombres que Odoo asigna a los índices de un campo con index=True.
INDEX_TWO_PARENT = "sale_order_two_parent_id_index"
INDEX_AUTO_PO = "sale_order_auto_purchase_order_id_index"

QUERY_CHILD_ORDERS = (
    'SELECT "sale_order"."id", "sale_order"."two_parent_id" FROM "sale_order" '
    'WHERE ("sale_order"."two_parent_id" IN (%s)) '
    'ORDER BY "sale_order"."date_order" DESC, "sale_order"."id" DESC'
)
QUERY_AUTO_PO = (
    'SELECT "sale_order"."id" FROM "sale_order" '
    'WHERE (("sale_order"."auto_purchase_order_id" IN (%s)) '
    'AND ("sale_order"."state" = \'sale\')) '
    'ORDER BY "sale_order"."date_order" DESC, "sale_order"."id" DESC'
)


def open_connection():
    connection = psycopg2.connect(
        os.environ.get("LOCAL_DB_URL", DEFAULT_LOCAL_DB_URL), connect_timeout=10
    )
    connection.autocommit = True
    return connection


def seed(cursor, how_many):
    # Semilla fija → dataset reproducible entre corridas (comparar ramas sin ruido).
    cursor.execute("SELECT setseed(0.42)")
    cursor.execute("SELECT id FROM sale_order WHERE name NOT LIKE %s ORDER BY id LIMIT 100",
                   (f"{STRESS_TAG}%",))
    parent_pool = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT id FROM purchase_order ORDER BY id LIMIT 100")
    purchase_pool = [row[0] for row in cursor.fetchall()]
    if not parent_pool or not purchase_pool:
        raise SystemExit("Faltan sale_order / purchase_order base para apuntar las FKs.")

    print(f"Sembrando {how_many:,} sale_order sintéticas…")
    cursor.execute("""
        INSERT INTO sale_order
            (company_id, partner_id, partner_invoice_id, partner_shipping_id,
             name, date_order, picking_policy, state,
             two_parent_id, auto_purchase_order_id)
        SELECT 1, 1, 1, 1,
               %s || '/' || series.n,
               now() - (random() * interval '365 days'),
               'direct',
               (ARRAY['sale','draft','sale','done','sale'])[1 + floor(random() * 5)::int],
               (%s::int[])[1 + floor(random() * array_length(%s::int[], 1))::int],
               (%s::int[])[1 + floor(random() * array_length(%s::int[], 1))::int]
        FROM generate_series(1, %s) AS series(n)
    """, (STRESS_TAG, parent_pool, parent_pool, purchase_pool, purchase_pool, how_many))
    print(f"  insertadas: {cursor.rowcount:,}")
    cursor.execute("ANALYZE sale_order")
    return parent_pool[0], purchase_pool[0]


def measure(cursor, sql_text, probe_value, runs, warmups):
    for _ in range(warmups):
        cursor.execute(sql_text, (probe_value,))
        cursor.fetchall()
    samples = []
    for _ in range(runs):
        start_time = time.perf_counter()
        cursor.execute(sql_text, (probe_value,))
        cursor.fetchall()
        samples.append((time.perf_counter() - start_time) * 1000)
    return statistics.median(samples), min(samples), max(samples)


def plan_first_node(cursor, sql_text, probe_value):
    cursor.execute("EXPLAIN " + sql_text, (probe_value,))
    for row in cursor.fetchall():
        line = row[0].strip()
        if "Scan" in line:
            return line
    return "(sin nodo de scan)"


def drop_indexes(cursor):
    cursor.execute(f"DROP INDEX IF EXISTS {INDEX_TWO_PARENT}")
    cursor.execute(f"DROP INDEX IF EXISTS {INDEX_AUTO_PO}")


def create_indexes(cursor):
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_TWO_PARENT} ON sale_order (two_parent_id)"
    )
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_AUTO_PO} ON sale_order (auto_purchase_order_id)"
    )
    cursor.execute("ANALYZE sale_order")


def cleanup(cursor):
    # Crear el índice de two_parent_id ANTES de borrar: el ondelete='set null'
    # dispara una verificación FK por cada fila borrada, que sin índice es un
    # seq scan (O(n²) en un borrado masivo → timeout). Con índice es instantáneo.
    # (Esto por sí solo ya justifica la Optimización 2.)
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_TWO_PARENT} ON sale_order (two_parent_id)"
    )
    cursor.execute("DELETE FROM sale_order WHERE name LIKE %s", (f"{STRESS_TAG}%",))
    deleted = cursor.rowcount
    drop_indexes(cursor)
    cursor.execute("ANALYZE sale_order")
    return deleted


def run_bench(cursor, parent_probe, purchase_probe, runs, warmups, label):
    child_median, child_min, child_max = measure(
        cursor, QUERY_CHILD_ORDERS, parent_probe, runs, warmups
    )
    auto_median, auto_min, auto_max = measure(
        cursor, QUERY_AUTO_PO, purchase_probe, runs, warmups
    )
    child_plan = plan_first_node(cursor, QUERY_CHILD_ORDERS, parent_probe)
    auto_plan = plan_first_node(cursor, QUERY_AUTO_PO, purchase_probe)
    print(f"\n[{label}]")
    print(f"  #4 two_parent_id       p50={child_median:7.2f}ms  ({child_plan})")
    print(f"  #5 auto_purchase_order p50={auto_median:7.2f}ms  ({auto_plan})")
    return child_median, auto_median


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=300000)
    parser.add_argument("--runs", type=int, default=15)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--keep", action="store_true", help="no borrar lo sembrado al final")
    args = parser.parse_args()

    connection = open_connection()
    cursor = connection.cursor()
    cursor.execute("SET statement_timeout = '120s'")
    try:
        drop_indexes(cursor)
        parent_probe, purchase_probe = seed(cursor, args.rows)

        child_before, auto_before = run_bench(
            cursor, parent_probe, purchase_probe, args.runs, args.warmups,
            "SIN índice (estado actual)",
        )
        create_indexes(cursor)
        child_after, auto_after = run_bench(
            cursor, parent_probe, purchase_probe, args.runs, args.warmups,
            "CON índice (index=True)",
        )

        print("\n=== A/B ===")
        print(f"  #4 two_parent_id:       {child_before:7.2f}ms → {child_after:7.2f}ms  "
              f"({child_before / child_after:.0f}× más rápido)")
        print(f"  #5 auto_purchase_order: {auto_before:7.2f}ms → {auto_after:7.2f}ms  "
              f"({auto_before / auto_after:.0f}× más rápido)")
    finally:
        if not args.keep:
            deleted = cleanup(cursor)
            print(f"\nLimpieza: {deleted:,} sale_order sintéticas borradas + índices de prueba.")
        else:
            print("\n--keep: se conservan datos e índices de prueba.")
    connection.close()


if __name__ == "__main__":
    main()
