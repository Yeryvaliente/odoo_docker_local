/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.two_mercado_force = vals.two_mercado_force || false;
    },

    serialize() {
        const data = super.serialize(...arguments);
        data.two_mercado_force = this.two_mercado_force;
        return data;
    },
});