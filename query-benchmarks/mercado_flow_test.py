# Prueba del flujo de STOCK de mercado (odoo shell) al nivel de
# compute_stock_with_kits — la función que filter_products_ground_shipping usa
# para obtener el `stock` de cada producto de la respuesta del catálogo
# (query de disponibilidad + inyección de kits fantasma). Es exactamente donde
# vive la optimización. Compara OPTIMIZADA (picking_type_id) vs ORIGINAL
# (anti-join, por monkeypatch) sobre almacenes reales CON stock.
# Rama feature (firma main), alineada con la BD local.

from odoo.addons.twonary_mercado.utils import stock_availability as sa

_ANTIJOIN = """
    WITH warehouse_locations AS (
        SELECT sw.id AS warehouse_id, sw.company_id, sl.id AS location_id
        FROM stock_warehouse sw
        JOIN stock_location wh_loc ON wh_loc.id = sw.lot_stock_id
        JOIN stock_location sl ON (sl.id = wh_loc.id OR sl.parent_path LIKE wh_loc.parent_path || '%%')
        WHERE sl.usage = 'internal' AND sw.id IN %s
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
            AND NOT EXISTS (SELECT 1 FROM stock_picking sp
                            JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                            WHERE sp.id = sm.picking_id AND spt.code = 'incoming')
        GROUP BY wl.warehouse_id, sm.product_id
    )
    SELECT sq.product_id, wl.warehouse_id, wl.company_id,
           COALESCE(SUM(sq.quantity),0) - COALESCE(MAX(om.outgoing_qty),0) + COALESCE(MAX(aim.all_incoming_qty),0)
    FROM warehouse_locations wl
    JOIN stock_quant sq ON sq.location_id = wl.location_id AND sq.product_id IN %s
    LEFT JOIN outgoing_moves om ON om.warehouse_id = wl.warehouse_id AND om.product_id = sq.product_id
    LEFT JOIN all_incoming_moves aim ON aim.warehouse_id = wl.warehouse_id AND aim.product_id = sq.product_id
    GROUP BY sq.product_id, wl.warehouse_id, wl.company_id
    HAVING COALESCE(SUM(sq.quantity),0) > 0 OR COALESCE(MAX(om.outgoing_qty),0) > 0 OR COALESCE(MAX(aim.all_incoming_qty),0) > 0
"""


def _orig_query(env, variant_ids, warehouse_ids):
    if not variant_ids or not warehouse_ids:
        return {}
    wh_ids_tuple = tuple(warehouse_ids) if not isinstance(warehouse_ids, tuple) else warehouse_ids
    env.cr.execute(_ANTIJOIN, (wh_ids_tuple, variant_ids, variant_ids, variant_ids))
    out = {}
    for pid, wid, cid, va in env.cr.fetchall():
        out.setdefault(pid, []).append(
            {"warehouse_id": wid, "company_id": cid, "virtual_available": va})
    return out


def _flatten(stock_by_variant):
    flat = {}
    for vid, entries in stock_by_variant.items():
        for e in entries:
            flat[(vid, e["warehouse_id"])] = e["virtual_available"]
    return flat


# Descubrir almacenes CON stock y productos CON stock en ellos (SQL directo).
env.cr.execute("""
    SELECT sw.id FROM stock_warehouse sw
    JOIN stock_location wl ON wl.id = sw.lot_stock_id
    JOIN stock_location sl ON (sl.id = wl.id OR sl.parent_path LIKE wl.parent_path || '%%')
    JOIN stock_quant sq ON sq.location_id = sl.id AND sq.quantity > 0
    WHERE sl.usage = 'internal'
    GROUP BY sw.id ORDER BY count(sq.id) DESC LIMIT 6
""")
warehouse_ids = {r[0] for r in env.cr.fetchall()}

env.cr.execute("""
    SELECT DISTINCT sq.product_id FROM stock_quant sq
    JOIN stock_location sl ON sl.id = sq.location_id
    WHERE sl.usage='internal' AND sq.quantity>0 AND sq.product_id IS NOT NULL
    ORDER BY sq.product_id LIMIT 500
""")
variant_ids = tuple(r[0] for r in env.cr.fetchall())

env.cr.execute("SELECT to_regclass('mrp_bom') IS NOT NULL")
kit_count = 0
if env.cr.fetchone()[0] and variant_ids:
    env.cr.execute("""
        SELECT count(DISTINCT pp.id) FROM product_product pp
        JOIN mrp_bom mb ON mb.product_tmpl_id = pp.product_tmpl_id
        WHERE pp.id IN %s AND mb.type='phantom' AND mb.active=TRUE
    """, (variant_ids,))
    kit_count = env.cr.fetchone()[0]

print(f"FLOW_CASE warehouses={sorted(warehouse_ids)} variants={len(variant_ids)} phantom_kits={kit_count}")

resA = sa.compute_stock_with_kits(env, variant_ids, warehouse_ids)          # optimizada
flatA = _flatten(resA)

saved = sa._compute_catalog_stock_by_variant
sa._compute_catalog_stock_by_variant = _orig_query
try:
    resB = sa.compute_stock_with_kits(env, variant_ids, warehouse_ids)      # original
    flatB = _flatten(resB)
finally:
    sa._compute_catalog_stock_by_variant = saved

keys = set(flatA) | set(flatB)
diffs = {k: (flatA.get(k), flatB.get(k)) for k in keys if flatA.get(k) != flatB.get(k)}
print(f"FLOW_ROWS optimizada={len(flatA)} original={len(flatB)}")
print(f"FLOW_PRODUCTS_WITH_STOCK optimizada={len(resA)} original={len(resB)}")
print(f"FLOW_DIFFS {len(diffs)}")
if diffs:
    print("FLOW_DIFF_SAMPLE", list(diffs.items())[:10])
print(f"FLOW_TOTAL_VIRTUAL optimizada={sum(flatA.values())} original={sum(flatB.values())}")
print(f"FLOW_VERDICT {'IDENTICA' if not diffs else 'DIFERENTE'}")
