from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class OrderSync(models.Model):
    _name = 'opencart.order.sync'
    _description = 'Order Sync: OpenCart to Odoo'

    sale_order_id = fields.Many2one('sale.order', string='Odoo Sale Order', ondelete='cascade')
    opencart_order_id = fields.Integer(string='OpenCart Order ID')
    last_sync = fields.Datetime(string='Last Synced')
    sync_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status')
    sync_message = fields.Text(string='Last Message')

    def _get_config(self):
        return self.env['opencart.config'].search([('active', '=', True)], limit=1)

    def _cron_sync_orders(self):
        """Pull OpenCart orders into Odoo as sale.order records."""
        config = self._get_config()
        if not config:
            _logger.warning('No active OpenCart config found. Skipping order sync.')
            return

        prefix = config.db_table_prefix or 'oc_'

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
        except Exception as e:
            _logger.error('MySQL connection failed during order sync: %s', e)
            return

        try:
            # Get already synced OC order IDs
            synced = self.search([('sync_status', '=', 'success')]).mapped('opencart_order_id')
            synced_ids = tuple(synced) if synced else (0,)

            cursor.execute(f"""
                SELECT order_id, customer_id, firstname, lastname, email, telephone,
                       payment_address_1, payment_city, payment_postcode,
                       payment_country, total, currency_code, date_added
                FROM {prefix}order
                WHERE order_id NOT IN ({','.join(['%s'] * len(synced_ids))})
                  AND order_status_id > 0
                ORDER BY order_id
            """, synced_ids)

            orders = cursor.fetchall()

            for oc_order in orders:
                try:
                    partner = self._get_or_create_partner(oc_order)
                    order_lines = self._get_order_lines(cursor, prefix, oc_order['order_id'])

                    so_vals = {
                        'partner_id': partner.id,
                        'date_order': oc_order.get('date_added'),
                        'origin': f"OC-{oc_order['order_id']}",
                        'order_line': order_lines,
                    }

                    sale_order = self.env['sale.order'].create(so_vals)
                    self.create({
                        'sale_order_id': sale_order.id,
                        'opencart_order_id': oc_order['order_id'],
                        'last_sync': fields.Datetime.now(),
                        'sync_status': 'success',
                        'sync_message': f'Imported as {sale_order.name}',
                    })
                except Exception as e:
                    _logger.error('Failed to sync order %s: %s', oc_order.get('order_id'), e)
                    self.create({
                        'opencart_order_id': oc_order['order_id'],
                        'last_sync': fields.Datetime.now(),
                        'sync_status': 'failed',
                        'sync_message': str(e),
                    })
        finally:
            cursor.close()
            conn.close()

        _logger.info('Order sync completed.')

    def _get_or_create_partner(self, oc_order):
        """Find existing partner by OC customer_id mapping or email, or create new."""
        # Check customer sync mapping first
        if oc_order.get('customer_id'):
            cust_sync = self.env['opencart.customer.sync'].search([
                ('opencart_customer_id', '=', oc_order['customer_id']),
                ('partner_id', '!=', False),
            ], limit=1)
            if cust_sync:
                return cust_sync.partner_id

        # Fallback: search by email
        if oc_order.get('email'):
            partner = self.env['res.partner'].search([('email', '=', oc_order['email'])], limit=1)
            if partner:
                return partner

        # Create new partner
        return self.env['res.partner'].create({
            'name': f"{oc_order.get('firstname', '')} {oc_order.get('lastname', '')}".strip() or 'OpenCart Customer',
            'email': oc_order.get('email'),
            'phone': oc_order.get('telephone'),
            'street': oc_order.get('payment_address_1') or False,
            'city': oc_order.get('payment_city') or False,
            'zip': oc_order.get('payment_postcode') or False,
            'customer_rank': 1,
        })

    def _get_order_lines(self, cursor, prefix, oc_order_id):
        """Fetch OC order products and return Odoo sale.order.line vals."""
        cursor.execute(f"""
            SELECT name, model, quantity, price, total, tax
            FROM {prefix}order_product
            WHERE order_id = %s
        """, (oc_order_id,))

        lines = []
        for item in cursor.fetchall():
            # Try to find Odoo product by SKU/model
            product = False
            if item.get('model'):
                product = self.env['product.product'].search([
                    ('default_code', '=', item['model'])
                ], limit=1)

            lines.append((0, 0, {
                'product_id': product.id if product else False,
                'name': item.get('name', 'OpenCart Product'),
                'product_uom_qty': item.get('quantity', 1),
                'price_unit': item.get('price', 0.0),
            }))

        return lines
