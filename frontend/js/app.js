class App {
    constructor() {
        this.map = new TunnelMap();
        this.deviceDetail = window.DeviceDetail;
        this.ws = null;
        this.currentDevice = null;
        this.charts = {};
        this.healthScoreChart = null;
        this.faultChart = null;
        this.selectedDeviceId = null;
    }

    init() {
        this.map.init();
        if (this.deviceDetail) {
            this.deviceDetail.init();
            this.deviceDetail.setOnClose(() => {
                this.selectedDeviceId = null;
            });
        }
        this._bindEvents();
        this._initCharts();
        this._connectWebSocket();
        this._startDataRefresh();
        this.loadDashboardData();
        this._loadNewFeatureData();
        this._startNewFeatureRefresh();
        
        if (window.robotInspector) {
            window.robotInspector.fetchRobots().then(() => {
                window.robotInspector.startRealTimeUpdates(5000);
            });
        }
    }
    
    async _loadNewFeatureData() {
        try {
            await Promise.all([
                window.structureMonitor?.fetchStructureAlerts(),
                window.structureMonitor?.fetchHeatmapData(),
                window.fireDetector?.fetchFireAlerts(),
                window.fireDetector?.fetchZoneStatus(),
                window.robotInspector?.fetchRobots(),
                window.assetManager?.fetchAssets()
            ]);
            
            this._updateNewFeatureStats();
        } catch (e) {
            console.error('Failed to load new feature data:', e);
        }
    }
    
    _updateNewFeatureStats() {
        const structureElem = document.getElementById('fault-structural');
        if (structureElem && window.structureMonitor) {
            structureElem.textContent = window.structureMonitor.structureAlerts.filter(a =>
                a.risk_level === 'critical' || a.risk_level === 'warning'
            ).length;
        }
        
        const fireElem = document.getElementById('fault-fire');
        if (fireElem && window.fireDetector) {
            fireElem.textContent = window.fireDetector.fireAlerts.filter(a =>
                a.risk_level === 'critical' || a.risk_level === 'warning'
            ).length;
        }
    }
    
    _startNewFeatureRefresh() {
        setInterval(() => {
            this._loadNewFeatureData();
        }, 15000);
    }

    _bindEvents() {
        document.querySelectorAll('.layer-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.layer-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.map.setFilter(e.target.dataset.type, null);
            });
        });

        document.querySelectorAll('.chamber-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.chamber-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.map.setFilter(null, e.target.dataset.chamber);
            });
        });

        document.querySelectorAll('.overlay-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const isActive = e.target.classList.toggle('active');
                const overlay = e.target.dataset.overlay;
                
                if (overlay === 'structure_heatmap') {
                    window.structureMonitor.toggleHeatmap(isActive);
                } else if (overlay === 'robot_tracks') {
                    window.robotInspector.toggleTracks(isActive);
                } else if (overlay === 'fire_zones') {
                    window.fireDetector.toggleFireZones(isActive);
                }
            });
        });

        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.map.refresh();
            this.loadDashboardData();
            this._loadNewFeatureData();
        });

        document.getElementById('close-detail').addEventListener('click', () => {
            this._hideDeviceDetail();
        });

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tab = e.target.dataset.tab;
                if (tab) {
                    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                    e.target.classList.add('active');
                    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
                    document.getElementById(`${tab}-tab`).style.display = 'block';
                    if (tab === 'trends' && this.selectedDeviceId) {
                        this._loadDeviceTrends(this.selectedDeviceId);
                    }
                }
            });
        });

        document.querySelectorAll('.assets-tabs .tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tab = e.target.dataset.assetsTab;
                if (tab) {
                    window.assetManager.switchTab(tab);
                }
            });
        });

        document.getElementById('close-modal-btn').addEventListener('click', () => {
            this._hideAlertModal();
        });

        document.getElementById('acknowledge-btn').addEventListener('click', () => {
            this._acknowledgeCurrentAlert();
        });

        document.getElementById('alert-modal').addEventListener('click', (e) => {
            if (e.target.id === 'alert-modal') {
                this._hideAlertModal();
            }
        });

        document.getElementById('view-assets-btn').addEventListener('click', () => {
            window.assetManager.openModal();
        });

        document.getElementById('close-assets-modal').addEventListener('click', () => {
            window.assetManager.closeModal();
        });

        document.getElementById('assets-modal').addEventListener('click', (e) => {
            if (e.target.id === 'assets-modal') {
                window.assetManager.closeModal();
            }
        });

        document.getElementById('generate-plan-btn').addEventListener('click', () => {
            window.assetManager.generateMonthlyPlan();
        });

        document.getElementById('asset-search').addEventListener('input', () => {
            window.assetManager.renderAssetsTable();
        });

        document.getElementById('asset-type-filter').addEventListener('change', () => {
            window.assetManager.renderAssetsTable();
        });

        document.getElementById('asset-risk-filter').addEventListener('change', () => {
            window.assetManager.renderAssetsTable();
        });

        document.getElementById('close-robot-modal').addEventListener('click', () => {
            document.getElementById('robot-modal').style.display = 'none';
        });

        document.getElementById('robot-modal').addEventListener('click', (e) => {
            if (e.target.id === 'robot-modal') {
                document.getElementById('robot-modal').style.display = 'none';
            }
        });

        document.getElementById('btn-start-mission').addEventListener('click', () => {
            if (window.robotInspector.selectedRobot) {
                window.robotInspector.startMission(
                    window.robotInspector.selectedRobot.robot_id
                );
            }
        });

        document.getElementById('btn-pause-mission').addEventListener('click', () => {
            if (window.robotInspector.selectedRobot) {
                window.robotInspector.controlRobot(
                    window.robotInspector.selectedRobot.robot_id, 'pause'
                );
                document.getElementById('btn-pause-mission').style.display = 'none';
                document.getElementById('btn-resume-mission').style.display = 'inline-block';
            }
        });

        document.getElementById('btn-resume-mission').addEventListener('click', () => {
            if (window.robotInspector.selectedRobot) {
                window.robotInspector.controlRobot(
                    window.robotInspector.selectedRobot.robot_id, 'resume'
                );
                document.getElementById('btn-pause-mission').style.display = 'inline-block';
                document.getElementById('btn-resume-mission').style.display = 'none';
            }
        });

        document.getElementById('btn-return-base').addEventListener('click', () => {
            if (window.robotInspector.selectedRobot) {
                window.robotInspector.controlRobot(
                    window.robotInspector.selectedRobot.robot_id, 'return_base'
                );
            }
        });

        document.getElementById('btn-cancel-mission').addEventListener('click', () => {
            if (window.robotInspector.selectedRobot &&
                confirm('确认要取消当前任务吗？')) {
                window.robotInspector.controlRobot(
                    window.robotInspector.selectedRobot.robot_id, 'cancel'
                );
            }
        });
    }

    _initCharts() {
        this._drawHealthScoreGauge(0);
        
        const faultCtx = document.getElementById('fault-chart').getContext('2d');
        this.faultChart = new Chart(faultCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: '一级告警',
                        data: [],
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: '二级告警',
                        data: [],
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: '安防告警',
                        data: [],
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: '结构告警',
                        data: [],
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: '火灾预警',
                        data: [],
                        borderColor: '#dc2626',
                        backgroundColor: 'rgba(220, 38, 38, 0.1)',
                        fill: true,
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        display: false
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#8899aa'
                        },
                        grid: {
                            color: 'rgba(42, 63, 95, 0.5)'
                        }
                    }
                }
            }
        });

        console.log('Trend chart initialized in DeviceDetail component');
    }

    _drawHealthScoreGauge(score) {
        const canvas = document.getElementById('health-score-canvas');
        const ctx = canvas.getContext('2d');
        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const radius = 80;
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, Math.PI * 0.75, Math.PI * 2.25);
        ctx.lineWidth = 12;
        ctx.strokeStyle = 'rgba(42, 63, 95, 0.5)';
        ctx.lineCap = 'round';
        ctx.stroke();
        
        const scoreAngle = Math.PI * 0.75 + (score / 100) * Math.PI * 1.5;
        
        let color;
        if (score >= 80) color = '#4ade80';
        else if (score >= 60) color = '#f59e0b';
        else color = '#ef4444';
        
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, Math.PI * 0.75, scoreAngle);
        ctx.lineWidth = 12;
        ctx.strokeStyle = color;
        ctx.lineCap = 'round';
        ctx.stroke();
        
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius - 20, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(26, 26, 46, 0.8)';
        ctx.fill();
        
        document.getElementById('health-score-value').textContent = score > 0 ? score : '--';
        document.getElementById('health-score-value').style.color = color;
    }

    _connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/alerts/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this._handleWebSocketMessage(data);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket disconnected, retrying...');
            setTimeout(() => this._connectWebSocket(), 5000);
        };
    }

    _handleWebSocketMessage(data) {
        if (data.type === 'alert') {
            this._handleNewAlert(data.data);
        } else if (data.type === 'alert_acknowledged') {
            this._updateAlertList();
        } else if (data.type === 'device_status') {
            this._updateDeviceStatusDisplay(data.data);
        } else if (data.type === 'structure_alert') {
            this._handleNewAlert({
                ...data.data,
                level: 'structural',
                type: 'structure_risk'
            });
            window.structureMonitor?.fetchStructureAlerts();
        } else if (data.type === 'fire_alert') {
            this._handleNewAlert({
                ...data.data,
                level: 'fire',
                type: 'fire_risk'
            });
            window.fireDetector?.fetchFireAlerts();
            window.fireDetector?.fetchZoneStatus();
        } else if (data.type === 'robot_position') {
            window.robotInspector?.handlePositionUpdate(data.data);
        }
    }

    _handleNewAlert(alert) {
        this._showAlertModal(alert);
        this._updateAlertList();
        this.loadDashboardData();
        
        if (this.map.deviceMarkers[alert.device_id]) {
            this.map.updateDeviceStatus(alert.device_id, { status: 'fault' });
        }
    }

    _showAlertModal(alert) {
        this.currentAlert = alert;
        
        const levelNames = {
            'level1': '🚨 一级气体告警',
            'level2': '⚠️ 二级窒息告警',
            'security': '🔒 安防告警',
            'structural': '🏗️ 结构风险告警',
            'fire': '🔥 火灾预警'
        };
        
        document.getElementById('alert-modal-title').textContent = levelNames[alert.level] || '告警通知';
        
        let bodyHtml = `
            <div class="alert-detail-row">
                <span class="info-label">告警类型</span>
                <span class="info-value">${alert.type || alert.level}</span>
            </div>
            <div class="alert-detail-row">
                <span class="info-label">设备ID</span>
                <span class="info-value">${alert.device_id}</span>
            </div>
            <div class="alert-detail-row">
                <span class="info-label">告警内容</span>
                <span class="info-value">${alert.message}</span>
            </div>
        `;
        
        if (alert.value !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">当前值</span>
                <span class="info-value">${alert.value}</span>
            </div>`;
        }
        
        if (alert.threshold !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">阈值</span>
                <span class="info-value">${alert.threshold}</span>
            </div>`;
        }
        
        if (alert.strain !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">应变值</span>
                <span class="info-value">${alert.strain.toFixed(1)} με</span>
            </div>`;
        }
        
        if (alert.crack_width !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">裂缝宽度</span>
                <span class="info-value">${alert.crack_width.toFixed(4)} mm</span>
            </div>`;
        }
        
        if (alert.fire_probability !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">火灾概率</span>
                <span class="info-value">${(alert.fire_probability * 100).toFixed(1)}%</span>
            </div>`;
        }
        
        if (alert.temperature !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">温度</span>
                <span class="info-value">${alert.temperature.toFixed(1)}°C</span>
            </div>`;
        }
        
        if (alert.temperature_rate !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">温度变化率</span>
                <span class="info-value">${alert.temperature_rate.toFixed(2)}°C/min</span>
            </div>`;
        }
        
        if (alert.smoke_density !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">烟雾浓度</span>
                <span class="info-value">${alert.smoke_density.toFixed(1)}%</span>
            </div>`;
        }
        
        if (alert.is_equipment_overheat !== undefined) {
            bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">类型判断</span>
                <span class="info-value" style="color: ${alert.is_equipment_overheat ? '#f59e0b' : '#ef4444'};">
                    ${alert.is_equipment_overheat ? '设备过热' : '火灾征兆'}
                </span>
            </div>`;
        }
        
        bodyHtml += `
            <div class="alert-detail-row">
                <span class="info-label">告警时间</span>
                <span class="info-value">${new Date(alert.timestamp).toLocaleString()}</span>
            </div>
        `;
        
        document.getElementById('alert-modal-body').innerHTML = bodyHtml;
        document.getElementById('alert-modal').classList.add('show');
    }

    _hideAlertModal() {
        document.getElementById('alert-modal').classList.remove('show');
        this.currentAlert = null;
    }

    async _acknowledgeCurrentAlert() {
        if (!this.currentAlert) return;
        
        try {
            const response = await fetch(`/api/alerts/${this.currentAlert._id}/acknowledge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ operator: 'admin' })
            });
            
            if (response.ok) {
                this._hideAlertModal();
                this._updateAlertList();
            }
        } catch (e) {
            console.error('Failed to acknowledge alert:', e);
        }
    }

    async _updateAlertList() {
        try {
            const response = await fetch('/api/alerts/active');
            if (response.ok) {
                const data = await response.json();
                this._renderAlertList(data.alerts);
            }
        } catch (e) {
            console.error('Failed to load alerts:', e);
        }
    }

    _renderAlertList(alerts) {
        const container = document.getElementById('active-alerts');
        
        if (alerts.length === 0) {
            container.innerHTML = '<div style="color: #667788; text-align: center; padding: 20px;">暂无活动告警</div>';
            return;
        }
        
        const typeNames = {
            'methane_high': '甲烷超标',
            'h2s_high': '硫化氢超标',
            'oxygen_low': '氧气过低',
            'temperature_high': '温度过高',
            'manhole_open': '井盖开启',
            'structure_risk': '结构风险',
            'fire_risk': '火灾预警',
            'strain_high': '应变超标',
            'crack_wide': '裂缝扩展',
            'smoke_detected': '烟雾检测',
            'temp_rise_fast': '温度骤升'
        };
        
        container.innerHTML = alerts.map(alert => `
            <div class="alert-item ${alert.level} ${alert.acknowledged ? 'acknowledged' : ''}" 
                 onclick="window.App.showDeviceDetail('${alert.device_id}')">
                <div class="alert-type">${typeNames[alert.type] || alert.type}</div>
                <div class="alert-message">${alert.message}</div>
                <div class="alert-time">${new Date(alert.timestamp).toLocaleString()}</div>
            </div>
        `).join('');
    }

    _updateDeviceStatusDisplay(data) {
        if (data.by_type) {
            const types = ['env_sensor', 'manhole', 'pump', 'fan',
                'fiber_sensor', 'smoke_sensor', 'inspection_robot',
                'fire_door', 'fire_extinguisher'];
            const typeLabels = {
                'env_sensor': 'env',
                'manhole': 'manhole',
                'pump': 'pump',
                'fan': 'fan',
                'fiber_sensor': 'fiber',
                'smoke_sensor': 'smoke',
                'inspection_robot': 'robot',
                'fire_door': 'door',
                'fire_extinguisher': 'ext'
            };
            
            types.forEach(type => {
                const typeData = data.by_type[type] || { normal: 0, warning: 0, fault: 0, total: 0 };
                const label = typeLabels[type];
                if (label) {
                    const normalElem = document.getElementById(`${label}-normal`);
                    const warningElem = document.getElementById(`${label}-warning`);
                    const faultElem = document.getElementById(`${label}-fault`);
                    
                    if (normalElem) normalElem.textContent = typeData.normal;
                    if (warningElem) warningElem.textContent = typeData.warning;
                    if (faultElem) faultElem.textContent = typeData.fault;
                }
            });
        }
        
        if (data.equipment) {
            document.getElementById('running-fans').textContent = `${data.equipment.fans_running} / 30`;
            document.getElementById('running-pumps').textContent = `${data.equipment.pumps_running} / 50`;
            
            if (data.equipment.robots_inspecting !== undefined) {
                document.getElementById('robots-inspecting').textContent = 
                    `${data.equipment.robots_inspecting} / ${data.equipment.robots_total || 5}`;
            }
            
            if (data.equipment.closed_fire_zones !== undefined) {
                document.getElementById('closed-fire-zones').textContent = 
                    `${data.equipment.closed_fire_zones} / ${data.equipment.fire_zones_total || 16}`;
            }
        }
    }

    async loadDashboardData() {
        try {
            const [healthData, faultData, envData, alertsData, deviceStats] = await Promise.all([
                fetch('/api/stats/health-score?calculate_new=true').then(r => r.json()),
                fetch('/api/stats/fault-statistics?months=1').then(r => r.json()),
                fetch('/api/sensor/data/average?hours=1').then(r => r.json()),
                fetch('/api/alerts/active').then(r => r.json()),
                fetch('/api/devices/statistics/summary').then(r => r.json())
            ]);
            
            this._updateHealthScore(healthData);
            this._updateFaultStatistics(faultData);
            this._updateEnvironmentData(envData);
            this._renderAlertList(alertsData.alerts);
            this._updateDeviceStatistics(deviceStats);
            
        } catch (e) {
            console.error('Failed to load dashboard data:', e);
        }
    }

    _updateHealthScore(data) {
        this._drawHealthScoreGauge(data.score || 0);
        
        const detailsHtml = `
            <div class="health-detail-row">
                <span>设备得分</span>
                <span>${data.details?.device_score || 0}</span>
            </div>
            <div class="health-detail-row">
                <span>预警扣减</span>
                <span style="color: #f59e0b;">-${data.details?.warning_penalty || 0}</span>
            </div>
            <div class="health-detail-row">
                <span>故障扣减</span>
                <span style="color: #ef4444;">-${data.details?.fault_penalty || 0}</span>
            </div>
            <div class="health-detail-row">
                <span>告警扣减</span>
                <span style="color: #ef4444;">-${data.details?.alert_penalty || 0}</span>
            </div>
        `;
        
        document.getElementById('health-details').innerHTML = detailsHtml;
    }

    _updateFaultStatistics(data) {
        const byLevel = data.alerts_by_level || {};
        document.getElementById('fault-level1').textContent = byLevel.level1 || 0;
        document.getElementById('fault-level2').textContent = byLevel.level2 || 0;
        document.getElementById('fault-security').textContent = byLevel.security || 0;
        document.getElementById('fault-structural').textContent = byLevel.structural || 0;
        document.getElementById('fault-fire').textContent = byLevel.fire || 0;
        
        if (data.daily && data.daily.length > 0) {
            const daily = data.daily.slice(-14);
            this.faultChart.data.labels = daily.map(d => d.date.substring(5));
            this.faultChart.data.datasets[0].data = daily.map(d => d.level1 || 0);
            this.faultChart.data.datasets[1].data = daily.map(d => d.level2 || 0);
            this.faultChart.data.datasets[2].data = daily.map(d => d.security || 0);
            this.faultChart.data.datasets[3].data = daily.map(d => d.structural || 0);
            this.faultChart.data.datasets[4].data = daily.map(d => d.fire || 0);
            this.faultChart.update();
        }
    }

    _updateEnvironmentData(data) {
        const avg = data.averages || {};
        document.getElementById('avg-temp').textContent = `${avg.temperature || '--'}°C`;
        document.getElementById('avg-humidity').textContent = `${avg.humidity || '--'}%`;
        document.getElementById('avg-oxygen').textContent = `${avg.oxygen || '--'}%`;
        document.getElementById('avg-methane').textContent = `${avg.methane || '--'}%`;
        document.getElementById('avg-h2s').textContent = `${avg.h2s || '--'}ppm`;
    }

    _updateDeviceStatistics(data) {
        const byType = data.by_type || {};
        const typeLabels = {
            'env_sensor': 'env',
            'manhole': 'manhole',
            'pump': 'pump',
            'fan': 'fan',
            'fiber_sensor': 'fiber',
            'smoke_sensor': 'smoke',
            'inspection_robot': 'robot',
            'fire_door': 'door',
            'fire_extinguisher': 'ext'
        };
        
        Object.keys(byType).forEach(type => {
            const label = typeLabels[type];
            if (label) {
                const stats = byType[type];
                const normalElem = document.getElementById(`${label}-normal`);
                const warningElem = document.getElementById(`${label}-warning`);
                const faultElem = document.getElementById(`${label}-fault`);
                
                if (normalElem) normalElem.textContent = stats.normal || 0;
                if (warningElem) warningElem.textContent = stats.warning || 0;
                if (faultElem) faultElem.textContent = stats.fault || 0;
            }
        });
        
        document.getElementById('total-devices').textContent = data.total_devices || 951;
    }

    async showDeviceDetail(deviceId) {
        this.selectedDeviceId = deviceId;
        
        if (this.deviceDetail) {
            await this.deviceDetail.show(deviceId);
        }
    }

    _hideDeviceDetail() {
        if (this.deviceDetail) {
            this.deviceDetail.hide();
        }
        this.selectedDeviceId = null;
    }

    _startDataRefresh() {
        setInterval(() => {
            this.loadDashboardData();
        }, 30000);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.App = new App();
    window.App.init();
});
