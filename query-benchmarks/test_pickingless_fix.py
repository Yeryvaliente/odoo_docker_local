#!/usr/bin/env python3
"""Prueba dirigida del hallazgo del reviewer (ODOO-1393): un stock_move SIN
picking_id pero con picking_type_id de tipo incoming (los que fija una regla de
aprovisionamiento) debe CONSERVARSE en all_incoming_moves, igual que hacía el
anti-join original.

Compara 3 variantes del filtro de exclusión de vendor sobre el MISMO dataset,
midiendo el delta de virtual_available que aporta un move pickingless-incoming
insertado a propósito:
  - ANTIJOIN : NOT EXISTS(stock_picking ... incoming)      (comportamiento original)
  - BUG_A    : picking_type_id IS NULL OR != ALL(incoming) (mi primera versión)
  - FIX_B    : picking_id      IS NULL OR != ALL(incoming) (el fix del reviewer)

Esperado: ANTIJOIN y FIX_B suman el move (+qty); BUG_A lo excluye (+0).
Todo dentro de una transacción con ROLLBACK: no persiste nada.
"""

import os

import psycopg2

DB_URL = os.environ.get("LOCAL_DB_URL", "postgresql://odoo:odoo@localhost:5432/odoo_18")

_CTE = """
    WITH warehouse_locations AS (
        SELECT sw.id AS warehouse_id, sw.company_id, sl.id AS location_id
        FROM stock_warehouse sw
        JOIN stock_location wh_loc ON wh_loc.id = sw.lot_stock_id
        JOIN stock_location sl ON (sl.id = wh_loc.id OR sl.parent_path LIKE wh_loc.parent_path || '%%')
        WHERE sl.usage = 'internal' AND sw.id IN %(wh)s
    ),
    outgoing_moves AS (
        SELECT wl.warehouse_id, sm.product_id, COALESCE(SUM(sm.product_qty),0) AS outgoing_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_id = wl.location_id
            AND sm.product_id IN %(pids)s AND sm.state IN ('waiting','confirmed','assigned','partially_available')
            AND NOT EXISTS (SELECT 1 FROM warehouse_locations wl2
                            WHERE wl2.warehouse_id = wl.warehouse_id AND wl2.location_id = sm.location_dest_id)
        GROUP BY wl.warehouse_id, sm.product_id
    ),
    all_incoming_moves AS (
        SELECT wl.warehouse_id, sm.product_id, COALESCE(SUM(sm.product_qty),0) AS all_incoming_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_dest_id = wl.location_id
            AND sm.product_id IN %(pids)s AND sm.state IN ('waiting','confirmed','assigned','partially_available')
            AND NOT EXISTS (SELECT 1 FROM warehouse_locations wl2
                            WHERE wl2.warehouse_id = wl.warehouse_id AND wl2.location_id = sm.location_id)
            AND {vendor_filter}
        GROUP BY wl.warehouse_id, sm.product_id
    )
    SELECT COALESCE(SUM(sq.quantity),0) - COALESCE(MAX(om.outgoing_qty),0) + COALESCE(MAX(aim.all_incoming_qty),0)
    FROM warehouse_locations wl
    JOIN stock_quant sq ON sq.location_id = wl.location_id AND sq.product_id IN %(pids)s
    LEFT JOIN outgoing_moves om ON om.warehouse_id = wl.warehouse_id AND om.product_id = sq.product_id
    LEFT JOIN all_incoming_moves aim ON aim.warehouse_id = wl.warehouse_id AND aim.product_id = sq.product_id
    GROUP BY sq.product_id, wl.warehouse_id, wl.company_id
"""

VARIANTS = {
    "ANTIJOIN": """NOT EXISTS (SELECT 1 FROM stock_picking sp
                    JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                    WHERE sp.id = sm.picking_id AND spt.code = 'incoming')""",
    "BUG_A": "(sm.picking_type_id IS NULL OR sm.picking_type_id != ALL(%(inc)s::int[]))",
    "FIX_B": "(sm.picking_id IS NULL OR sm.picking_type_id != ALL(%(inc)s::int[]))",
}


def virtual_available(cur, params):
    totals = {}
    for name, vf in VARIANTS.items():
        cur.execute(_CTE.format(vendor_filter=vf), params)
        rows = cur.fetchall()
        totals[name] = float(rows[0][0]) if rows else 0.0
    return totals


def main():
    conn = psycopg2.connect(DB_URL, connect_timeout=10)
    conn.autocommit = False  # transacción manual -> ROLLBACK al final
    cur = conn.cursor()
    try:
        # Un warehouse con lot_stock interna + un producto CON quant ahí.
        cur.execute("""
            SELECT sw.id, sw.company_id, sw.lot_stock_id, sq.product_id, uu.id AS uom
            FROM stock_warehouse sw
            JOIN stock_location wl ON wl.id = sw.lot_stock_id AND wl.usage='internal'
            JOIN stock_quant sq ON sq.location_id = wl.id AND sq.quantity > 0
            JOIN product_product pp ON pp.id = sq.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN uom_uom uu ON uu.id = pt.uom_id
            LIMIT 1
        """)
        wh_id, company_id, lot_stock_id, product_id, uom_id = cur.fetchone()
        cur.execute("SELECT id FROM stock_location WHERE usage='supplier' ORDER BY id LIMIT 1")
        supplier_loc = cur.fetchone()[0]
        cur.execute("SELECT id FROM stock_picking_type WHERE code='incoming' ORDER BY id LIMIT 1")
        incoming_type = cur.fetchone()[0]
        cur.execute("SELECT array_agg(id) FROM stock_picking_type WHERE code='incoming'")
        incoming_ids = cur.fetchone()[0]

        params = {"wh": (wh_id,), "pids": (product_id,), "inc": incoming_ids}
        print(f"Caso: warehouse={wh_id} product={product_id} incoming_type={incoming_type}")

        before = virtual_available(cur, params)
        print(f"\nBASELINE (sin el move):  {before}")

        # Insertar el move problemático: SIN picking_id, con picking_type_id incoming,
        # entrante a la ubicación interna del warehouse, pendiente.
        cur.execute("""
            INSERT INTO stock_move
                (company_id, product_id, product_uom, location_id, location_dest_id,
                 name, procure_method, product_uom_qty, product_qty, state, date,
                 picking_id, picking_type_id)
            VALUES (%s, %s, %s, %s, %s, 'PICKINGLESS_INCOMING_TEST', 'make_to_stock',
                    100, 100, 'confirmed', now(), NULL, %s)
        """, (company_id, product_id, uom_id, supplier_loc, lot_stock_id, incoming_type))

        after = virtual_available(cur, params)
        print(f"CON move pickingless-incoming (qty=100): {after}")

        print("\nDelta (efecto del move sobre virtual_available):")
        ok = True
        for name in VARIANTS:
            delta = after[name] - before[name]
            expect = 100.0 if name in ("ANTIJOIN", "FIX_B") else 0.0
            verdict = "OK" if abs(delta - expect) < 0.001 else "!!"
            if verdict != "OK":
                ok = False
            print(f"  {name:9} delta={delta:+.0f}  (esperado {expect:+.0f})  {verdict}")

        print("\n" + ("✓ FIX_B replica el anti-join; BUG_A divergía (excluía el move)."
                      if ok else "✗ resultado inesperado — revisar."))
    finally:
        conn.rollback()   # nada se persiste
        conn.close()
        print("(rollback: no se modificó la BD)")


if __name__ == "__main__":
    main()
