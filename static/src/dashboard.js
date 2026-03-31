/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

class OpenCartDashboard extends Component {
    static template = "opencart_connector.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            data: null,
            loading: true,
            syncing: false,
            syncingType: "",
            chartDays: 7,
        });
        this.chartRef = useRef("chart");
        this._chart = null;

        onMounted(async () => {
            await this.loadData();
        });
        onWillUnmount(() => {
            if (this._chart) {
                this._chart.destroy();
            }
        });
    }

    async loadData() {
        this.state.loading = true;
        const data = await this.orm.call(
            "opencart.dashboard",
            "get_dashboard_data",
            [this.state.chartDays],
        );
        this.state.data = data;
        this.state.loading = false;
        setTimeout(() => this.renderChart(data), 100);
    }

    async setChartDays(days) {
        this.state.chartDays = days;
        await this.loadData();
    }

    async triggerSync(syncType) {
        this.state.syncing = true;
        this.state.syncingType = syncType;
        try {
            await this.orm.call("opencart.dashboard", "trigger_sync", [syncType]);
            this.notification.add(
                `${syncType.charAt(0).toUpperCase() + syncType.slice(1)} sync completed!`,
                { type: "success" }
            );
            await this.loadData();
        } catch (e) {
            this.notification.add(
                `Sync failed: ${e.message || "Unknown error"}`,
                { type: "danger" }
            );
        }
        this.state.syncing = false;
        this.state.syncingType = "";
    }

    openView(model, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: model,
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }

    openFailedProducts() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Failed Products",
            res_model: "opencart.product.sync",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["sync_status", "=", "failed"]],
        });
    }

    openFailedOrders() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Failed Orders",
            res_model: "opencart.order.sync",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["sync_status", "=", "failed"]],
        });
    }

    openLogs() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sync Logs",
            res_model: "opencart.sync.log",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }

    renderChart(data) {
        if (this._chart) {
            this._chart.destroy();
            this._chart = null;
        }
        const canvas = this.chartRef.el;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");

        this._chart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: data.chart_labels,
                datasets: [
                    {
                        label: "Products",
                        data: data.chart_products,
                        backgroundColor: "rgba(114, 85, 163, 0.75)",
                        borderColor: "rgba(114, 85, 163, 1)",
                        borderWidth: 1,
                        borderRadius: 4,
                        order: 2,
                    },
                    {
                        label: "Orders",
                        data: data.chart_orders,
                        backgroundColor: "rgba(52, 152, 219, 0.75)",
                        borderColor: "rgba(52, 152, 219, 1)",
                        borderWidth: 1,
                        borderRadius: 4,
                        order: 2,
                    },
                    {
                        label: "Customers",
                        data: data.chart_customers,
                        type: "line",
                        borderColor: "rgba(46, 204, 113, 1)",
                        backgroundColor: "rgba(46, 204, 113, 0.1)",
                        borderWidth: 2,
                        pointRadius: 4,
                        pointBackgroundColor: "rgba(46, 204, 113, 1)",
                        fill: true,
                        tension: 0.3,
                        order: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: "index",
                },
                plugins: {
                    legend: {
                        position: "top",
                        labels: { usePointStyle: true, padding: 20 },
                    },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1 },
                        grid: { color: "rgba(0,0,0,0.05)" },
                    },
                    x: {
                        grid: { display: false },
                    },
                },
            },
        });
    }
}

registry.category("actions").add("opencart_dashboard", OpenCartDashboard);
