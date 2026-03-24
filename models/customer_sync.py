from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class CustomerSync(models.Model):
    _name = 'opencart.customer.sync'
    _description = 'Customer Sync: OpenCart to Odoo'

    partner_id = fields.Many2one('res.partner', string='Odoo Partner', ondelete='cascade')
    opencart_customer_id = fields.Integer(string='OpenCart Customer ID')
    last_sync = fields.Datetime(string='Last Synced')
    sync_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status')
    sync_message = fields.Text(string='Last Message')

    def _get_config(self):
        return self.env['opencart.config'].search([('active', '=', True)], limit=1)

    def _cron_sync_customers(self):
        """Pull OpenCart customers into Odoo as res.partner."""
        config = self._get_config()
        if not config:
            _logger.warning('No active OpenCart config found. Skipping customer sync.')
            return

        prefix = config.db_table_prefix or 'oc_'

        try:
            conn = config.get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
        except Exception as e:
            _logger.error('MySQL connection failed during customer sync: %s', e)
            return

        try:
            # Get already synced OC customer IDs
            synced = self.search([]).mapped('opencart_customer_id')
            synced_ids = tuple(synced) if synced else (0,)

            cursor.execute(f"""
                SELECT c.customer_id, c.firstname, c.lastname, c.email, c.telephone,
                       a.address_1, a.address_2, a.city, a.postcode, a.country_id as oc_country_id
                FROM {prefix}customer c
                LEFT JOIN {prefix}address a ON a.customer_id = c.customer_id
                    AND a.address_id = c.address_id
                WHERE c.customer_id NOT IN ({','.join(['%s'] * len(synced_ids))})
            """, synced_ids)

            customers = cursor.fetchall()

            for cust in customers:
                try:
                    # Look up country by OC country_id
                    country = False
                    if cust.get('oc_country_id'):
                        cursor.execute(f"""
                            SELECT iso_code_2 FROM {prefix}country
                            WHERE country_id = %s
                        """, (cust['oc_country_id'],))
                        row = cursor.fetchone()
                        if row:
                            country = self.env['res.country'].search(
                                [('code', '=', row['iso_code_2'])], limit=1)

                    partner_vals = {
                        'name': f"{cust['firstname']} {cust['lastname']}".strip(),
                        'email': cust.get('email'),
                        'phone': cust.get('telephone'),
                        'street': cust.get('address_1') or False,
                        'street2': cust.get('address_2') or False,
                        'city': cust.get('city') or False,
                        'zip': cust.get('postcode') or False,
                        'customer_rank': 1,
                    }
                    if country:
                        partner_vals['country_id'] = country.id

                    partner = self.env['res.partner'].create(partner_vals)
                    self.create({
                        'partner_id': partner.id,
                        'opencart_customer_id': cust['customer_id'],
                        'last_sync': fields.Datetime.now(),
                        'sync_status': 'success',
                        'sync_message': 'Imported',
                    })
                except Exception as e:
                    _logger.error('Failed to sync customer %s: %s', cust.get('customer_id'), e)
                    self.create({
                        'opencart_customer_id': cust['customer_id'],
                        'last_sync': fields.Datetime.now(),
                        'sync_status': 'failed',
                        'sync_message': str(e),
                    })
        finally:
            cursor.close()
            conn.close()

        _logger.info('Customer sync completed.')
