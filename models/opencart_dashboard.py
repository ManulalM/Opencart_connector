from odoo import models, api
from datetime import datetime, timedelta


class OpenCartDashboard(models.Model):
    _name = 'opencart.dashboard'
    _description = 'OpenCart Dashboard'

    @api.model
    def get_dashboard_data(self, days=7):
        """Returns all data needed for the dashboard.

        :param days: Number of days for chart history (7 or 30).
        """
        ProductSync = self.env['opencart.product.sync']
        OrderSync = self.env['opencart.order.sync']
        CustomerSync = self.env['opencart.customer.sync']
        SyncLog = self.env['opencart.sync.log']

        # ── Counts ──
        total_products = ProductSync.search_count([])
        failed_products = ProductSync.search_count([('sync_status', '=', 'failed')])
        success_products = total_products - failed_products

        total_orders = OrderSync.search_count([])
        failed_orders = OrderSync.search_count([('sync_status', '=', 'failed')])
        success_orders = total_orders - failed_orders

        total_customers = CustomerSync.search_count([])
        failed_customers = CustomerSync.search_count([('sync_status', '=', 'failed')])
        success_customers = total_customers - failed_customers

        # ── Today counts ──
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        products_today = ProductSync.search_count([
            ('last_sync', '>=', today_start.strftime('%Y-%m-%d %H:%M:%S')),
        ])
        orders_today = OrderSync.search_count([
            ('last_sync', '>=', today_start.strftime('%Y-%m-%d %H:%M:%S')),
        ])
        customers_today = CustomerSync.search_count([
            ('last_sync', '>=', today_start.strftime('%Y-%m-%d %H:%M:%S')),
        ])

        # ── Pending (failed that need retry) ──
        pending_count = (failed_products + failed_orders + failed_customers)

        # ── Last sync time ──
        last_product = ProductSync.search([], order='last_sync desc', limit=1)
        last_order = OrderSync.search([], order='last_sync desc', limit=1)
        last_customer = CustomerSync.search([], order='last_sync desc', limit=1)

        times = []
        if last_product and last_product.last_sync:
            times.append(last_product.last_sync)
        if last_order and last_order.last_sync:
            times.append(last_order.last_sync)
        if last_customer and last_customer.last_sync:
            times.append(last_customer.last_sync)
        last_sync = max(times).strftime('%Y-%m-%d %H:%M:%S') if times else 'Never'

        # ── Last sync status ──
        last_log = SyncLog.search([], order='create_date desc', limit=1)
        last_sync_status = last_log.status if last_log else 'none'

        # ── Recent logs (last 10) ──
        recent_logs = []
        for log in SyncLog.search([], order='create_date desc', limit=10):
            recent_logs.append({
                'id': log.id,
                'sync_type': log.sync_type,
                'status': log.status,
                'summary': log.summary or '',
                'detail': log.detail or '',
                'direction': log.direction or '',
                'create_date': log.create_date.strftime('%Y-%m-%d %H:%M:%S') if log.create_date else '',
            })

        # ── Chart data (N days) ──
        days = max(1, min(days, 90))
        chart_labels = []
        chart_products = []
        chart_orders = []
        chart_customers = []

        for i in range(days - 1, -1, -1):
            day = datetime.now() - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
            ds = day_start.strftime('%Y-%m-%d %H:%M:%S')
            de = day_end.strftime('%Y-%m-%d %H:%M:%S')

            chart_labels.append(day.strftime('%b %d'))
            chart_products.append(ProductSync.search_count([
                ('last_sync', '>=', ds), ('last_sync', '<=', de),
            ]))
            chart_orders.append(OrderSync.search_count([
                ('last_sync', '>=', ds), ('last_sync', '<=', de),
            ]))
            chart_customers.append(CustomerSync.search_count([
                ('last_sync', '>=', ds), ('last_sync', '<=', de),
            ]))

        return {
            # KPI cards
            'total_products': total_products,
            'success_products': success_products,
            'failed_products': failed_products,
            'products_today': products_today,

            'total_orders': total_orders,
            'success_orders': success_orders,
            'failed_orders': failed_orders,
            'orders_today': orders_today,

            'total_customers': total_customers,
            'success_customers': success_customers,
            'failed_customers': failed_customers,
            'customers_today': customers_today,

            'pending_count': pending_count,
            'last_sync': last_sync,
            'last_sync_status': last_sync_status,

            # Recent activity
            'recent_logs': recent_logs,

            # Chart
            'chart_labels': chart_labels,
            'chart_products': chart_products,
            'chart_orders': chart_orders,
            'chart_customers': chart_customers,
        }

    @api.model
    def trigger_sync(self, sync_type):
        """Trigger a manual sync from the dashboard."""
        if sync_type == 'product':
            self.env['opencart.product.sync']._cron_sync_products()
        elif sync_type == 'order':
            self.env['opencart.order.sync']._cron_sync_orders()
        elif sync_type == 'customer':
            self.env['opencart.customer.sync']._cron_sync_customers()
        elif sync_type == 'stock':
            self.env['opencart.stock.sync']._cron_sync_stock()
        elif sync_type == 'all':
            self.env['opencart.customer.sync']._cron_sync_customers()
            self.env['opencart.product.sync']._cron_sync_products()
            self.env['opencart.order.sync']._cron_sync_orders()
            self.env['opencart.stock.sync']._cron_sync_stock()
        return True
