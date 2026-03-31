import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class OpenCartWebhook(http.Controller):
    """Receive webhook notifications from OpenCart for instant sync."""

    @http.route('/opencart/webhook/order', type='json', auth='public', methods=['POST'], csrf=False)
    def webhook_order(self):
        """Receive new/updated order from OpenCart and sync to Odoo."""
        data = request.jsonrequest
        _logger.info('Received OpenCart order webhook: %s', data.get('order_id'))

        api_key = data.get('api_key')
        if not self._validate_api_key(api_key):
            return {'status': 'error', 'message': 'Invalid API key'}

        try:
            request.env['opencart.order.sync'].sudo()._cron_sync_orders()
            return {'status': 'success', 'message': 'Order sync triggered'}
        except Exception as e:
            _logger.error('Webhook order sync failed: %s', e)
            return {'status': 'error', 'message': str(e)}

    @http.route('/opencart/webhook/customer', type='json', auth='public', methods=['POST'], csrf=False)
    def webhook_customer(self):
        """Receive new/updated customer from OpenCart and sync to Odoo."""
        data = request.jsonrequest
        _logger.info('Received OpenCart customer webhook: %s', data.get('customer_id'))

        api_key = data.get('api_key')
        if not self._validate_api_key(api_key):
            return {'status': 'error', 'message': 'Invalid API key'}

        try:
            request.env['opencart.customer.sync'].sudo()._cron_sync_customers()
            return {'status': 'success', 'message': 'Customer sync triggered'}
        except Exception as e:
            _logger.error('Webhook customer sync failed: %s', e)
            return {'status': 'error', 'message': str(e)}

    @http.route('/opencart/webhook/ping', type='json', auth='public', methods=['POST'], csrf=False)
    def webhook_ping(self):
        """Health check endpoint for OpenCart to verify connectivity."""
        return {'status': 'success', 'message': 'Odoo webhook is active'}

    def _validate_api_key(self, api_key):
        """Validate the API key against the active OpenCart config."""
        if not api_key:
            return False
        config = request.env['opencart.config'].sudo().search([
            ('active', '=', True),
            ('api_key', '!=', False),
        ], limit=1)
        return config and config.api_key == api_key
