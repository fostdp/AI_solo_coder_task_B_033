class AssetManagerComponent {
    constructor() {
        this.assets = [];
        this.predictions = [];
        this.maintenancePlans = [];
        this.currentTab = 'assets';
        this.lifeDistributionChart = null;
        this.riskDistributionChart = null;
        this.containerId = 'asset-manager';
        this.isInitialized = false;
    }

    init(options = {}) {
        if (this.isInitialized) return;

        this.containerId = options.containerId || this.containerId;
        this.assets = options.initialAssets || [];
        this.predictions = options.initialPredictions || [];
        this.maintenancePlans = options.initialPlans || [];
        this.currentTab = options.initialTab || 'assets';

        this.bindEvents();
        this.isInitialized = true;
        console.log('AssetManagerComponent initialized');
    }

    render() {
        if (!this.isInitialized) {
            this.init();
        }

        this.renderAssetSummary();
        this.renderAssetsTable();
        this.renderPredictionCharts();
        this.renderMaintenancePlan();
    }

    update(data = {}) {
        if (data.assets !== undefined) {
            this.assets = data.assets;
        }
        if (data.predictions !== undefined) {
            this.predictions = data.predictions;
        }
        if (data.maintenancePlans !== undefined) {
            this.maintenancePlans = data.maintenancePlans;
        }
        if (data.currentTab !== undefined) {
            this.currentTab = data.currentTab;
        }

        this.render();
    }

    bindEvents() {
        const searchInput = document.getElementById('asset-search');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                this.renderAssetsTable();
            });
        }

        const typeFilter = document.getElementById('asset-type-filter');
        if (typeFilter) {
            typeFilter.addEventListener('change', () => {
                this.renderAssetsTable();
            });
        }

        const riskFilter = document.getElementById('asset-risk-filter');
        if (riskFilter) {
            riskFilter.addEventListener('change', () => {
                this.renderAssetsTable();
            });
        }

        const tabBtns = document.querySelectorAll('.assets-tabs .tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabName = e.target.dataset.assetsTab;
                if (tabName) {
                    this.switchTab(tabName);
                }
            });
        });

        const generatePlanBtn = document.getElementById('generate-monthly-plan');
        if (generatePlanBtn) {
            generatePlanBtn.addEventListener('click', () => {
                this.generateMonthlyPlan();
            });
        }
    }

    async fetchAssets() {
        try {
            const response = await fetch('/api/assets');
            if (response.ok) {
                const data = await response.json();
                this.update({ assets: data.assets || [] });
                return this.assets;
            }
        } catch (error) {
            console.error('Failed to fetch assets:', error);
        }
        return [];
    }

    async fetchPredictions() {
        try {
            const response = await fetch('/api/assets/life-predictions');
            if (response.ok) {
                const data = await response.json();
                this.update({ predictions: data.predictions || [] });
                return this.predictions;
            }
        } catch (error) {
            console.error('Failed to fetch predictions:', error);
        }
        return [];
    }

    async fetchMaintenancePlans(year, month) {
        try {
            const url = year && month
                ? `/api/assets/maintenance-plans?year=${year}&month=${month}`
                : '/api/assets/maintenance-plans';
            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                this.update({ maintenancePlans: data.plans || [] });
                return this.maintenancePlans;
            }
        } catch (error) {
            console.error('Failed to fetch maintenance plans:', error);
        }
        return [];
    }

    renderAssetSummary() {
        const highRiskCount = this.assets.filter(a =>
            a.risk_level === 'high' || a.risk_level === 'critical'
        ).length;

        const pendingMaintenance = this.assets.filter(a =>
            a.remaining_life_years !== undefined && a.remaining_life_years < 1
        ).length;

        const highRiskElem = document.getElementById('high-risk-assets');
        if (highRiskElem) {
            highRiskElem.textContent = highRiskCount;
        }

        const pendingElem = document.getElementById('pending-maintenance');
        if (pendingElem) {
            pendingElem.textContent = pendingMaintenance;
        }
    }

    renderAssetsTable() {
        const tbody = document.getElementById('assets-table-body');
        if (!tbody) return;

        const searchTerm = document.getElementById('asset-search')?.value?.toLowerCase() || '';
        const typeFilter = document.getElementById('asset-type-filter')?.value || 'all';
        const riskFilter = document.getElementById('asset-risk-filter')?.value || 'all';

        const filteredAssets = this.assets.filter(asset => {
            const matchesSearch = !searchTerm ||
                asset.device_id.toLowerCase().includes(searchTerm) ||
                (asset.name && asset.name.toLowerCase().includes(searchTerm));
            const matchesType = typeFilter === 'all' || asset.type === typeFilter;
            const matchesRisk = riskFilter === 'all' || asset.risk_level === riskFilter;
            return matchesSearch && matchesType && matchesRisk;
        });

        tbody.innerHTML = filteredAssets.map(asset => `
            <tr class="asset-row">
                <td>${asset.device_id}</td>
                <td>${asset.name || '-'}</td>
                <td>${this.getTypeText(asset.type)}</td>
                <td>${asset.manufacturer || '-'}</td>
                <td>${asset.installation_date ? new Date(asset.installation_date).toLocaleDateString() : '-'}</td>
                <td>${asset.design_life_years ? asset.design_life_years.toFixed(1) + '年' : '-'}</td>
                <td>
                    <span class="life-value ${this.getLifeClass(asset.remaining_life_years)}">
                        ${asset.remaining_life_years !== undefined ?
                            asset.remaining_life_years.toFixed(1) + '年' : '-'}
                    </span>
                </td>
                <td>
                    <span class="risk-badge ${asset.risk_level || 'low'}">
                        ${this.getRiskText(asset.risk_level || 'low')}
                    </span>
                </td>
                <td>
                    <button class="action-btn small"
                        onclick="assetManager.showAssetDetail('${asset.device_id}')">
                        详情
                    </button>
                    <button class="action-btn small warning"
                        onclick="assetManager.createMaintenance('${asset.device_id}')">
                        维修
                    </button>
                </td>
            </tr>
        `).join('');
    }

    renderPredictionCharts() {
        this.renderLifeDistributionChart();
        this.renderRiskDistributionChart();
    }

    renderLifeDistributionChart() {
        const ctx = document.getElementById('life-distribution-chart');
        if (!ctx) return;

        if (this.lifeDistributionChart) {
            this.lifeDistributionChart.destroy();
        }

        const ranges = ['<1年', '1-3年', '3-5年', '5-10年', '>10年'];
        const counts = [0, 0, 0, 0, 0];

        this.predictions.forEach(p => {
            const life = p.remaining_life_years;
            if (life < 1) counts[0]++;
            else if (life < 3) counts[1]++;
            else if (life < 5) counts[2]++;
            else if (life < 10) counts[3]++;
            else counts[4]++;
        });

        this.lifeDistributionChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ranges,
                datasets: [{
                    label: '设备数量',
                    data: counts,
                    backgroundColor: ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6'],
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }

    renderRiskDistributionChart() {
        const ctx = document.getElementById('risk-distribution-chart');
        if (!ctx) return;

        if (this.riskDistributionChart) {
            this.riskDistributionChart.destroy();
        }

        const risks = ['low', 'medium', 'high', 'critical'];
        const counts = [0, 0, 0, 0];

        this.predictions.forEach(p => {
            const idx = risks.indexOf(p.risk_level || 'low');
            if (idx >= 0) counts[idx]++;
        });

        this.riskDistributionChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['低风险', '中风险', '高风险', '严重风险'],
                datasets: [{
                    data: counts,
                    backgroundColor: ['#22c55e', '#eab308', '#f97316', '#ef4444'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    renderMaintenancePlan() {
        const tasksContainer = document.getElementById('maintenance-tasks');
        if (!tasksContainer || this.maintenancePlans.length === 0) return;

        const latestPlan = this.maintenancePlans[0];
        const tasks = latestPlan.tasks || [];

        const totalTasks = tasks.length;
        const highPriority = tasks.filter(t => t.priority === 'high').length;
        const completed = tasks.filter(t => t.status === 'completed').length;
        const totalHours = tasks.reduce((sum, t) => sum + (t.estimated_hours || 0), 0);

        document.getElementById('maint-total').textContent = totalTasks;
        document.getElementById('maint-high').textContent = highPriority;
        document.getElementById('maint-completed').textContent = completed;
        document.getElementById('maint-hours').textContent = totalHours.toFixed(1) + ' h';
        document.getElementById('monthly-tasks').textContent = totalTasks;

        tasks.sort((a, b) => {
            const priorityOrder = { high: 0, medium: 1, low: 2 };
            return (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3);
        });

        tasksContainer.innerHTML = tasks.map(task => `
            <div class="maintenance-task ${task.priority} ${task.status}">
                <div class="task-header">
                    <span class="task-priority">${this.getPriorityText(task.priority)}</span>
                    <span class="task-status">${this.getTaskStatusText(task.status)}</span>
                </div>
                <div class="task-body">
                    <div class="task-title">${task.task_name}</div>
                    <div class="task-details">
                        <span>设备: ${task.device_id}</span>
                        <span>预计工时: ${task.estimated_hours?.toFixed(1) || '0'}h</span>
                        ${task.scheduled_date ?
                            `<span>计划日期: ${new Date(task.scheduled_date).toLocaleDateString()}</span>` : ''}
                    </div>
                    ${task.description ? `<div class="task-desc">${task.description}</div>` : ''}
                </div>
                <div class="task-actions">
                    ${task.status !== 'completed' ? `
                        <button class="action-btn small"
                            onclick="assetManager.completeTask('${latestPlan.plan_id}', '${task.task_id}')">
                            标记完成
                        </button>
                    ` : '<span class="completed-badge">✓ 已完成</span>'}
                </div>
            </div>
        `).join('');
    }

    async generateMonthlyPlan() {
        if (confirm('确认生成本月维修计划？\n这将基于设备状态和寿命预测自动生成。')) {
            try {
                const now = new Date();
                const year = now.getFullYear();
                const month = now.getMonth() + 1;
                const response = await fetch(
                    `/api/assets/maintenance-plans/generate?year=${year}&month=${month}`,
                    { method: 'POST' }
                );
                if (response.ok) {
                    alert('维修计划生成成功');
                    await this.fetchMaintenancePlans();
                }
            } catch (error) {
                console.error('Failed to generate maintenance plan:', error);
                alert('生成失败');
            }
        }
    }

    async completeTask(planId, taskId) {
        try {
            const response = await fetch(
                `/api/assets/maintenance-plans/${planId}/execute?task_id=${taskId}`,
                { method: 'POST' }
            );
            if (response.ok) {
                await this.fetchMaintenancePlans();
            }
        } catch (error) {
            console.error('Failed to complete task:', error);
        }
    }

    showAssetDetail(deviceId) {
        const asset = this.assets.find(a => a.device_id === deviceId);
        if (asset) {
            alert(`设备详情:\n\n编号: ${asset.device_id}\n名称: ${asset.name}\n类型: ${this.getTypeText(asset.type)}\n制造商: ${asset.manufacturer}\n安装日期: ${asset.installation_date ? new Date(asset.installation_date).toLocaleDateString() : '-'}\n设计寿命: ${asset.design_life_years?.toFixed(1) || '-'}年\n剩余寿命: ${asset.remaining_life_years?.toFixed(1) || '-'}年\n风险等级: ${this.getRiskText(asset.risk_level || 'low')}\n维护次数: ${asset.maintenance_count || 0}\n故障次数: ${asset.failure_count || 0}`);
        }
    }

    createMaintenance(deviceId) {
        if (confirm(`确认要为 ${deviceId} 创建维修任务？`)) {
            alert('维修任务创建功能 - 演示版本');
        }
    }

    getTypeText(type) {
        const texts = {
            env_sensor: '环境传感器',
            fiber_sensor: '光纤传感器',
            smoke_sensor: '烟雾传感器',
            inspection_robot: '巡检机器人',
            fan: '风机',
            pump: '排水泵',
            manhole: '井盖传感器',
            fire_door: '防火门',
            fire_extinguisher: '灭火装置'
        };
        return texts[type] || type;
    }

    getRiskText(risk) {
        const texts = {
            low: '低风险',
            medium: '中风险',
            high: '高风险',
            critical: '严重风险'
        };
        return texts[risk] || risk;
    }

    getPriorityText(priority) {
        const texts = { high: '高优先级', medium: '中优先级', low: '低优先级' };
        return texts[priority] || priority;
    }

    getTaskStatusText(status) {
        const texts = { pending: '待执行', in_progress: '进行中', completed: '已完成', cancelled: '已取消' };
        return texts[status] || status;
    }

    getLifeClass(life) {
        if (life === undefined) return '';
        if (life < 1) return 'critical';
        if (life < 3) return 'warning';
        if (life < 5) return 'attention';
        return 'normal';
    }

    openModal() {
        const modal = document.getElementById('assets-modal');
        if (modal) {
            modal.style.display = 'block';
            this.fetchAssets();
            this.fetchPredictions();
            this.fetchMaintenancePlans();
        }
    }

    closeModal() {
        const modal = document.getElementById('assets-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    switchTab(tabName) {
        this.update({ currentTab: tabName });

        document.querySelectorAll('.assets-tabs .tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.assetsTab === tabName);
        });

        document.querySelectorAll('#assets-modal .tab-content').forEach(content => {
            content.style.display = 'none';
        });

        const activeTab = document.getElementById(`${tabName}-tab`);
        if (activeTab) {
            activeTab.style.display = 'block';
        }
    }

    destroy() {
        if (this.lifeDistributionChart) {
            this.lifeDistributionChart.destroy();
            this.lifeDistributionChart = null;
        }
        if (this.riskDistributionChart) {
            this.riskDistributionChart.destroy();
            this.riskDistributionChart = null;
        }
        this.isInitialized = false;
        console.log('AssetManagerComponent destroyed');
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = AssetManagerComponent;
} else {
    window.AssetManagerComponent = AssetManagerComponent;
    window.assetManager = new AssetManagerComponent();
}
