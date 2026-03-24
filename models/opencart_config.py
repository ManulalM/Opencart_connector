from odoo import fields, models
from odoo.exceptions import UserError


class OpencartConfig(models.Model):
    _name = 'opencart.config'
    _description = 'Opencart Connector'
    _rec_name = 'name'

    name = fields.Char(string='Configuration Name', required=True, default='Opencart Connector')
    url = fields.Char(string='URL', required=True)
    api_username = fields.Char(string='API Username')
    api_key = fields.Char(string='API Key')
    active = fields.Boolean(string='Active', default=True)

    db_host = fields.Char(string='MySQL Host', required=True, default='localhost')
    db_port = fields.Integer(string='MySQL Port', default=3306)
    db_user = fields.Char(string='MySQL User', required=True, default='ocuser')
    db_password = fields.Char(string='MySQL Password')
    db_name = fields.Char(string='MySQL Database', required=True, default='opencart_db')
    db_table_prefix = fields.Char(string='Table Prefix', default='oc_')

    @classmethod
    def _get_active_config(cls, env):
        config = env['opencart.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise UserError('No active OpenCart configuration found.')
        return config

    def get_mysql_connection(self):
        import mysql.connector
        return mysql.connector.connect(
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_password,
            database=self.db_name,
        )

    def action_test_mysql(self):
        self.ensure_one()
        try:
            conn = self.get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute(f'SELECT COUNT(*) FROM {self.db_table_prefix}product')
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'MySQL Connection Successful',
                    'message': f'Connected! OpenCart has {count} products.',
                    'type': 'success',
                }
            }
        except Exception as e:
            raise UserError(f'MySQL connection failed: {e}')

    def action_sync_products(self):
        self.ensure_one()
        self.env['opencart.product.sync']._cron_sync_products()
        return self._notify('Product sync completed.')

    def action_sync_customers(self):
        self.ensure_one()
        self.env['opencart.customer.sync']._cron_sync_customers()
        return self._notify('Customer sync completed.')

    def action_sync_orders(self):
        self.ensure_one()
        self.env['opencart.order.sync']._cron_sync_orders()
        return self._notify('Order sync completed.')

    def action_sync_stock(self):
        self.ensure_one()
        self.env['opencart.stock.sync']._cron_sync_stock()
        return self._notify('Stock sync completed.')

    def action_sync_all(self):
        self.ensure_one()
        self.env['opencart.customer.sync']._cron_sync_customers()
        self.env['opencart.product.sync']._cron_sync_products()
        self.env['opencart.order.sync']._cron_sync_orders()
        self.env['opencart.stock.sync']._cron_sync_stock()
        return self._notify('All syncs completed.')

    def _notify(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync',
                'message': message,
                'type': 'success',
            }
        }
