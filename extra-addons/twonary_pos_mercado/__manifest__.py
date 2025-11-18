# -*- coding: utf-8 -*-
{
    'name': 'Twonary POS Mercado',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Add required customer and internal notes to POS categories',
    'description': """
        This module extends POS categories to allow making customer notes and
        internal notes required. When a product from a category with required
        notes is added to the cart, the appropriate note field will be shown.
    """,
    'author': 'Twonary',
    'website': 'https://twonary.com',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_category_views.xml',
        'data/ir_config_param_data.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'twonary_pos_category/static/src/js/pos_category_notes.js',
            'twonary_pos_category/static/src/js/pos_order_line.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
