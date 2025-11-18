/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { ask } from "@point_of_sale/app/store/make_awaitable_dialog";

patch(PosStore.prototype, {
    /**
     * Override addLineToCurrentOrder to check for required notes based on product category
     */
    async addLineToCurrentOrder(vals, opts = {}, configure = true) {
        // Check if product has a category that requires notes
        const product = vals.product_id;
        
        if (product && product.pos_categ_ids && product.pos_categ_ids.length > 0) {
            // Get the first category that has note requirements
            const categoryWithNotes = this._getCategoryWithNoteRequirements(product);
            
            if (categoryWithNotes) {
                const requiredNoteType = this._getRequiredNoteType(categoryWithNotes);
                
                if (requiredNoteType && !vals.customer_note) {
                    // Show note popup
                    const note = await this._showRequiredNotePopup(requiredNoteType, product);
                    
                    if (note === null) {
                        // User cancelled, don't add the product
                        return;
                    }
                    
                    // Add the note to the vals
                    vals.customer_note = note;
                    
                    // Si es producto TIENDA-SALE-REST, validar con Mercado
                    if (product.default_code === 'TIENDA-SALE-REST') {
                        
                        const mercadoData = await this._validateMercadoOrder(note);
                        
                        
                        if (mercadoData && mercadoData.success) {
                            // Validación exitosa: actualizar precio
                            vals.price_unit = mercadoData.totalCost;
                            
                        } else {
                            // Validación falló: mostrar diálogo de confirmación
                            console.error('❌ [MERCADO] Error:', mercadoData?.error || 'Unknown error');
                            
                            const confirmed = await ask(this.dialog, {
                                title: _t('Mercado Validation Failed'),
                                body: _t(
                                    'The Mercado order validation failed:\n\n' +
                                    'Error: ' + (mercadoData?.error || 'Unknown error') + '\n\n' +
                                    'Do you want to save the order ID anyway?'
                                ),
                            });
                            
                            if (!confirmed) {
                                // Usuario canceló, no agregar el producto
                                console.log('❌ [MERCADO] User cancelled, not adding product');
                                return null;
                            }
                            
                            // Usuario confirmó: marcar como bypass
                            console.log('⚠️ [MERCADO] User chose to save without validation');
                            vals.two_mercado_force = true;
                            
                            // Si hay precio disponible, usarlo incluso en bypass
                            if (mercadoData && mercadoData.totalCost) {
                                vals.price_unit = mercadoData.totalCost;
                            }
                        }
                    }
                }
            }
        }
        
        // Call the original method
        return await super.addLineToCurrentOrder(vals, opts, configure);
    },

    /**
     * Get the first category that has note requirements for the given product
     */
    _getCategoryWithNoteRequirements(product) {
        if (!product.pos_categ_ids) {
            return null;
        }
        
        for (const category of product.pos_categ_ids) {
            // Check this category and its parent hierarchy
            const categoryWithNotes = this._checkCategoryHierarchy(category);
            if (categoryWithNotes) {
                return categoryWithNotes;
            }
        }
        return null;
    },

    /**
     * Check category and its parent hierarchy for note requirements
     */
    _checkCategoryHierarchy(category) {
        let currentCategory = category;
        let depth = 0;
        const maxDepth = 10; // Prevent infinite loops
        
        while (currentCategory && depth < maxDepth) {
            // Check if current category has note requirements
            if (currentCategory.customer_note_required || currentCategory.internal_note_required) {
                return currentCategory;
            }
            
            // Move to parent category
            if (currentCategory.parent_id) {
                // Handle different parent_id formats
                if (typeof currentCategory.parent_id === 'object' && currentCategory.parent_id.id) {
                    // If parent_id is already a PosCategory object
                    currentCategory = currentCategory.parent_id;
                } else if (Array.isArray(currentCategory.parent_id) && currentCategory.parent_id.length > 0) {
                    // If parent_id is [id, name] format
                    const parentId = currentCategory.parent_id[0];
                    currentCategory = this.data.models["pos.category"].get(parentId);
                } else if (typeof currentCategory.parent_id === 'number') {
                    // If parent_id is just a number
                    currentCategory = this.data.models["pos.category"].get(currentCategory.parent_id);
                } else {
                    break;
                }
            } else {
                break;
            }
            
            depth++;
        }
        
        return null;
    },

    /**
     * Get the type of required note for a category
     */
    _getRequiredNoteType(category) {
        if (category.customer_note_required) {
            return 'customer';
        } else if (category.internal_note_required) {
            return 'internal';
        }
        return null;
    },

    /**
     * Show popup for required note input
     */
    async _showRequiredNotePopup(noteType, product) {
        const title = noteType === 'customer' 
            ? _t("Customer Note Required") 
            : _t("Internal Note Required");
        
        const placeholder = noteType === 'customer'
            ? _t("Enter customer note...")
            : _t("Enter internal note...");

        let buttons = [];
        if (noteType === 'internal') {
            // For internal notes, show predefined notes if available
            buttons = this.data.models["pos.note"]?.getAll().map((note) => ({
                label: note.name,
                isSelected: false,
            })) || [];
        }

        try {
            const result = await makeAwaitable(this.dialog, TextInputPopup, {
                title: title,
                placeholder: placeholder,
                buttons: buttons,
                rows: 3,
                startingValue: "",
            });
            
            return result || "";
        } catch (error) {
            // User cancelled
            return null;
        }
    },
    /**
     * Validar orden de Mercado contra API
     */
    async _validateMercadoOrder(orderId) {
        
        try {
            const payload = {
                note: orderId,
                sku: 'TIENDA-SALE-REST',
            };
            
            const response = await fetch('/api/mercado/validate-note', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const resp = await response.json();
            
            const result = resp.result;

            if (result && result.success && result.totalCost) {
                const orderDate = result.orderDate;
                const isToday = this._isSameDay(orderDate);
                
                if (!isToday) {
                    return {
                        success: false,
                        totalCost: result.totalCost,
                        error: 'Order is not from today'
                    };
                }
                console.log('✅ Validation successful - Total:', result.totalCost, 'Date:', orderDate);
                
                return {
                    success: true,
                    totalCost: result.totalCost,
                    orderDate: orderDate,
                    orderId: result.order_id || orderId
                };
            } else {
                console.warn('⚠️ Validation failed:', result);
                return {
                    success: false,
                    error: result?.error || 'Order not found or invalid response'
                };
            }
        } catch (error) {
            console.error('❌ Error validating Mercado order:', error);
            return {
                success: false,
                error: error.message || 'Network error connecting to Mercado API'
            };
        }
    },
    _isSameDay(dateString) {
        if (!dateString) return false;
        
        try {
            const orderDate = new Date(dateString);
            const today = new Date();
            
            return orderDate.getFullYear() === today.getFullYear() &&
                   orderDate.getMonth() === today.getMonth() &&
                   orderDate.getDate() === today.getDate();
        } catch (error) {
            console.error('Error parsing date:', error);
            return false;
        }
    },
});
