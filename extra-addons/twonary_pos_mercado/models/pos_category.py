# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosCategory(models.Model):
    _inherit = 'pos.category'

    customer_note_required = fields.Boolean(
        string='Customer Note Required',
        default=False,
        help='If checked, customer note will be required when adding products from this category to the cart.'
    )
    internal_note_required = fields.Boolean(
        string='Internal Note Required',
        default=False,
        help='If checked, internal note will be required when adding products from this category to the cart.'
    )

    @api.constrains('customer_note_required', 'internal_note_required')
    def _check_note_requirements(self):
        """Ensure only one type of note can be required at a time."""
        for record in self:
            if record.customer_note_required and record.internal_note_required:
                raise ValidationError(
                    _('You cannot require both customer note and internal note at the same time. '
                      'Please select only one.')
                )

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Override to include the new fields in POS data loading."""
        pos_fields = super()._load_pos_data_fields(config_id)
        pos_fields.extend(['customer_note_required', 'internal_note_required'])
        return pos_fields

    @api.onchange('customer_note_required')
    def _onchange_customer_note_required(self):
        """When customer note is required, disable internal note."""
        if self.customer_note_required:
            self.internal_note_required = False

    @api.onchange('internal_note_required')
    def _onchange_internal_note_required(self):
        """When internal note is required, disable customer note."""
        if self.internal_note_required:
            self.customer_note_required = False
