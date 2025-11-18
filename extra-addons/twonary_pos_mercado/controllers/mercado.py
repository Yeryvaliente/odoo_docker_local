# -*- coding: utf-8 -*-

import json
import logging
import requests
from odoo import http
from odoo.http import request
from datetime import datetime


_logger = logging.getLogger(__name__)


class MercadoController(http.Controller):

    @http.route('/api/mercado/validate-note', type='json', auth='user', methods=['POST'], csrf=False)
    def validate_note(self):
        """
        Endpoint para validar notas de Mercado y obtener el totalCost
        Extrae el orderId de la nota y consulta la API de Mercado
        """
        try:
            # Obtener datos del request
            data = json.loads(request.httprequest.data.decode('utf-8'))
            note = data.get('note', '')
            sku = data.get('sku', '')
            
            _logger.info('🔍 Mercado note validation started - Note: %s, SKU: %s', note, sku)
            
            # Extraer orderId de la nota (formato esperado: "2788320" o similar)
            try:
                order_id = int(note.strip())
            except (ValueError, AttributeError):
                _logger.warning('❌ Invalid order ID in note: %s', note)
                return {
                    'success': False,
                    'error': 'Invalid order ID format in note',
                    'note': note
                }
            
            # Obtener token desde configuración global
            mercado_token = request.env['ir.config_parameter'].sudo().get_param('mercado.api.token')
            if not mercado_token:
                _logger.error('❌ Mercado API token not configured in ir.config_parameter')
                return {
                    'success': False,
                    'error': 'Mercado API token not configured'
                }
            
            # Llamar a API de Mercado
            mercado_response = self._call_mercado_api(order_id, mercado_token)
            
            if not mercado_response:
                return {
                    'success': False,
                    'error': 'Failed to fetch order from Mercado',
                    'order_id': order_id
                }
            
            # Extraer datos del response
            total_cost = None
            order_date = None
            
            if mercado_response.get('list') and len(mercado_response['list']) > 0:
                order_data = mercado_response['list'][0]
                total_cost = order_data.get('totalCost')
                
                # Intentar obtener la fecha de la orden (orderCreatedDate o deliveryDateReal)
                order_created_timestamp = order_data.get('orderCreatedDate')
                if order_created_timestamp:
                    # Convertir timestamp de milisegundos a ISO format
                    order_date = datetime.fromtimestamp(order_created_timestamp / 1000).isoformat()
                
                _logger.info('✅ Order found in Mercado - ID: %s, Total: %s, Date: %s', 
                           order_id, total_cost, order_date)
            else:
                _logger.warning('⚠️ No order data found in Mercado response for order ID: %s', order_id)
                return {
                    'success': False,
                    'error': 'Order not found in Mercado',
                    'order_id': order_id
                }
            
            # Retornar totalCost y fecha
            return {
                'success': True,
                'totalCost': total_cost,
                'order_id': order_id,
                'orderDate': order_date
            }

        except requests.exceptions.RequestException as request_error:
            _logger.error('❌ Request error validating Mercado note: %s', str(request_error))
            return {
                'success': False,
                'error': str(request_error)
            }
        except (ValueError, KeyError) as value_error:
            _logger.error('❌ Value error validating Mercado note: %s', str(value_error))
            return {
                'success': False,
                'error': str(value_error)
            }

    def _call_mercado_api(self, order_id, token):
        """
        Llamar a la API de Mercado para obtener datos de la orden
        """
        try:
            url = 'https://api.cuballama.com/restaurantes/resources/historical'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}'
            }
            payload = {
                'pointer': 1,
                'counter': 1,
                'orderId': order_id
            }
            
            _logger.info('🌐 Calling Mercado API - URL: %s, OrderID: %s', url, order_id)
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            _logger.info('✅ Mercado API response received')
            return data
            
        except requests.exceptions.Timeout as timeout_error:
            _logger.error('❌ Timeout calling Mercado API: %s', str(timeout_error))
            return None
        except requests.exceptions.HTTPError as http_error:
            _logger.error('❌ HTTP error calling Mercado API: %s', str(http_error))
            return None
        except requests.exceptions.RequestException as request_error:
            _logger.error('❌ Request error calling Mercado API: %s', str(request_error))
            return None
        except ValueError as value_error:
            _logger.error('❌ Error parsing Mercado API response: %s', str(value_error))
            return None