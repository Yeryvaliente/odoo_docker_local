#!/usr/bin/env python3
"""Benchmark READ-ONLY contra la BD de test (datos reales, SIN el código de
optimización de ODOO-1393).

Mide las tres queries tal como corren hoy en main/test y, para la #1, ejecuta
además la variante reescrita (ambas son SELECT, no tocan la BD) para:
  - comparar el tiempo sobre datos reales, y
  - VERIFICAR que original y reescrita devuelven filas idénticas (correctitud).

NO escribe nada: sin seed, sin CREATE INDEX, sin DELETE. La sesión va con
readonly=True, así que cualquier intento de escritura fallaría.

Las queries #4/#5 solo se miden en su forma actual (Seq Scan, sin índice), que
es justo lo que hay en test. El "con índice" no se puede medir aquí sin crear el
índice (escritura); ese número está en el benchmark local (sale_order_index_stress.py).

Conexión: $ODOO_TEST_DATABASE_URL con el dbname corregido a 'odoo' (igual que el
comando /bd-test). Requiere VPN activa.

Uso:
    python3 test_readonly_bench.py [--runs 20] [--products 400]
"""

import argparse
import os
import re
import statistics
import sys
import time

import psycopg2
import psycopg2.extras

from stock_query_stress import CATALOG_STOCK_SQL, CATALOG_STOCK_SQL_REWRITE

PENDING_STATES = ("waiting", "confirmed", "assigned", "partially_available")

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


def open_test_connection():
    connection_url = os.environ.get("ODOO_TEST_DATABASE_URL")
    if not connection_url:
        sys.exit("Falta ODOO_TEST_DATABASE_URL (source ~/.claude/secrets.env, VPN activa).")
    connection_url = re.sub(r"/([^/?]+)(\?|$)", r"/odoo\2", connection_url)
    connection = psycopg2.connect(connection_url, connect_timeout=15)
    connection.set_session(readonly=True, autocommit=True)
    return connection


def measure(cursor, sql_text, parameters, runs, warmups):
    for _ in range(warmups):
        cursor.execute(sql_text, parameters)
        cursor.fetchall()
    samples = []
    for _ in range(runs):
        start_time = time.perf_counter()
        cursor.execute(sql_text, parameters)
        cursor.fetchall()
        samples.append((time.perf_counter() - start_time) * 1000)
    return statistics.median(samples)


def first_scan_node(cursor, sql_text, parameters):
    cursor.execute("EXPLAIN " + sql_text, parameters)
    for row in cursor.fetchall():
        text = row[0].strip()
        if "Scan" in text:
            return text
    return "(sin nodo de scan)"


def discover_stock_params(cursor, warehouse_count, product_count):
    cursor.execute("""
        SELECT sw.id
        FROM stock_warehouse sw
        JOIN stock_location wl ON wl.id = sw.lot_stock_id
        JOIN stock_location sl ON (sl.id = wl.id OR sl.parent_path LIKE wl.parent_path || '%%')
        JOIN stock_quant sq ON sq.location_id = sl.id AND sq.quantity > 0
        WHERE sl.usage = 'internal'
        GROUP BY sw.id
        ORDER BY count(sq.id) DESC
        LIMIT %s
    """, (warehouse_count,))
    warehouse_ids = [row[0] for row in cursor.fetchall()]
    if not warehouse_ids:
        return [], []

    cursor.execute("""
        SELECT DISTINCT sq.product_id
        FROM stock_quant sq
        JOIN stock_location sl ON sl.id = sq.location_id
        WHERE sl.usage = 'internal' AND sq.quantity > 0
          AND EXISTS (
              SELECT 1 FROM stock_warehouse sw
              JOIN stock_location wl ON wl.id = sw.lot_stock_id
              WHERE sw.id = ANY(%s)
                AND (sl.id = wl.id OR sl.parent_path LIKE wl.parent_path || '%%')
          )
        ORDER BY sq.product_id
        LIMIT %s
    """, (warehouse_ids, product_count))
    product_ids = [row[0] for row in cursor.fetchall()]
    return warehouse_ids, product_ids


def incoming_type_ids(cursor):
    cursor.execute("SELECT id FROM stock_picking_type WHERE code = 'incoming'")
    return [row[0] for row in cursor.fetchall()]


def bench_stock(cursor, runs, warmups, product_count):
    print("\n" + "=" * 70)
    print("OPTIMIZACIÓN 1 — query de stock del catálogo (datos reales de test)")
    print("=" * 70)
    warehouse_ids, product_ids = discover_stock_params(cursor, 6, product_count)
    if not product_ids:
        print("  Sin warehouses/productos con stock en test — se omite.")
        return
    print(f"  Parámetros reales: {len(warehouse_ids)} almacenes, {len(product_ids)} productos con stock.")

    incoming_ids = incoming_type_ids(cursor)
    params_original = (warehouse_ids, product_ids, product_ids, product_ids)
    params_rewrite = (warehouse_ids, product_ids, product_ids, incoming_ids, product_ids)

    # Correctitud sobre datos reales: filas idénticas entre original y reescrita.
    cursor.execute(CATALOG_STOCK_SQL, params_original)
    rows_original = {tuple(r) for r in cursor.fetchall()}
    cursor.execute(CATALOG_STOCK_SQL_REWRITE, params_rewrite)
    rows_rewrite = {tuple(r) for r in cursor.fetchall()}
    only_original = rows_original - rows_rewrite
    only_rewrite = rows_rewrite - rows_original
    if not only_original and not only_rewrite:
        print(f"  Correctitud: OK — {len(rows_original)} filas IDÉNTICAS (original == reescrita).")
    else:
        print(f"  Correctitud: DIFIEREN — solo original {len(only_original)}, "
              f"solo rewrite {len(only_rewrite)}")
        for row in list(only_original)[:5]:
            print(f"      solo original: {row}")
        for row in list(only_rewrite)[:5]:
            print(f"      solo rewrite:  {row}")

    original_ms = measure(cursor, CATALOG_STOCK_SQL, params_original, runs, warmups)
    rewrite_ms = measure(cursor, CATALOG_STOCK_SQL_REWRITE, params_rewrite, runs, warmups)
    speedup = original_ms / rewrite_ms if rewrite_ms else 0
    print(f"\n  main (original, anti-join)   p50 = {original_ms:8.2f} ms")
    print(f"  rama (rewrite picking_type)  p50 = {rewrite_ms:8.2f} ms   ({speedup:.1f}× más rápido)")


def bench_search(cursor, runs, warmups):
    print("\n" + "=" * 70)
    print("OPTIMIZACIONES 2 y 3 — búsquedas sale_order (baseline actual de test)")
    print("=" * 70)

    cursor.execute("""
        SELECT two_parent_id FROM sale_order
        WHERE two_parent_id IS NOT NULL
        GROUP BY two_parent_id ORDER BY count(*) DESC LIMIT 1
    """)
    parent_row = cursor.fetchone()
    if parent_row:
        parent_probe = parent_row[0]
        child_ms = measure(cursor, QUERY_CHILD_ORDERS, (parent_probe,), runs, warmups)
        child_plan = first_scan_node(cursor, QUERY_CHILD_ORDERS, (parent_probe,))
        print(f"\n  #4 two_parent_id (parent {parent_probe})   p50 = {child_ms:7.2f} ms   ({child_plan})")
    else:
        print("\n  #4 two_parent_id: sin datos.")

    cursor.execute("""
        SELECT auto_purchase_order_id FROM sale_order
        WHERE auto_purchase_order_id IS NOT NULL AND state = 'sale'
        GROUP BY auto_purchase_order_id ORDER BY count(*) DESC LIMIT 1
    """)
    auto_row = cursor.fetchone()
    if auto_row:
        auto_probe = auto_row[0]
        auto_ms = measure(cursor, QUERY_AUTO_PO, (auto_probe,), runs, warmups)
        auto_plan = first_scan_node(cursor, QUERY_AUTO_PO, (auto_probe,))
        print(f"  #5 auto_purchase_order_id (PO {auto_probe})  p50 = {auto_ms:7.2f} ms   ({auto_plan})")
    else:
        print("  #5 auto_purchase_order_id: sin datos.")
    print("\n  (El 'con índice' no se mide en test — sería escritura. Ver benchmark local: 8-9×.)")


def report_divergence(cursor):
    print("\n" + "=" * 70)
    print("DIVERGENCIA de la Optimización 1 sobre datos reales de test")
    print("=" * 70)
    cursor.execute("""
        SELECT count(*) FROM stock_move sm
        JOIN stock_picking_type spt ON spt.id = sm.picking_type_id
        WHERE sm.picking_id IS NULL AND spt.code = 'incoming'
          AND sm.state IN ('waiting','confirmed','assigned','partially_available')
    """)
    no_picking_incoming = cursor.fetchone()[0]
    cursor.execute("""
        SELECT count(*) FROM stock_move sm
        WHERE sm.picking_id IS NOT NULL
          AND sm.picking_type_id IS DISTINCT FROM
              (SELECT picking_type_id FROM stock_picking WHERE id = sm.picking_id)
    """)
    desynced = cursor.fetchone()[0]
    print(f"  moves entrantes pendientes SIN albarán con tipo incoming: {no_picking_incoming}")
    print(f"  moves con albarán y picking_type_id desincronizado:       {desynced}")
    print("  (Ambos ~0 → la reescritura es equivalente; los que difieran se verían")
    print("   en la comprobación de correctitud de arriba.)")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=4)
    parser.add_argument("--products", type=int, default=400)
    args = parser.parse_args()

    connection = open_test_connection()
    cursor = connection.cursor()
    cursor.execute("SET statement_timeout = '60s'")
    cursor.execute("SET application_name = 'claude_odoo1393_readonly_bench'")
    print("Conectado a la BD de test (READ-ONLY).")

    bench_stock(cursor, args.runs, args.warmups, args.products)
    bench_search(cursor, args.runs, args.warmups)
    report_divergence(cursor)

    connection.close()
    print("\nHecho. Nada fue modificado en test (sesión read-only).")


if __name__ == "__main__":
    main()
