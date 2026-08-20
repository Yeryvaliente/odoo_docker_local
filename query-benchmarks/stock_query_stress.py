#!/usr/bin/env python3
"""Banco de pruebas A/B para la query de stock del catálogo Mercado (local).

Reproduce en la BD LOCAL el peso que la query
``_compute_catalog_stock_by_variant`` tiene en producción, para medir el antes
y el después de una optimización (índices parciales / reescritura) de forma
repetible.

Por qué hace falta sembrar: la BD local tiene la estructura (productos,
almacenes, ubicaciones) pero casi ningún ``stock_move`` ni ``stock_quant``.
El cuello de botella de prod solo aparece con volumen (leer decenas de miles
de moves pendientes por producto + anti-join contra un ``stock_picking``
grande), así que primero se siembran datos sintéticos MARCADOS y luego se mide.

Todos los datos sembrados llevan el prefijo STRESS_TAG en ``stock_move.name`` /
``stock_picking.name`` para poder borrarlos con el modo ``cleanup`` sin tocar
nada real.

Modos (ver ``--help``):
    status   volumen actual de las tablas relevantes
    seed     siembra datos sintéticos prod-like (idempotente con --reset)
    bench    corre la query N veces, reporta latencias + EXPLAIN, guarda a JSON
    index    crea / borra los índices parciales propuestos
    compare  muestra todas las corridas guardadas lado a lado con el delta
    cleanup  borra todo lo sembrado (y opcionalmente los índices)
    full     seed (si falta) -> bench baseline -> index -> bench optimizado -> compare

Conexión: localhost:5432 db=odoo user=odoo pass=odoo (override con LOCAL_DB_URL).
"""

import argparse
import json
import os
import re
import statistics
import sys
import time

import psycopg2
import psycopg2.extras

DEFAULT_LOCAL_DB_URL = "postgresql://odoo:odoo@localhost:5432/odoo_18"
SCRATCHPAD_DIR = os.path.dirname(os.path.abspath(__file__))
TARGETS_PATH = os.path.join(SCRATCHPAD_DIR, "stress_targets.json")
RESULTS_PATH = os.path.join(SCRATCHPAD_DIR, "stress_results.json")
PLAN_DIR = os.path.join(SCRATCHPAD_DIR, "stress_plans")

STRESS_TAG = "STRESSTEST"
PENDING_STATES = ("waiting", "confirmed", "assigned", "partially_available")

# Los dos índices parciales propuestos (capa 2 del plan de optimización).
# En local se crean sin CONCURRENTLY (no hay tráfico); en prod van con
# CONCURRENTLY a mano — este script solo sirve para medir el efecto.
PROPOSED_INDEXES = {
    # product_id primero (alta selectividad) + parcial sobre estados pendientes,
    # para que ante un historial grande de moves 'done' el índice traiga solo los
    # pendientes del producto sin tocar el resto. Uno orientado al CTE incoming
    # (filtra por location_dest_id) y otro al outgoing (location_id).
    "stress_stock_move_pending_dest_idx": (
        "CREATE INDEX stress_stock_move_pending_dest_idx "
        "ON stock_move (product_id, location_dest_id) "
        "WHERE state IN ('waiting','confirmed','assigned','partially_available')"
    ),
    "stress_stock_move_pending_src_idx": (
        "CREATE INDEX stress_stock_move_pending_src_idx "
        "ON stock_move (product_id, location_id) "
        "WHERE state IN ('waiting','confirmed','assigned','partially_available')"
    ),
}


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------
def open_connection(read_only):
    connection_url = os.environ.get("LOCAL_DB_URL", DEFAULT_LOCAL_DB_URL)
    connection = psycopg2.connect(connection_url, connect_timeout=10)
    connection.set_session(readonly=read_only, autocommit=not read_only)
    return connection


# ---------------------------------------------------------------------------
# La query objetivo (idéntica en forma a _compute_catalog_stock_by_variant),
# parametrizada con = ANY(%s) para no interpolar nunca IDs en el texto SQL.
# El orden de parámetros es: warehouse_ids, product_ids, product_ids, product_ids.
# ---------------------------------------------------------------------------
CATALOG_STOCK_SQL = """
    WITH warehouse_locations AS (
        SELECT sw.id AS warehouse_id, sw.company_id, sl.id AS location_id
        FROM stock_warehouse sw
        JOIN stock_location wh_loc ON wh_loc.id = sw.lot_stock_id
        JOIN stock_location sl ON (
            sl.id = wh_loc.id
            OR sl.parent_path LIKE wh_loc.parent_path || '%%'
        )
        WHERE sl.usage = 'internal'
          AND sw.id = ANY(%s)
    ),
    outgoing_moves AS (
        SELECT wl.warehouse_id, sm.product_id,
               COALESCE(SUM(sm.product_qty), 0) AS outgoing_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_id = wl.location_id
            AND sm.product_id = ANY(%s)
            AND sm.state IN ('waiting', 'confirmed', 'assigned', 'partially_available')
            AND NOT EXISTS (
                SELECT 1 FROM warehouse_locations wl2
                WHERE wl2.warehouse_id = wl.warehouse_id
                  AND wl2.location_id = sm.location_dest_id
            )
        GROUP BY wl.warehouse_id, sm.product_id
    ),
    all_incoming_moves AS (
        SELECT wl.warehouse_id, sm.product_id,
               COALESCE(SUM(sm.product_qty), 0) AS all_incoming_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_dest_id = wl.location_id
            AND sm.product_id = ANY(%s)
            AND sm.state IN ('waiting', 'confirmed', 'assigned', 'partially_available')
            AND NOT EXISTS (
                SELECT 1 FROM warehouse_locations wl2
                WHERE wl2.warehouse_id = wl.warehouse_id
                  AND wl2.location_id = sm.location_id
            )
            AND NOT EXISTS (
                SELECT 1
                FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE sp.id = sm.picking_id
                  AND spt.code = 'incoming'
            )
        GROUP BY wl.warehouse_id, sm.product_id
    )
    SELECT sq.product_id, wl.warehouse_id, wl.company_id,
           COALESCE(SUM(sq.quantity), 0)
               - COALESCE(MAX(om.outgoing_qty), 0)
               + COALESCE(MAX(aim.all_incoming_qty), 0) AS virtual_available
    FROM warehouse_locations wl
    JOIN stock_quant sq ON sq.location_id = wl.location_id
        AND sq.product_id = ANY(%s)
    LEFT JOIN outgoing_moves om
        ON om.warehouse_id = wl.warehouse_id AND om.product_id = sq.product_id
    LEFT JOIN all_incoming_moves aim
        ON aim.warehouse_id = wl.warehouse_id AND aim.product_id = sq.product_id
    GROUP BY sq.product_id, wl.warehouse_id, wl.company_id
    HAVING COALESCE(SUM(sq.quantity), 0) > 0
        OR COALESCE(MAX(om.outgoing_qty), 0) > 0
        OR COALESCE(MAX(aim.all_incoming_qty), 0) > 0
"""

# Variante REESCRITA: reemplaza el anti-join contra stock_picking (para excluir
# recibos de vendor) por un filtro directo sobre stock_move.picking_type_id, que
# está almacenado (store=True en upstream). Elimina el JOIN a stock_picking +
# stock_picking_type que en el plan de prod costaba ~378ms (Parallel Hash sobre
# 1M pickings) y en el seed local 2.88M buffers de nested-loop lookups.
# Orden de parámetros: warehouse_ids, pids(out), pids(in), incoming_type_ids, pids(quant).
CATALOG_STOCK_SQL_REWRITE = """
    WITH warehouse_locations AS (
        SELECT sw.id AS warehouse_id, sw.company_id, sl.id AS location_id
        FROM stock_warehouse sw
        JOIN stock_location wh_loc ON wh_loc.id = sw.lot_stock_id
        JOIN stock_location sl ON (
            sl.id = wh_loc.id
            OR sl.parent_path LIKE wh_loc.parent_path || '%%'
        )
        WHERE sl.usage = 'internal'
          AND sw.id = ANY(%s)
    ),
    outgoing_moves AS (
        SELECT wl.warehouse_id, sm.product_id,
               COALESCE(SUM(sm.product_qty), 0) AS outgoing_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_id = wl.location_id
            AND sm.product_id = ANY(%s)
            AND sm.state IN ('waiting', 'confirmed', 'assigned', 'partially_available')
            AND NOT EXISTS (
                SELECT 1 FROM warehouse_locations wl2
                WHERE wl2.warehouse_id = wl.warehouse_id
                  AND wl2.location_id = sm.location_dest_id
            )
        GROUP BY wl.warehouse_id, sm.product_id
    ),
    all_incoming_moves AS (
        SELECT wl.warehouse_id, sm.product_id,
               COALESCE(SUM(sm.product_qty), 0) AS all_incoming_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_dest_id = wl.location_id
            AND sm.product_id = ANY(%s)
            AND sm.state IN ('waiting', 'confirmed', 'assigned', 'partially_available')
            AND NOT EXISTS (
                SELECT 1 FROM warehouse_locations wl2
                WHERE wl2.warehouse_id = wl.warehouse_id
                  AND wl2.location_id = sm.location_id
            )
            AND (sm.picking_id IS NULL OR sm.picking_type_id != ALL(%s::int[]))
        GROUP BY wl.warehouse_id, sm.product_id
    )
    SELECT sq.product_id, wl.warehouse_id, wl.company_id,
           COALESCE(SUM(sq.quantity), 0)
               - COALESCE(MAX(om.outgoing_qty), 0)
               + COALESCE(MAX(aim.all_incoming_qty), 0) AS virtual_available
    FROM warehouse_locations wl
    JOIN stock_quant sq ON sq.location_id = wl.location_id
        AND sq.product_id = ANY(%s)
    LEFT JOIN outgoing_moves om
        ON om.warehouse_id = wl.warehouse_id AND om.product_id = sq.product_id
    LEFT JOIN all_incoming_moves aim
        ON aim.warehouse_id = wl.warehouse_id AND aim.product_id = sq.product_id
    GROUP BY sq.product_id, wl.warehouse_id, wl.company_id
    HAVING COALESCE(SUM(sq.quantity), 0) > 0
        OR COALESCE(MAX(om.outgoing_qty), 0) > 0
        OR COALESCE(MAX(aim.all_incoming_qty), 0) > 0
"""


def _incoming_picking_type_ids(cursor):
    cursor.execute("SELECT id FROM stock_picking_type WHERE code = 'incoming'")
    return [row[0] for row in cursor.fetchall()]


def _build_query(variant, cursor, warehouse_ids, product_ids):
    """Devuelve (sql_text, params) para la variante pedida."""
    if variant == "rewrite":
        incoming_type_ids = _incoming_picking_type_ids(cursor)
        params = (warehouse_ids, product_ids, product_ids, incoming_type_ids, product_ids)
        return CATALOG_STOCK_SQL_REWRITE, params
    params = (warehouse_ids, product_ids, product_ids, product_ids)
    return CATALOG_STOCK_SQL, params


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
def command_status(_args):
    connection = open_connection(read_only=True)
    cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("""
        SELECT
            (SELECT count(*) FROM stock_move) AS moves_total,
            (SELECT count(*) FROM stock_move
                WHERE state IN ('waiting','confirmed','assigned','partially_available')) AS moves_pending,
            (SELECT count(*) FROM stock_move WHERE name LIKE %s) AS moves_stress,
            (SELECT count(*) FROM stock_quant) AS quants_total,
            (SELECT count(*) FROM stock_quant WHERE in_date IS NOT NULL) AS quants_with_date,
            (SELECT count(*) FROM stock_picking WHERE name LIKE %s) AS pickings_stress,
            (SELECT count(*) FROM pg_indexes
                WHERE indexname LIKE 'stress_%%') AS proposed_indexes_present
    """, (f"{STRESS_TAG}%", f"{STRESS_TAG}%"))
    snapshot = cursor.fetchone()
    connection.close()

    print("Estado de la BD local")
    print("-" * 50)
    for column_name, column_value in snapshot.items():
        print(f"  {column_name:24} {column_value}")
    if os.path.exists(TARGETS_PATH):
        with open(TARGETS_PATH) as targets_file:
            targets = json.load(targets_file)
        print(f"\n  targets sembrados: {len(targets['product_ids'])} productos, "
              f"{len(targets['warehouse_ids'])} almacenes")
    else:
        print("\n  (sin targets sembrados todavía — corre 'seed')")


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------
def _resolve_external_location(cursor, usage_kind, fallback_name):
    """Devuelve el id de una ubicación NO interna (proveedor/cliente) para usar
    como origen de incoming / destino de outgoing. La crea marcada si no existe."""
    cursor.execute(
        "SELECT id FROM stock_location WHERE usage = %s ORDER BY id LIMIT 1",
        (usage_kind,),
    )
    existing_row = cursor.fetchone()
    if existing_row:
        return existing_row[0]
    cursor.execute("""
        INSERT INTO stock_location (name, usage, parent_path, complete_name)
        VALUES (%s, %s, '0/', %s) RETURNING id
    """, (f"{STRESS_TAG} {fallback_name}", usage_kind, f"{STRESS_TAG} {fallback_name}"))
    return cursor.fetchone()[0]


def command_seed(args):
    connection = open_connection(read_only=False)
    cursor = connection.cursor()

    # Semilla fija: el dataset sintético es idéntico entre corridas, de modo que
    # los números sean comparables (p.ej. esta rama vs main) sin ruido aleatorio.
    cursor.execute("SELECT setseed(0.42)")

    if args.reset:
        print("Limpiando datos STRESSTEST previos…")
        _delete_seeded_rows(cursor)

    # 1. Almacenes objetivo: los primeros N con lot_stock interno.
    cursor.execute("""
        SELECT sw.id, sw.company_id, sw.lot_stock_id
        FROM stock_warehouse sw
        JOIN stock_location wh_loc ON wh_loc.id = sw.lot_stock_id
        WHERE wh_loc.usage = 'internal'
        ORDER BY sw.id
        LIMIT %s
    """, (args.warehouses,))
    warehouse_rows = cursor.fetchall()
    if len(warehouse_rows) < 2:
        sys.exit("No hay suficientes almacenes con lot_stock interno en local.")
    warehouse_ids = [row[0] for row in warehouse_rows]

    # 2. Productos objetivo: activos y almacenables.
    cursor.execute("""
        SELECT pp.id
        FROM product_product pp
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE pp.active = true AND pt.is_storable = true
        ORDER BY pp.id
        LIMIT %s
    """, (args.target_products,))
    product_ids = [row[0] for row in cursor.fetchall()]
    if len(product_ids) < 14:
        sys.exit("No hay suficientes productos almacenables en local.")

    # 3. Ubicaciones externas + uom por defecto.
    supplier_location_id = _resolve_external_location(cursor, "supplier", "Vendors")
    customer_location_id = _resolve_external_location(cursor, "customer", "Customers")
    cursor.execute("SELECT id FROM uom_uom ORDER BY id LIMIT 1")
    default_uom_id = cursor.fetchone()[0]

    # 4. picking types: uno incoming (para ejercitar el anti-join) y uno no-incoming.
    cursor.execute("SELECT id FROM stock_picking_type WHERE code = 'incoming' ORDER BY id LIMIT 1")
    incoming_type_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM stock_picking_type WHERE code != 'incoming' ORDER BY id LIMIT 1")
    non_incoming_type_id = cursor.fetchone()[0]

    # 5. Pickings sintéticos: mitad incoming, mitad no. Los moves los referencian
    #    al azar, así el anti-join filtra una fracción (como en prod).
    print(f"Sembrando {args.pickings} pickings…")
    incoming_picking_ids = _seed_pickings(
        cursor, args.pickings // 2, incoming_type_id,
        supplier_location_id, warehouse_rows[0][2], "IN",
    )
    other_picking_ids = _seed_pickings(
        cursor, args.pickings - args.pickings // 2, non_incoming_type_id,
        warehouse_rows[0][2], customer_location_id, "OUT",
    )
    all_picking_ids = incoming_picking_ids + other_picking_ids

    # 6. Moves pendientes por almacén + historial 'done' + quants.
    #    Incoming se divide en dos para que la variante reescrita (filtra por
    #    picking_type_id) sea EQUIVALENTE a la original (anti-join por picking_id):
    #      - vendor receipts (~40%): picking incoming + picking_type_id incoming
    #        → EXCLUIDOS por ambas variantes.
    #      - resupply (~60%): picking no-incoming + picking_type_id no-incoming
    #        → CONTADOS por ambas variantes.
    total_incoming = 0
    total_outgoing = 0
    total_done = 0
    vendor_share = args.moves_per_product * 2 // 5
    resupply_share = args.moves_per_product - vendor_share
    for warehouse_id, company_id, lot_stock_id in warehouse_rows:
        total_incoming += _seed_incoming_moves(
            cursor, product_ids, vendor_share, company_id, default_uom_id,
            supplier_location_id, lot_stock_id, incoming_picking_ids, incoming_type_id,
        )
        total_incoming += _seed_incoming_moves(
            cursor, product_ids, resupply_share, company_id, default_uom_id,
            supplier_location_id, lot_stock_id, other_picking_ids, non_incoming_type_id,
        )
        outgoing_per_product = max(1, args.moves_per_product // 5)
        total_outgoing += _seed_outgoing_moves(
            cursor, product_ids, outgoing_per_product, company_id, default_uom_id,
            lot_stock_id, customer_location_id, other_picking_ids, non_incoming_type_id,
        )
        if args.done_per_product > 0:
            total_done += _seed_done_moves(
                cursor, product_ids, args.done_per_product, company_id, default_uom_id,
                supplier_location_id, lot_stock_id, all_picking_ids, non_incoming_type_id,
            )
        _seed_quants(cursor, product_ids, company_id, lot_stock_id)

    print(f"  incoming moves (pending): {total_incoming:,}")
    print(f"  outgoing moves (pending): {total_outgoing:,}")
    print(f"  done moves (historial):   {total_done:,}")
    print("ANALYZE de las tablas sembradas…")
    cursor.execute("ANALYZE stock_move")
    cursor.execute("ANALYZE stock_quant")
    cursor.execute("ANALYZE stock_picking")

    with open(TARGETS_PATH, "w") as targets_file:
        json.dump({"warehouse_ids": warehouse_ids, "product_ids": product_ids}, targets_file)
    print(f"\nTargets guardados en {TARGETS_PATH}")
    print(f"  {len(product_ids)} productos × {len(warehouse_ids)} almacenes")
    connection.close()


def _seed_pickings(cursor, how_many, picking_type_id, location_id, location_dest_id, tag):
    if how_many <= 0:
        return []
    psycopg2.extras.execute_values(cursor, """
        INSERT INTO stock_picking
            (name, state, move_type, picking_type_id, location_id, location_dest_id)
        VALUES %s
        RETURNING id
    """, [
        (f"{STRESS_TAG}/{tag}/{sequence_number}", "assigned", "direct",
         picking_type_id, location_id, location_dest_id)
        for sequence_number in range(how_many)
    ], page_size=1000)
    return [row[0] for row in cursor.fetchall()]


def _seed_incoming_moves(cursor, product_ids, per_product, company_id,
                         uom_id, source_location_id, dest_location_id,
                         picking_ids, picking_type_id):
    """Moves entrantes: origen externo, destino = ubicación interna del almacén.
    Alimentan el CTE all_incoming_moves (el cuello de botella de prod).
    picking_type_id se puebla coherente con el picking asignado, de modo que la
    variante reescrita (filtra por picking_type_id) equivalga a la original."""
    if per_product <= 0 or not picking_ids:
        return 0
    cursor.execute("""
        INSERT INTO stock_move
            (company_id, product_id, product_uom, location_id, location_dest_id,
             name, procure_method, product_uom_qty, product_qty, state, date,
             picking_id, picking_type_id)
        SELECT %s, target.pid, %s, %s, %s,
               %s || '/IN/' || target.pid || '/' || series.n,
               'make_to_stock', 1, (1 + floor(random() * 5))::numeric,
               (ARRAY['waiting','confirmed','assigned','partially_available'])[1 + floor(random() * 4)::int],
               now() - (random() * interval '180 days'),
               (%s::int[])[1 + floor(random() * array_length(%s::int[], 1))::int],
               %s
        FROM unnest(%s::int[]) AS target(pid),
             generate_series(1, %s) AS series(n)
    """, (
        company_id, uom_id, source_location_id, dest_location_id,
        STRESS_TAG, picking_ids, picking_ids, picking_type_id,
        product_ids, per_product,
    ))
    return cursor.rowcount


def _seed_outgoing_moves(cursor, product_ids, per_product, company_id,
                         uom_id, source_location_id, dest_location_id,
                         picking_ids, picking_type_id):
    """Moves salientes: origen = ubicación interna, destino externo. Alimentan
    el CTE outgoing_moves."""
    if per_product <= 0 or not picking_ids:
        return 0
    cursor.execute("""
        INSERT INTO stock_move
            (company_id, product_id, product_uom, location_id, location_dest_id,
             name, procure_method, product_uom_qty, product_qty, state, date,
             picking_id, picking_type_id)
        SELECT %s, target.pid, %s, %s, %s,
               %s || '/OUT/' || target.pid || '/' || series.n,
               'make_to_stock', 1, (1 + floor(random() * 3))::numeric,
               (ARRAY['waiting','confirmed','assigned','partially_available'])[1 + floor(random() * 4)::int],
               now() - (random() * interval '180 days'),
               (%s::int[])[1 + floor(random() * array_length(%s::int[], 1))::int],
               %s
        FROM unnest(%s::int[]) AS target(pid),
             generate_series(1, %s) AS series(n)
    """, (
        company_id, uom_id, source_location_id, dest_location_id,
        STRESS_TAG, picking_ids, picking_ids, picking_type_id,
        product_ids, per_product,
    ))
    return cursor.rowcount


def _seed_done_moves(cursor, product_ids, per_product, company_id,
                     uom_id, source_location_id, dest_location_id,
                     picking_ids, picking_type_id):
    """Moves 'done' (historial de ventas/recepciones pasadas). Comparten
    product_id con los pendientes, así que un índice NO parcial tendría que
    escanearlos; un índice parcial 'WHERE pending' los evita. Reproduce la
    proporción ~80/20 done/pendiente de producción."""
    if per_product <= 0 or not picking_ids:
        return 0
    cursor.execute("""
        INSERT INTO stock_move
            (company_id, product_id, product_uom, location_id, location_dest_id,
             name, procure_method, product_uom_qty, product_qty, state, date,
             picking_id, picking_type_id)
        SELECT %s, target.pid, %s, %s, %s,
               %s || '/DONE/' || target.pid || '/' || series.n,
               'make_to_stock', 1, (1 + floor(random() * 5))::numeric,
               'done',
               now() - (random() * interval '540 days'),
               (%s::int[])[1 + floor(random() * array_length(%s::int[], 1))::int],
               %s
        FROM unnest(%s::int[]) AS target(pid),
             generate_series(1, %s) AS series(n)
    """, (
        company_id, uom_id, source_location_id, dest_location_id,
        STRESS_TAG, picking_ids, picking_ids, picking_type_id,
        product_ids, per_product,
    ))
    return cursor.rowcount


def _seed_quants(cursor, product_ids, company_id, location_id):
    """Un quant con stock por (producto, ubicación interna) para el join final."""
    cursor.execute("""
        INSERT INTO stock_quant
            (company_id, product_id, location_id, quantity, reserved_quantity, in_date)
        SELECT %s, target.pid, %s, (5 + floor(random() * 50))::numeric, 0, now()
        FROM unnest(%s::int[]) AS target(pid)
    """, (company_id, location_id, product_ids))


# ---------------------------------------------------------------------------
# bench
# ---------------------------------------------------------------------------
def _load_targets():
    if not os.path.exists(TARGETS_PATH):
        sys.exit("No hay targets. Corre 'seed' primero.")
    with open(TARGETS_PATH) as targets_file:
        return json.load(targets_file)


def _percentile(sorted_samples, fraction):
    if not sorted_samples:
        return 0.0
    position = fraction * (len(sorted_samples) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_samples) - 1)
    interpolation = position - lower_index
    return (sorted_samples[lower_index] * (1 - interpolation)
            + sorted_samples[upper_index] * interpolation)


def _measure_shape(cursor, sql_text, parameters, runs, warmups):
    for _ in range(warmups):
        cursor.execute(sql_text, parameters)
        cursor.fetchall()

    elapsed_milliseconds = []
    row_count = 0
    for _ in range(runs):
        start_time = time.perf_counter()
        cursor.execute(sql_text, parameters)
        fetched = cursor.fetchall()
        elapsed_milliseconds.append((time.perf_counter() - start_time) * 1000)
        row_count = len(fetched)

    sorted_samples = sorted(elapsed_milliseconds)
    return {
        "runs": runs,
        "rows": row_count,
        "min_ms": round(sorted_samples[0], 2),
        "p50_ms": round(_percentile(sorted_samples, 0.50), 2),
        "p95_ms": round(_percentile(sorted_samples, 0.95), 2),
        "p99_ms": round(_percentile(sorted_samples, 0.99), 2),
        "max_ms": round(sorted_samples[-1], 2),
        "mean_ms": round(statistics.fmean(elapsed_milliseconds), 2),
    }


def _capture_plan(cursor, sql_text, parameters, label, shape_name):
    cursor.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql_text, parameters)
    plan_lines = [row[0] for row in cursor.fetchall()]
    os.makedirs(PLAN_DIR, exist_ok=True)
    plan_path = os.path.join(PLAN_DIR, f"{label}__{shape_name}.txt")
    with open(plan_path, "w") as plan_file:
        plan_file.write("\n".join(plan_lines))
    execution_ms = None
    for plan_line in plan_lines:
        match = re.search(r"Execution Time: ([\d.]+) ms", plan_line)
        if match:
            execution_ms = float(match.group(1))
    return execution_ms, plan_path


def command_bench(args):
    targets = _load_targets()
    warehouse_ids = targets["warehouse_ids"]
    full_product_ids = targets["product_ids"]

    shapes = {}
    if args.shape in ("q2", "both"):
        shapes["q2_14prod"] = full_product_ids[:14]
    if args.shape in ("q1", "both"):
        shapes["q1_full"] = full_product_ids

    connection = open_connection(read_only=True)
    cursor = connection.cursor()

    saved_runs = _read_results()
    print(f"Corriendo bench (label='{args.label}', variant={args.variant}, runs={args.runs})\n")
    for shape_name, product_ids in shapes.items():
        sql_text, parameters = _build_query(args.variant, cursor, warehouse_ids, product_ids)
        latency = _measure_shape(cursor, sql_text, parameters, args.runs, args.warmups)
        execution_ms, plan_path = _capture_plan(
            cursor, sql_text, parameters, args.label, shape_name
        )
        latency["explain_execution_ms"] = execution_ms
        latency["n_products"] = len(product_ids)
        latency["variant"] = args.variant
        print(f"  [{shape_name}]  {len(product_ids)} productos → "
              f"p50={latency['p50_ms']}ms  p95={latency['p95_ms']}ms  "
              f"mean={latency['mean_ms']}ms  (EXPLAIN {execution_ms}ms, {latency['rows']} filas)")
        print(f"        plan: {plan_path}")
        saved_runs.append({
            "label": args.label,
            "shape": shape_name,
            **latency,
        })

    _write_results(saved_runs)
    connection.close()
    print(f"\nResultados acumulados en {RESULTS_PATH} — usá 'compare' para el A/B.")


# ---------------------------------------------------------------------------
# verify (correctitud: original vs reescrita deben dar lo mismo)
# ---------------------------------------------------------------------------
def command_verify(_args):
    """La query original y la reescrita deben devolver EXACTAMENTE el mismo
    resultado sobre los datos sembrados (con picking_type_id coherente). Es la
    prueba de correctitud que respalda la optimización — sin esto, medir la
    velocidad de una query que devuelve algo distinto no significa nada."""
    targets = _load_targets()
    warehouse_ids = targets["warehouse_ids"]
    connection = open_connection(read_only=True)
    cursor = connection.cursor()
    print("Verificando equivalencia: query original vs reescrita\n")
    all_ok = True
    for shape_name, product_ids in (
        ("q2_14prod", targets["product_ids"][:14]),
        ("q1_full", targets["product_ids"]),
    ):
        sql_original, params_original = _build_query("original", cursor, warehouse_ids, product_ids)
        cursor.execute(sql_original, params_original)
        rows_original = {tuple(row) for row in cursor.fetchall()}

        sql_rewrite, params_rewrite = _build_query("rewrite", cursor, warehouse_ids, product_ids)
        cursor.execute(sql_rewrite, params_rewrite)
        rows_rewrite = {tuple(row) for row in cursor.fetchall()}

        only_original = rows_original - rows_rewrite
        only_rewrite = rows_rewrite - rows_original
        if not only_original and not only_rewrite:
            print(f"  [{shape_name}] OK — {len(rows_original)} filas idénticas")
        else:
            all_ok = False
            print(f"  [{shape_name}] DIFIEREN — solo en original: {len(only_original)}, "
                  f"solo en rewrite: {len(only_rewrite)}")
            for row in list(only_original)[:5]:
                print(f"        solo original: {row}")
            for row in list(only_rewrite)[:5]:
                print(f"        solo rewrite:  {row}")
    connection.close()
    print("\n" + ("Equivalencia CONFIRMADA." if all_ok else "HAY DIVERGENCIAS — revisar."))
    if not all_ok:
        sys.exit(1)


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------
def command_index(args):
    connection = open_connection(read_only=False)
    cursor = connection.cursor()
    if args.action == "create":
        for index_name, create_statement in PROPOSED_INDEXES.items():
            cursor.execute(
                "SELECT 1 FROM pg_indexes WHERE indexname = %s", (index_name,)
            )
            if cursor.fetchone():
                print(f"  ya existe: {index_name}")
                continue
            print(f"  creando: {index_name}…")
            cursor.execute(create_statement)
        cursor.execute("ANALYZE stock_move")
    else:
        for index_name in PROPOSED_INDEXES:
            print(f"  drop: {index_name}")
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
    connection.close()
    print("Listo.")


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------
def command_compare(_args):
    saved_runs = _read_results()
    if not saved_runs:
        sys.exit("No hay corridas guardadas. Corre 'bench' primero.")

    by_shape = {}
    for run in saved_runs:
        by_shape.setdefault(run["shape"], []).append(run)

    for shape_name, runs in by_shape.items():
        print(f"\n=== {shape_name} ({runs[0]['n_products']} productos) ===")
        header = f"{'label':22} {'p50_ms':>10} {'p95_ms':>10} {'mean_ms':>10} {'EXPLAIN':>10}"
        print(header)
        print("-" * len(header))
        baseline_p50 = None
        for run in runs:
            delta = ""
            if baseline_p50 is None:
                baseline_p50 = run["p50_ms"]
            elif baseline_p50 > 0:
                change_pct = (run["p50_ms"] - baseline_p50) / baseline_p50 * 100
                speedup = baseline_p50 / run["p50_ms"] if run["p50_ms"] > 0 else 0
                delta = f"  ({change_pct:+.0f}%, {speedup:.1f}× vs baseline)"
            print(f"{run['label']:22} {run['p50_ms']:>10} {run['p95_ms']:>10} "
                  f"{run['mean_ms']:>10} {str(run['explain_execution_ms']):>10}{delta}")


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------
def _delete_seeded_rows(cursor):
    cursor.execute("DELETE FROM stock_move WHERE name LIKE %s", (f"{STRESS_TAG}%",))
    moves_deleted = cursor.rowcount
    cursor.execute("DELETE FROM stock_picking WHERE name LIKE %s", (f"{STRESS_TAG}%",))
    pickings_deleted = cursor.rowcount
    # Los quants sembrados son los de los productos objetivo en las ubicaciones
    # objetivo; se identifican por los targets guardados.
    quants_deleted = 0
    if os.path.exists(TARGETS_PATH):
        with open(TARGETS_PATH) as targets_file:
            targets = json.load(targets_file)
        cursor.execute("""
            DELETE FROM stock_quant sq
            USING stock_warehouse sw
            WHERE sw.id = ANY(%s)
              AND sq.location_id = sw.lot_stock_id
              AND sq.product_id = ANY(%s)
        """, (targets["warehouse_ids"], targets["product_ids"]))
        quants_deleted = cursor.rowcount
    cursor.execute("DELETE FROM stock_location WHERE name LIKE %s", (f"{STRESS_TAG}%",))
    return moves_deleted, pickings_deleted, quants_deleted


def command_cleanup(args):
    connection = open_connection(read_only=False)
    cursor = connection.cursor()
    print("Borrando datos sembrados…")
    moves_deleted, pickings_deleted, quants_deleted = _delete_seeded_rows(cursor)
    print(f"  moves:    {moves_deleted:,}")
    print(f"  pickings: {pickings_deleted:,}")
    print(f"  quants:   {quants_deleted:,}")
    if args.drop_indexes:
        for index_name in PROPOSED_INDEXES:
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
        print("  índices de prueba borrados")
    cursor.execute("ANALYZE stock_move")
    connection.close()
    if os.path.exists(TARGETS_PATH):
        os.remove(TARGETS_PATH)
    print("Listo. (stress_results.json se conserva; borralo a mano si querés reiniciar el A/B)")


# ---------------------------------------------------------------------------
# full
# ---------------------------------------------------------------------------
def command_full(args):
    if not os.path.exists(TARGETS_PATH) or args.reset:
        command_seed(args)
    # 0. Correctitud primero: si original y reescrita difieren, medir velocidad
    #    no tiene sentido. Aborta el flujo si hay divergencia.
    command_verify(None)
    # 1. Baseline: query original, sin índices
    command_index(argparse.Namespace(action="drop"))
    command_bench(argparse.Namespace(
        label="baseline", runs=args.runs, warmups=args.warmups,
        shape=args.shape, variant="original",
    ))
    # 2. Query original + índices parciales propuestos
    command_index(argparse.Namespace(action="create"))
    command_bench(argparse.Namespace(
        label="orig+index", runs=args.runs, warmups=args.warmups,
        shape=args.shape, variant="original",
    ))
    # 3. Query REESCRITA (picking_type_id), sin índices — la optimización real
    command_index(argparse.Namespace(action="drop"))
    command_bench(argparse.Namespace(
        label="rewrite", runs=args.runs, warmups=args.warmups,
        shape=args.shape, variant="rewrite",
    ))
    # 4. Query reescrita + índices
    command_index(argparse.Namespace(action="create"))
    command_bench(argparse.Namespace(
        label="rewrite+index", runs=args.runs, warmups=args.warmups,
        shape=args.shape, variant="rewrite",
    ))
    command_compare(None)


# ---------------------------------------------------------------------------
# results io
# ---------------------------------------------------------------------------
def _read_results():
    if not os.path.exists(RESULTS_PATH):
        return []
    with open(RESULTS_PATH) as results_file:
        return json.load(results_file)


def _write_results(saved_runs):
    with open(RESULTS_PATH, "w") as results_file:
        json.dump(saved_runs, results_file, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="volumen actual")

    seed_parser = subparsers.add_parser("seed", help="siembra datos sintéticos")
    seed_parser.add_argument("--target-products", type=int, default=400, dest="target_products")
    seed_parser.add_argument("--moves-per-product", type=int, default=200, dest="moves_per_product",
                             help="incoming moves PENDIENTES por producto POR almacén (outgoing = /5)")
    seed_parser.add_argument("--done-per-product", type=int, default=800, dest="done_per_product",
                             help="moves 'done' por producto POR almacén (historial; ~4× pending = 80/20)")
    seed_parser.add_argument("--warehouses", type=int, default=6)
    seed_parser.add_argument("--pickings", type=int, default=4000)
    seed_parser.add_argument("--reset", action="store_true", help="borra lo sembrado antes")

    bench_parser = subparsers.add_parser("bench", help="mide la query")
    bench_parser.add_argument("--label", required=True)
    bench_parser.add_argument("--runs", type=int, default=12)
    bench_parser.add_argument("--warmups", type=int, default=3)
    bench_parser.add_argument("--shape", choices=["q1", "q2", "both"], default="both")
    bench_parser.add_argument("--variant", choices=["original", "rewrite"], default="original",
                              help="original = anti-join a stock_picking; rewrite = filtro por picking_type_id")

    subparsers.add_parser("verify", help="correctitud: original vs reescrita dan lo mismo")

    index_parser = subparsers.add_parser("index", help="crea/borra índices propuestos")
    index_parser.add_argument("action", choices=["create", "drop"])

    subparsers.add_parser("compare", help="A/B de las corridas guardadas")

    cleanup_parser = subparsers.add_parser("cleanup", help="borra lo sembrado")
    cleanup_parser.add_argument("--drop-indexes", action="store_true", dest="drop_indexes")

    full_parser = subparsers.add_parser("full", help="seed→baseline→index→rewrite→compare")
    full_parser.add_argument("--target-products", type=int, default=400, dest="target_products")
    full_parser.add_argument("--moves-per-product", type=int, default=200, dest="moves_per_product")
    full_parser.add_argument("--done-per-product", type=int, default=800, dest="done_per_product")
    full_parser.add_argument("--warehouses", type=int, default=6)
    full_parser.add_argument("--pickings", type=int, default=4000)
    full_parser.add_argument("--runs", type=int, default=12)
    full_parser.add_argument("--warmups", type=int, default=3)
    full_parser.add_argument("--shape", choices=["q1", "q2", "both"], default="both")
    full_parser.add_argument("--reset", action="store_true")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "status": command_status,
        "seed": command_seed,
        "bench": command_bench,
        "verify": command_verify,
        "index": command_index,
        "compare": command_compare,
        "cleanup": command_cleanup,
        "full": command_full,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
