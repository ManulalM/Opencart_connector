from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class ProductSync(models.Model):
    _name = 'opencart.product.sync'
    _description = 'Product Sync: Odoo to OpenCart'

    odoo_product_id = fields.Many2one('product.template', string='Odoo Product', ondelete='cascade')
    opencart_product_id = fields.Integer(string='OpenCart Product ID')
    last_sync = fields.Datetime(string='Last Synced')
    sync_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status')
    sync_message = fields.Text(string='Last Message')

    def _get_config(self):
        return self.env['opencart.config'].search([('active', '=', True)], limit=1)

    def _cron_sync_products(self):
        """Push Odoo products to OpenCart via MySQL."""
        config = self._get_config()
        if not config:
            _logger.warning('No active OpenCart config found. Skipping product sync.')
            return

        prefix = config.db_table_prefix or 'oc_'
        products = self.env['product.template'].search([('sale_ok', '=', True)])

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
        except Exception as e:
            _logger.error('MySQL connection failed during product sync: %s', e)
            return

        try:
            for product in products:
                existing = self.search([('odoo_product_id', '=', product.id)], limit=1)
                try:
                    if existing and existing.opencart_product_id:
                        self._update_oc_product(cursor, prefix, existing.opencart_product_id, product)
                        existing.write({
                            'last_sync': fields.Datetime.now(),
                            'sync_status': 'success',
                            'sync_message': 'Updated',
                        })
                    else:
                        oc_id = self._insert_oc_product(cursor, prefix, product)
                        vals = {
                            'odoo_product_id': product.id,
                            'opencart_product_id': oc_id,
                            'last_sync': fields.Datetime.now(),
                            'sync_status': 'success',
                            'sync_message': 'Created',
                        }
                        if existing:
                            existing.write(vals)
                        else:
                            self.create(vals)
                except Exception as e:
                    _logger.error('Failed to sync product %s: %s', product.name, e)
                    vals = {
                        'last_sync': fields.Datetime.now(),
                        'sync_status': 'failed',
                        'sync_message': str(e),
                    }
                    if existing:
                        existing.write(vals)
                    else:
                        self.create({
                            'odoo_product_id': product.id,
                            **vals,
                        })

            conn.commit()
        finally:
            cursor.close()
            conn.close()

        _logger.info('Product sync completed.')

    def _insert_oc_product(self, cursor, prefix, product):
        sku = product.default_code or ''
        price = product.list_price or 0.0
        qty = product.qty_available or 0
        weight = product.weight or 0.0

        cursor.execute(f"""
            INSERT INTO {prefix}product
                (model, sku, upc, ean, jan, isbn, mpn, location,
                 variant, override, quantity, stock_status_id, image,
                 manufacturer_id, shipping, price, points, tax_class_id,
                 date_available, weight, weight_class_id,
                 length, width, height, length_class_id,
                 subtract, minimum, rating, sort_order,
                 status, date_added, date_modified)
            VALUES (%s, %s, '', '', '', '', '', '',
                    '', '', %s, 7, '',
                    0, 1, %s, 0, 0,
                    CURDATE(), %s, 1,
                    0, 0, 0, 1,
                    1, 1, 0, 0,
                    %s, NOW(), NOW())
        """, (sku, sku, int(qty), price, weight, 1))
        oc_product_id = cursor.lastrowid

        # Insert product description for default language (1)
        cursor.execute(f"""
            INSERT INTO {prefix}product_description
                (product_id, language_id, name, description, tag,
                 meta_title, meta_description, meta_keyword)
            VALUES (%s, %s, %s, %s, '',
                    %s, '', '')
        """, (oc_product_id, 1, product.name, product.description_sale or '', product.name))

        # Insert into product_to_store (store 0 = default)
        cursor.execute(f"""
            INSERT INTO {prefix}product_to_store (product_id, store_id)
            VALUES (%s, %s)
        """, (oc_product_id, 0))

        return oc_product_id

    def _update_oc_product(self, cursor, prefix, oc_id, product):
        sku = product.default_code or ''
        price = product.list_price or 0.0
        qty = product.qty_available or 0
        weight = product.weight or 0.0

        cursor.execute(f"""
            UPDATE {prefix}product
            SET model = %s, sku = %s, quantity = %s, price = %s,
                weight = %s, status = %s, date_modified = NOW()
            WHERE product_id = %s
        """, (sku, sku, int(qty), price, weight, 1, oc_id))

        cursor.execute(f"""
            UPDATE {prefix}product_description
            SET name = %s, description = %s, meta_title = %s
            WHERE product_id = %s AND language_id = %s
        """, (product.name, product.description_sale or '', product.name, oc_id, 1))
