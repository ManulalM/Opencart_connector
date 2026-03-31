import logging
from odoo import models, api, fields

_logger = logging.getLogger(__name__)


class ProductTemplateRealtime(models.Model):
    """Inherit product.template to push changes to OpenCart instantly."""
    _inherit = 'product.template'

    def _push_to_opencart(self):
        """Push this product's data to OpenCart immediately."""
        config = self.env['opencart.config'].search([('active', '=', True)], limit=1)
        if not config:
            return

        prefix = config.db_table_prefix or 'oc_'
        product_sync = self.env['opencart.product.sync']

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
        except Exception as e:
            _logger.error('MySQL connection failed during realtime product push: %s', e)
            return

        try:
            for product in self:
                mapping = product_sync.search([('odoo_product_id', '=', product.id)], limit=1)
                if mapping and mapping.opencart_product_id:
                    try:
                        product_sync._update_oc_product(cursor, prefix, mapping.opencart_product_id, product)
                        product_sync._sync_product_image(cursor, prefix, mapping.opencart_product_id, product, config)
                        mapping.write({
                            'last_sync': fields.Datetime.now(),
                            'sync_status': 'success',
                            'sync_message': 'Realtime update',
                        })
                    except Exception as e:
                        _logger.error('Realtime push failed for product %s: %s', product.name, e)
                        mapping.write({
                            'sync_status': 'failed',
                            'sync_message': f'Realtime push failed: {e}',
                        })
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Push new saleable products to OpenCart immediately
        saleable = records.filtered(lambda r: r.sale_ok)
        if saleable:
            saleable._create_in_opencart()
        return records

    def _create_in_opencart(self):
        """Create new products in OpenCart and establish mapping."""
        config = self.env['opencart.config'].search([('active', '=', True)], limit=1)
        if not config:
            return

        prefix = config.db_table_prefix or 'oc_'
        product_sync = self.env['opencart.product.sync']

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
        except Exception as e:
            _logger.error('MySQL connection failed during realtime product create: %s', e)
            return

        try:
            for product in self:
                # Skip if already mapped
                existing = product_sync.search([('odoo_product_id', '=', product.id)], limit=1)
                if existing and existing.opencart_product_id:
                    continue
                try:
                    oc_id = product_sync._insert_oc_product(cursor, prefix, product)
                    product_sync._sync_product_image(cursor, prefix, oc_id, product, config)
                    vals = {
                        'odoo_product_id': product.id,
                        'opencart_product_id': oc_id,
                        'last_sync': fields.Datetime.now(),
                        'sync_status': 'success',
                        'sync_message': 'Realtime create',
                    }
                    if existing:
                        existing.write(vals)
                    else:
                        product_sync.create(vals)
                except Exception as e:
                    _logger.error('Realtime create failed for product %s: %s', product.name, e)
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def write(self, vals):
        res = super().write(vals)
        # Only push if product-relevant fields changed
        sync_fields = {
            'name', 'list_price', 'default_code', 'weight',
            'description_sale', 'qty_available', 'sale_ok',
            'image_1920',
        }
        if sync_fields & set(vals.keys()):
            self._push_to_opencart()
        return res


class StockQuantRealtime(models.Model):
    """Inherit stock.quant to push stock changes to OpenCart instantly."""
    _inherit = 'stock.quant'

    def write(self, vals):
        res = super().write(vals)
        if 'quantity' in vals or 'inventory_quantity' in vals:
            self._push_stock_to_opencart()
        return res

    def _push_stock_to_opencart(self):
        """Push stock quantity changes to OpenCart for affected products."""
        config = self.env['opencart.config'].search([('active', '=', True)], limit=1)
        if not config:
            return

        prefix = config.db_table_prefix or 'oc_'
        product_sync = self.env['opencart.product.sync']

        # Collect unique product templates from the quants
        product_templates = self.mapped('product_id.product_tmpl_id')
        if not product_templates:
            return

        mappings = product_sync.search([
            ('odoo_product_id', 'in', product_templates.ids),
            ('opencart_product_id', '>', 0),
        ])
        if not mappings:
            return

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor()
        except Exception as e:
            _logger.error('MySQL connection failed during realtime stock push: %s', e)
            return

        try:
            for mapping in mappings:
                product = mapping.odoo_product_id
                qty = product.qty_available or 0
                try:
                    cursor.execute(f"""
                        UPDATE {prefix}product
                        SET quantity = %s, date_modified = NOW()
                        WHERE product_id = %s
                    """, (int(qty), mapping.opencart_product_id))
                except Exception as e:
                    _logger.error(
                        'Realtime stock push failed for product %s: %s',
                        product.name, e
                    )
            conn.commit()
        finally:
            cursor.close()
            conn.close()


class StockMoveRealtime(models.Model):
    """Inherit stock.move to push stock after moves are done."""
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        self._push_stock_after_move()
        return res

    def _push_stock_after_move(self):
        """After stock moves are done, push updated quantities to OpenCart."""
        config = self.env['opencart.config'].search([('active', '=', True)], limit=1)
        if not config:
            return

        prefix = config.db_table_prefix or 'oc_'
        product_sync = self.env['opencart.product.sync']

        product_templates = self.mapped('product_id.product_tmpl_id')
        mappings = product_sync.search([
            ('odoo_product_id', 'in', product_templates.ids),
            ('opencart_product_id', '>', 0),
        ])
        if not mappings:
            return

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor()
        except Exception as e:
            _logger.error('MySQL connection failed during post-move stock push: %s', e)
            return

        try:
            for mapping in mappings:
                product = mapping.odoo_product_id
                qty = product.qty_available or 0
                try:
                    cursor.execute(f"""
                        UPDATE {prefix}product
                        SET quantity = %s, date_modified = NOW()
                        WHERE product_id = %s
                    """, (int(qty), mapping.opencart_product_id))
                except Exception as e:
                    _logger.error(
                        'Post-move stock push failed for product %s: %s',
                        product.name, e
                    )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
