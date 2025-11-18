# -*- coding: utf-8 -*-

from odoo import models, fields


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    # Campo para bypass de validación de Mercado
    two_mercado_force = fields.Boolean(
        string='Validación Forzada Mercado',
    )