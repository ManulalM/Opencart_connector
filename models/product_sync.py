import base64
import io
import logging
import os

from odoo import models, fields

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
                        self._sync_product_image(cursor, prefix, existing.opencart_product_id, product, config)
                        existing.write({
                            'last_sync': fields.Datetime.now(),
                            'sync_status': 'success',
                            'sync_message': 'Updated',
                        })
                    else:
                        oc_id = self._insert_oc_product(cursor, prefix, product)
                        self._sync_product_image(cursor, prefix, oc_id, product, config)
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

    # ── Image sync ──────────────────────────────────────────────

    def _sync_product_image(self, cursor, prefix, oc_product_id, product, config):
        """Sync main product image from Odoo to OpenCart.

        Tries local file write first (same server). Falls back to SFTP.
        """
        if not config.opencart_image_path:
            _logger.warning('OpenCart image path not configured — skipping image sync.')
            return

        image_subdir = 'catalog/odoo'
        image_filename = f'product_{product.id}.jpg'
        oc_relative_path = f'{image_subdir}/{image_filename}'

        # Check current image in OpenCart DB
        cursor.execute(
            f"SELECT image FROM {prefix}product WHERE product_id = %s",
            (oc_product_id,),
        )
        row = cursor.fetchone()
        current_oc_image = (row or {}).get('image', '') or ''

        if product.image_1920:
            # ── Upload image ──
            image_data = base64.b64decode(product.image_1920)
            self._write_image(config, image_subdir, image_filename, image_data)
            # Update DB path
            if current_oc_image != oc_relative_path:
                cursor.execute(
                    f"UPDATE {prefix}product SET image = %s, date_modified = NOW() WHERE product_id = %s",
                    (oc_relative_path, oc_product_id),
                )
            _logger.info('Image synced for product %s (oc_id=%s)', product.name, oc_product_id)
        else:
            # ── Image removed in Odoo → clear in OpenCart ──
            if current_oc_image:
                self._remove_image(config, current_oc_image)
                cursor.execute(
                    f"UPDATE {prefix}product SET image = '', date_modified = NOW() WHERE product_id = %s",
                    (oc_product_id,),
                )
                _logger.info('Image removed for product %s (oc_id=%s)', product.name, oc_product_id)

    def _write_image(self, config, subdir, filename, image_bytes):
        """Write image to OpenCart's image directory. Local first, SFTP fallback."""
        local_dir = os.path.join(config.opencart_image_path, subdir)
        local_path = os.path.join(local_dir, filename)

        # Try local write (same server)
        if os.path.isdir(config.opencart_image_path):
            os.makedirs(local_dir, exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(image_bytes)
            _logger.info('Image written locally: %s', local_path)
            return

        # Fallback to SFTP (remote server)
        if config.sftp_user:
            self._upload_image_sftp(config, subdir, filename, image_bytes)
            return

        _logger.error(
            'Cannot write image: OpenCart path %s not found locally and SFTP not configured.',
            config.opencart_image_path,
        )

    def _remove_image(self, config, oc_relative_path):
        """Remove image file. Local first, SFTP fallback."""
        local_path = os.path.join(config.opencart_image_path, oc_relative_path)

        if os.path.isfile(local_path):
            os.remove(local_path)
            _logger.info('Image deleted locally: %s', local_path)
            return

        if config.sftp_user:
            self._delete_image_sftp(config, oc_relative_path)
            return

        _logger.info('Image file not found locally: %s', local_path)

    def _upload_image_sftp(self, config, subdir, filename, image_bytes):
        """Upload image bytes to OpenCart server via SFTP."""
        sftp = transport = None
        try:
            sftp, transport = config.get_sftp_connection()
            remote_dir = os.path.join(config.opencart_image_path, subdir)
            self._sftp_makedirs(sftp, remote_dir)
            remote_path = os.path.join(remote_dir, filename)
            with sftp.open(remote_path, 'wb') as f:
                f.write(image_bytes)
            _logger.info('Image uploaded via SFTP: %s', remote_path)
        except Exception as e:
            _logger.error('SFTP image upload failed: %s', e)
            raise
        finally:
            if sftp:
                sftp.close()
            if transport:
                transport.close()

    def _delete_image_sftp(self, config, oc_relative_path):
        """Delete image file from OpenCart server via SFTP."""
        sftp = transport = None
        try:
            sftp, transport = config.get_sftp_connection()
            remote_path = os.path.join(config.opencart_image_path, oc_relative_path)
            try:
                sftp.remove(remote_path)
                _logger.info('Image deleted via SFTP: %s', remote_path)
            except FileNotFoundError:
                pass
        except Exception as e:
            _logger.error('SFTP image delete failed: %s', e)
        finally:
            if sftp:
                sftp.close()
            if transport:
                transport.close()

    @staticmethod
    def _sftp_makedirs(sftp, remote_dir):
        """Recursively create remote directories."""
        dirs_to_create = []
        current = remote_dir
        while True:
            try:
                sftp.stat(current)
                break
            except FileNotFoundError:
                dirs_to_create.append(current)
                current = os.path.dirname(current)
                if current == '/' or not current:
                    break
        for d in reversed(dirs_to_create):
            try:
                sftp.mkdir(d)
            except OSError:
                pass
