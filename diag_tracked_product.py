"""Diagnose why a tracked product got fully skipped during replenishment.

Run with:
    docker compose -f docker-compose.yml exec odoo \
        odoo shell -d <DB> --no-http < diag_tracked_product.py
"""
from odoo import api, SUPERUSER_ID  # noqa: F401

PRODUCT_CODE = 'JMD-915-6L'
SOURCE_WH_CODE = 'WRHAB'
PICKING_NAME = 'WRHAB/INT/00084'

env = env  # noqa: F821 (provided by odoo shell)

product = env['product.product'].search([('default_code', '=', PRODUCT_CODE)], limit=1)
if not product:
    product = env['product.product'].search(
        [('name', 'ilike', 'Olla de Presión Multifuncion Marca JMD')], limit=1)

print('=' * 80)
print(f'Product: {product.display_name}  id={product.id}')
print(f'  tracking     = {product.tracking}')
print(f'  is_storable  = {product.is_storable}')
print(f'  active       = {product.active}')
print(f'  company_id   = {product.company_id.display_name or "ALL"}')

wh = env['stock.warehouse'].search([('code', '=', SOURCE_WH_CODE)], limit=1)
print('-' * 80)
print(f'Source warehouse: {wh.display_name}  id={wh.id}')
print(f'  lot_stock_id = {wh.lot_stock_id.display_name} id={wh.lot_stock_id.id}')
print(f'  company_id   = {wh.company_id.display_name}')

child_locs = env['stock.location'].search([
    ('id', 'child_of', wh.lot_stock_id.id),
])
print(f'  child locations: {len(child_locs)}')

quants = env['stock.quant'].sudo().search([
    ('product_id', '=', product.id),
    ('location_id', 'child_of', wh.lot_stock_id.id),
])
print('-' * 80)
print(f'Quants at source ({len(quants)}):')
for q in quants:
    print(
        f'  loc={q.location_id.complete_name!r} '
        f'qty={q.quantity} reserved={q.reserved_quantity} '
        f'available={q.available_quantity} '
        f'lot={q.lot_id.name!r} lot_id={q.lot_id.id} '
        f'company={q.company_id.display_name}'
    )

lots = env['stock.lot'].sudo().search([
    ('product_id', '=', product.id),
])
print('-' * 80)
print(f'All lots for product ({len(lots)}):')
for lot in lots:
    print(f'  lot={lot.name!r} id={lot.id} company={lot.company_id.display_name} '
          f'product_qty={lot.product_qty}')

pick = env['stock.picking'].sudo().search([('name', '=', PICKING_NAME)], limit=1)
if pick:
    print('-' * 80)
    print(f'Picking {pick.name}  state={pick.state}  company={pick.company_id.display_name}')
    for m in pick.move_ids:
        if m.product_id == product:
            print(f'  Move {m.id}: product={m.product_id.display_name}')
            print(f'    state={m.state} procure_method={m.procure_method}')
            print(f'    location_id={m.location_id.complete_name}')
            print(f'    location_dest_id={m.location_dest_id.complete_name}')
            print(f'    product_uom_qty={m.product_uom_qty} reserved={m.quantity} '
                  f'forecast={m.forecast_availability}')
            for ml in m.move_line_ids:
                print(f'    MoveLine {ml.id}: lot={ml.lot_id.name!r} '
                      f'qty={ml.quantity} product_uom_qty={ml.quantity_product_uom} '
                      f'loc={ml.location_id.complete_name}')
print('=' * 80)
