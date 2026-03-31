from odoo import models, fields


class SyncLog(models.Model):
    _name = 'opencart.sync.log'
    _description = 'OpenCart Sync Log'
    _order = 'create_date desc'
    _rec_name = 'summary'

    sync_type = fields.Selection([
        ('product', 'Product'),
        ('order', 'Order'),
        ('customer', 'Customer'),
        ('stock', 'Stock'),
    ], string='Sync Type', required=True, index=True)

    direction = fields.Selection([
        ('push', 'Odoo → OpenCart'),
        ('pull', 'OpenCart → Odoo'),
    ], string='Direction', default='push')

    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Status', required=True, index=True)

    summary = fields.Char(string='Summary')
    detail = fields.Text(string='Details / Error')

    odoo_ref = fields.Char(string='Odoo Reference', help='e.g. product.template,42')
    opencart_ref = fields.Char(string='OpenCart Reference', help='e.g. product_id=18')

    duration = fields.Float(string='Duration (s)', digits=(8, 3))

    @staticmethod
    def _log(env, sync_type, status, summary, detail='', direction='push',
             odoo_ref='', opencart_ref='', duration=0.0):
        """Helper to create a log entry from anywhere."""
        env['opencart.sync.log'].sudo().create({
            'sync_type': sync_type,
            'status': status,
            'summary': summary,
            'detail': detail or '',
            'direction': direction,
            'odoo_ref': odoo_ref,
            'opencart_ref': opencart_ref,
            'duration': duration,
        })
