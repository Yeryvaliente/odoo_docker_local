#!/usr/bin/env python3
"""Verifica que la FUSIÓN del cherry-pick de mercado en testing sea correcta:
la query de stock ya en testing (scope por location_ids + anti-join a
stock_picking) y la fusionada (scope por location_ids + filtro por
picking_type_id) deben devolver filas IDÉNTICAS sobre los mismos datos.

Esto valida el único punto de riesgo del cherry-pick: que resolver el conflicto
combinando la lógica de testing (location scoping) con la reescritura no cambió
lo que la función calcula. Read-only sobre la BD local odoo_18.
"""

import os

import psycopg2

DB_URL = os.environ.get("LOCAL_DB_URL", "postgresql://odoo:odoo@localhost:5432/odoo_18")

# CTE común (con el scope_loc que añadió testing). Solo cambia el filtro de vendor.
_HEAD = """
    WITH warehouse_locations AS (
        SELECT sw.id AS warehouse_id, sw.company_id, sl.id AS location_id
        FROM stock_warehouse sw
        JOIN stock_location wh_loc ON wh_loc.id = sw.lot_stock_id
        JOIN stock_location sl ON (sl.id = wh_loc.id OR sl.parent_path LIKE wh_loc.parent_path || '%%')
        JOIN stock_location scope_loc ON (sl.id = scope_loc.id OR sl.parent_path LIKE scope_loc.parent_path || '%%')
        WHERE sl.usage = 'internal' AND sw.id IN %s AND scope_loc.id IN %s
    ),
    outgoing_moves AS (
        SELECT wl.warehouse_id, sm.product_id, COALESCE(SUM(sm.product_qty),0) AS outgoing_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_id = wl.location_id
            AND sm.product_id IN %s
            AND sm.state IN ('waiting','confirmed','assigned','partially_available')
            AND NOT EXISTS (SELECT 1 FROM warehouse_locations wl2
                            WHERE wl2.warehouse_id = wl.warehouse_id AND wl2.location_id = sm.location_dest_id)
        GROUP BY wl.warehouse_id, sm.product_id
    ),
    all_incoming_moves AS (
        SELECT wl.warehouse_id, sm.product_id, COALESCE(SUM(sm.product_qty),0) AS all_incoming_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_dest_id = wl.location_id
            AND sm.product_id IN %s
            AND sm.state IN ('waiting','confirmed','assigned','partially_available')
            AND NOT EXISTS (SELECT 1 FROM warehouse_locations wl2
                            WHERE wl2.warehouse_id = wl.warehouse_id AND wl2.location_id = sm.location_id)
"""

_TAIL = """
        GROUP BY wl.warehouse_id, sm.product_id
    )
    SELECT sq.product_id, wl.warehouse_id, wl.company_id,
           COALESCE(SUM(sq.quantity),0) - COALESCE(MAX(om.outgoing_qty),0) + COALESCE(MAX(aim.all_incoming_qty),0) AS virtual_available
    FROM warehouse_locations wl
    JOIN stock_quant sq ON sq.location_id = wl.location_id AND sq.product_id IN %s
    LEFT JOIN outgoing_moves om ON om.warehouse_id = wl.warehouse_id AND om.product_id = sq.product_id
    LEFT JOIN all_incoming_moves aim ON aim.warehouse_id = wl.warehouse_id AND aim.product_id = sq.product_id
    GROUP BY sq.product_id, wl.warehouse_id, wl.company_id
    HAVING COALESCE(SUM(sq.quantity),0) > 0 OR COALESCE(MAX(om.outgoing_qty),0) > 0 OR COALESCE(MAX(aim.all_incoming_qty),0) > 0
"""

TESTING_ANTIJOIN = _HEAD + """
            AND NOT EXISTS (
                SELECT 1 FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE sp.id = sm.picking_id AND spt.code = 'incoming')
""" + _TAIL

MERGED_PICKING_TYPE = _HEAD + """
            AND (sm.picking_type_id IS NULL OR sm.picking_type_id != ALL(%s::int[]))
""" + _TAIL


def main():
    conn = psycopg2.connect(DB_URL, connect_timeout=10)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    cur.execute("""
        SELECT sw.id FROM stock_warehouse sw
        JOIN stock_location wl ON wl.id = sw.lot_stock_id
        JOIN stock_location sl ON (sl.id = wl.id OR sl.parent_path LIKE wl.parent_path || '%%')
        JOIN stock_quant sq ON sq.location_id = sl.id AND sq.quantity > 0
        WHERE sl.usage = 'internal'
        GROUP BY sw.id ORDER BY count(sq.id) DESC LIMIT 6
    """)
    warehouse_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT lot_stock_id FROM stock_warehouse WHERE id IN %s", (tuple(warehouse_ids),))
    scope_loc_ids = tuple(r[0] for r in cur.fetchall() if r[0])
    cur.execute("""
        SELECT DISTINCT sq.product_id FROM stock_quant sq
        JOIN stock_location sl ON sl.id = sq.location_id
        WHERE sl.usage='internal' AND sq.quantity>0 AND sq.product_id IS NOT NULL
        ORDER BY sq.product_id LIMIT 400
    """)
    product_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT id FROM stock_picking_type WHERE code='incoming'")
    incoming_type_ids = [r[0] for r in cur.fetchall()]

    print(f"Datos: {len(warehouse_ids)} almacenes, {len(scope_loc_ids)} scope-locs, "
          f"{len(product_ids)} productos, {len(incoming_type_ids)} tipos incoming.")

    wh = tuple(warehouse_ids)
    pids = tuple(product_ids)
    cur.execute(TESTING_ANTIJOIN, (wh, scope_loc_ids, pids, pids, pids))
    rows_testing = {tuple(r) for r in cur.fetchall()}
    cur.execute(MERGED_PICKING_TYPE, (wh, scope_loc_ids, pids, pids, incoming_type_ids, pids))
    rows_merged = {tuple(r) for r in cur.fetchall()}

    only_testing = rows_testing - rows_merged
    only_merged = rows_merged - rows_testing
    print(f"\nfilas testing (anti-join):     {len(rows_testing)}")
    print(f"filas fusionada (picking_type): {len(rows_merged)}")
    if not only_testing and not only_merged:
        print("\n✓ IDÉNTICAS — la fusión del cherry-pick preservó la lógica de mercado.")
    else:
        print(f"\n✗ DIFIEREN — solo testing {len(only_testing)}, solo fusionada {len(only_merged)}")
        for r in list(only_testing)[:5]:
            print("   solo testing:", r)
        for r in list(only_merged)[:5]:
            print("   solo fusionada:", r)
    conn.close()


if __name__ == "__main__":
    main()
