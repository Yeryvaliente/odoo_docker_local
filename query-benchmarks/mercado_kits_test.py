# Igual que mercado_flow_test pero enfocado en KITS FANTASMA: la inyección de
# stock de kits (_inject_kit_stock) calcula la disponibilidad del kit a partir de
# la disponibilidad de sus COMPONENTES, usando la misma query optimizada. Verifica
# que el stock de kits en la respuesta no cambia con la optimización.

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
            AND sm.product_id IN %s AND sm.state IN ('waiting','confirmed','assigned','partially_available')
            AND NOT EXISTS (SELECT 1 FROM warehouse_locations wl2
                            WHERE wl2.warehouse_id = wl.warehouse_id AND wl2.location_id = sm.location_dest_id)
        GROUP BY wl.warehouse_id, sm.product_id
    ),
    all_incoming_moves AS (
        SELECT wl.warehouse_id, sm.product_id, COALESCE(SUM(sm.product_qty),0) AS all_incoming_qty
        FROM warehouse_locations wl
        JOIN stock_move sm ON sm.location_dest_id = wl.location_id
            AND sm.product_id IN %s AND sm.state IN ('waiting','confirmed','assigned','partially_available')
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
    wh = tuple(warehouse_ids) if not isinstance(warehouse_ids, tuple) else warehouse_ids
    env.cr.execute(_ANTIJOIN, (wh, variant_ids, variant_ids, variant_ids))
    out = {}
    for pid, wid, cid, va in env.cr.fetchall():
        out.setdefault(pid, []).append({"warehouse_id": wid, "company_id": cid, "virtual_available": va})
    return out


def _flatten(sbv):
    return {(vid, e["warehouse_id"]): e["virtual_available"]
            for vid, entries in sbv.items() for e in entries}


# Almacenes con stock
env.cr.execute("""
    SELECT sw.id FROM stock_warehouse sw
    JOIN stock_location wl ON wl.id = sw.lot_stock_id
    JOIN stock_location sl ON (sl.id = wl.id OR sl.parent_path LIKE wl.parent_path || '%%')
    JOIN stock_quant sq ON sq.location_id = sl.id AND sq.quantity > 0
    WHERE sl.usage = 'internal' GROUP BY sw.id ORDER BY count(sq.id) DESC LIMIT 8
""")
warehouse_ids = {r[0] for r in env.cr.fetchall()}

# Kits fantasma cuyos componentes tienen stock en esos almacenes
env.cr.execute("SELECT to_regclass('mrp_bom') IS NOT NULL")
if not env.cr.fetchone()[0]:
    print("FLOW_KITS mrp no instalado; sin prueba de kits")
else:
    env.cr.execute("""
        SELECT DISTINCT pp.id
        FROM product_product pp
        JOIN mrp_bom mb ON mb.product_tmpl_id = pp.product_tmpl_id AND mb.type='phantom' AND mb.active=TRUE
        WHERE EXISTS (
            SELECT 1 FROM mrp_bom_line mbl
            JOIN stock_quant sq ON sq.product_id = mbl.product_id
            JOIN stock_location sl ON sl.id = sq.location_id
            WHERE mbl.bom_id = mb.id AND sl.usage='internal' AND sq.quantity > 0)
        LIMIT 300
    """)
    kit_ids = tuple(r[0] for r in env.cr.fetchall())
    print(f"FLOW_KITS_CASE warehouses={sorted(warehouse_ids)} phantom_kits_con_componentes_con_stock={len(kit_ids)}")

    if not kit_ids:
        print("FLOW_KITS_RESULT no hay kits fantasma con componentes con stock en local")
    else:
        resA = sa.compute_stock_with_kits(env, kit_ids, warehouse_ids)
        flatA = _flatten(resA)
        saved = sa._compute_catalog_stock_by_variant
        sa._compute_catalog_stock_by_variant = _orig_query
        try:
            resB = sa.compute_stock_with_kits(env, kit_ids, warehouse_ids)
            flatB = _flatten(resB)
        finally:
            sa._compute_catalog_stock_by_variant = saved
        keys = set(flatA) | set(flatB)
        diffs = {k: (flatA.get(k), flatB.get(k)) for k in keys if flatA.get(k) != flatB.get(k)}
        print(f"FLOW_KITS_WITH_STOCK optimizada={len(resA)} original={len(resB)}")
        print(f"FLOW_KITS_DIFFS {len(diffs)}")
        if diffs:
            print("FLOW_KITS_DIFF_SAMPLE", list(diffs.items())[:10])
        print(f"FLOW_KITS_TOTAL optimizada={sum(flatA.values())} original={sum(flatB.values())}")
        print(f"FLOW_KITS_VERDICT {'IDENTICA' if not diffs else 'DIFERENTE'}")
