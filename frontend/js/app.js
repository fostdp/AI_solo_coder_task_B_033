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

        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.map.refresh();
            this.loadDashboardData();
        });

        document.getElementById('close-detail').addEventListener('click', () => {
            this._hideDeviceDetail();
        });

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                const tab = e.target.dataset.tab;
                document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
                document.getElementById(`${tab}-tab`).style.display = 'block';
                if (tab === 'trends' && this.selectedDeviceId) {
                    this._loadDeviceTrends(this.selectedDeviceId);
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
            'security': '🔒 安防告警'
        };
        
        document.getElementById('alert-modal-title').textContent = levelNames[alert.level] || '告警通知';
        
        let bodyHtml = `
            <div class="alert-detail-row">
                <span class="info-label">告警类型</span>
                <span class="info-value">${alert.type}</span>
            </div>
            <div class="alert-detail-row">
                <span class="info-label">设备ID</span>
                <span class="info-value">${alert.device_id}</span>
            </div>
            <div class="alert-detail-row">
                <span class="info-label">告警内容</span>
                <span class="info-value">${alert.message}</span>
            </div>
            <div class="alert-detail-row">
                <span class="info-label">当前值</span>
                <span class="info-value">${alert.value}</span>
            </div>
            <div class="alert-detail-row">
                <span class="info-label">阈值</span>
                <span class="info-value">${alert.threshold}</span>
            </div>
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
            'manhole_open': '井盖开启'
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
            const types = ['env_sensor', 'manhole', 'pump', 'fan'];
            const typeLabels = {
                'env_sensor': 'env',
                'manhole': 'manhole',
                'pump': 'pump',
                'fan': 'fan'
            };
            
            types.forEach(type => {
                const typeData = data.by_type[type] || { normal: 0, warning: 0, fault: 0, total: 0 };
                const label = typeLabels[type];
                document.getElementById(`${label}-normal`).textContent = typeData.normal;
                document.getElementById(`${label}-warning`).textContent = typeData.warning;
                document.getElementById(`${label}-fault`).textContent = typeData.fault;
            });
        }
        
        if (data.equipment) {
            document.getElementById('running-fans').textContent = `${data.equipment.fans_running} / 30`;
            document.getElementById('running-pumps').textContent = `${data.equipment.pumps_running} / 50`;
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
        
        if (data.daily && data.daily.length > 0) {
            const daily = data.daily.slice(-14);
            this.faultChart.data.labels = daily.map(d => d.date.substring(5));
            this.faultChart.data.datasets[0].data = daily.map(d => d.level1);
            this.faultChart.data.datasets[1].data = daily.map(d => d.level2);
            this.faultChart.data.datasets[2].data = daily.map(d => d.security);
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
            'fan': 'fan'
        };
        
        Object.keys(byType).forEach(type => {
            const label = typeLabels[type];
            if (label) {
                const stats = byType[type];
                document.getElementById(`${label}-normal`).textContent = stats.normal || 0;
                document.getElementById(`${label}-warning`).textContent = stats.warning || 0;
                document.getElementById(`${label}-fault`).textContent = stats.fault || 0;
            }
        });
        
        document.getElementById('total-devices').textContent = data.total_devices || 380;
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

    console.log('Device detail methods moved to DeviceDetail component');

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
