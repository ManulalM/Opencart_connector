from odoo import models
import logging

_logger = logging.getLogger(__name__)


class StockSync(models.TransientModel):
    _name = 'opencart.stock.sync'
    _description = 'Stock Sync: Odoo to OpenCart'

    def _get_config(self):
        return self.env['opencart.config'].search([('active', '=', True)], limit=1)

    def _cron_sync_stock(self):
        """Push Odoo stock quantities to OpenCart for all mapped products."""
        config = self._get_config()
        if not config:
            _logger.warning('No active OpenCart config found. Skipping stock sync.')
            return

        prefix = config.db_table_prefix or 'oc_'
        mappings = self.env['opencart.product.sync'].search([
            ('opencart_product_id', '>', 0),
            ('odoo_product_id', '!=', False),
        ])

        if not mappings:
            _logger.info('No product mappings found. Skipping stock sync.')
            return

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor()
        except Exception as e:
            _logger.error('MySQL connection failed during stock sync: %s', e)
            return

        try:
            updated = 0
            for mapping in mappings:
                product = mapping.odoo_product_id
                qty = product.qty_available or 0
                try:
                    cursor.execute(f"""
                        UPDATE {prefix}product
                        SET quantity = %s, date_modified = NOW()
                        WHERE product_id = %s
                    """, (int(qty), mapping.opencart_product_id))
                    updated += 1
                except Exception as e:
                    _logger.error(
                        'Failed to sync stock for product %s (OC ID %s): %s',
                        product.name, mapping.opencart_product_id, e
                    )

            conn.commit()
            _logger.info('Stock sync completed. Updated %d products.', updated)
        finally:
            cursor.close()
            conn.close()
