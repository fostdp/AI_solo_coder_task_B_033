class App {
    constructor() {
        this.map = new TunnelMap();
        this.ws = null;
        this.currentDevice = null;
        this.charts = {};
        this.healthScoreChart = null;
        this.faultChart = null;
        this.trendChart = null;
        this.selectedDeviceId = null;
    }

    init() {
        this.map.init();
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

        const trendCtx = document.getElementById('trend-chart').getContext('2d');
        this.trendChart = new Chart(trendCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: '温度 (°C)',
                        data: [],
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        yAxisID: 'y',
                        tension: 0.4
                    },
                    {
                        label: '湿度 (%)',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        yAxisID: 'y1',
                        tension: 0.4
                    },
                    {
                        label: '氧气 (%)',
                        data: [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        yAxisID: 'y2',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#aabbcc',
                            font: { size: 10 }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#8899aa',
                            maxTicksLimit: 6
                        },
                        grid: {
                            color: 'rgba(42, 63, 95, 0.5)'
                        }
                    },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: { display: true, text: '温度', color: '#ef4444' },
                        ticks: { color: '#8899aa' },
                        grid: { color: 'rgba(42, 63, 95, 0.3)' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: { display: true, text: '湿度', color: '#3b82f6' },
                        ticks: { color: '#8899aa' },
                        grid: { drawOnChartArea: false }
                    },
                    y2: {
                        type: 'linear',
                        display: false,
                        position: 'right',
                        title: { display: true, text: '氧气', color: '#10b981' },
                        ticks: { color: '#8899aa' },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
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
        
        try {
            const [deviceData, historyData, operationsData] = await Promise.all([
                fetch(`/api/devices/${deviceId}`).then(r => r.json()),
                fetch(`/api/devices/${deviceId}/history?hours=24`).then(r => r.json()),
                fetch(`/api/devices/${deviceId}/operations?limit=50`).then(r => r.json())
            ]);
            
            this._renderDeviceInfo(deviceData);
            this._renderDeviceHistory(historyData);
            this._renderOperations(operationsData);
            this._renderDeviceControls(deviceData);
            
            document.getElementById('device-detail-panel').style.display = 'block';
            document.getElementById('device-detail-title').textContent = `设备详情 - ${deviceData.name || deviceId}`;
            
        } catch (e) {
            console.error('Failed to load device detail:', e);
        }
    }

    _hideDeviceDetail() {
        document.getElementById('device-detail-panel').style.display = 'none';
        this.selectedDeviceId = null;
    }

    _renderDeviceInfo(device) {
        const statusText = {
            'normal': '正常',
            'warning': '预警',
            'fault': '故障'
        };
        
        const props = device.properties || {};
        const lastData = device.last_data || {};
        
        let infoHtml = `
            <div class="info-row">
                <span class="info-label">设备ID</span>
                <span class="info-value">${device.device_id}</span>
            </div>
            <div class="info-row">
                <span class="info-label">设备类型</span>
                <span class="info-value">${device.type}</span>
            </div>
            <div class="info-row">
                <span class="info-label">所属舱室</span>
                <span class="info-value">${device.chamber}</span>
            </div>
            <div class="info-row">
                <span class="info-label">里程位置</span>
                <span class="info-value">${device.distance_km} km</span>
            </div>
            <div class="info-row">
                <span class="info-label">当前状态</span>
                <span class="status-badge ${device.status}">${statusText[device.status] || device.status}</span>
            </div>
        `;
        
        if (lastData.temperature !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">温度</span><span class="info-value">${lastData.temperature}°C</span></div>`;
        }
        if (lastData.humidity !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">湿度</span><span class="info-value">${lastData.humidity}%</span></div>`;
        }
        if (lastData.oxygen !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">氧气</span><span class="info-value">${lastData.oxygen}%</span></div>`;
        }
        if (lastData.methane !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">甲烷</span><span class="info-value">${lastData.methane}%</span></div>`;
        }
        if (lastData.h2s !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">硫化氢</span><span class="info-value">${lastData.h2s} ppm</span></div>`;
        }
        if (props.running !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">运行状态</span><span class="info-value">${props.running ? '运行中' : '已停止'}</span></div>`;
        }
        if (props.speed !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">转速</span><span class="info-value">${props.speed}%</span></div>`;
        }
        if (props.level !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">液位</span><span class="info-value">${props.level}%</span></div>`;
        }
        if (props.cover_open !== undefined) {
            infoHtml += `<div class="info-row"><span class="info-label">井盖状态</span><span class="info-value">${props.cover_open ? '已开启' : '已关闭'}</span></div>`;
        }
        
        document.getElementById('device-info').innerHTML = infoHtml;
    }

    _renderDeviceHistory(history) {
        const data = history.data || [];
        
        if (data.length === 0) {
            return;
        }
        
        const labels = data.map(d => {
            const date = new Date(d.timestamp);
            return `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`;
        });
        
        const datasets = [];
        
        if (data.some(d => d.temperature !== undefined)) {
            datasets.push({
                label: '温度 (°C)',
                data: data.map(d => d.temperature),
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                yAxisID: 'y',
                tension: 0.4
            });
        }
        
        if (data.some(d => d.humidity !== undefined)) {
            datasets.push({
                label: '湿度 (%)',
                data: data.map(d => d.humidity),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                yAxisID: 'y1',
                tension: 0.4
            });
        }
        
        if (data.some(d => d.oxygen !== undefined)) {
            datasets.push({
                label: '氧气 (%)',
                data: data.map(d => d.oxygen),
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                yAxisID: 'y2',
                tension: 0.4
            });
        }
        
        this.trendChart.data.labels = labels;
        this.trendChart.data.datasets = datasets;
        this.trendChart.update();
    }

    async _loadDeviceTrends(deviceId) {
        try {
            const response = await fetch(`/api/devices/${deviceId}/history?hours=24`);
            if (response.ok) {
                const data = await response.json();
                this._renderDeviceHistory(data);
            }
        } catch (e) {
            console.error('Failed to load trends:', e);
        }
    }

    _renderOperations(operations) {
        const data = operations.operations || [];
        const container = document.getElementById('operations-list');
        
        if (data.length === 0) {
            container.innerHTML = '<div style="color: #667788; text-align: center; padding: 20px;">暂无操作记录</div>';
            return;
        }
        
        const actionNames = {
            'fan_control': '风机控制',
            'pump_control': '水泵控制',
            'set_fan_speed': '设置风机转速',
            'stop_fan': '停止风机',
            'start_pump': '启动水泵',
            'stop_pump': '停止水泵',
            'auto_mode': '切换自动模式'
        };
        
        container.innerHTML = data.map(op => `
            <div class="operation-item">
                <div>
                    <span class="operation-action">${actionNames[op.action] || op.action}</span>
                    <span class="operator"> - ${op.operator}</span>
                </div>
                <div style="margin-top: 4px;">
                    ${op.details?.running !== undefined ? `运行: ${op.details.running ? '开启' : '关闭'}` : ''}
                    ${op.details?.speed !== undefined ? ` | 转速: ${op.details.speed}%` : ''}
                </div>
                <div class="operation-time">${new Date(op.timestamp).toLocaleString()}</div>
            </div>
        `).join('');
    }

    _renderDeviceControls(device) {
        const container = document.getElementById('device-controls');
        let controlsHtml = '';
        
        if (device.type === 'fan') {
            const running = device.properties?.running || false;
            const speed = device.properties?.speed || 0;
            
            controlsHtml = `
                <div class="control-group">
                    <label>转速</label>
                    <input type="range" class="speed-slider" id="fan-speed-slider" 
                           min="0" max="100" value="${speed}" ${!running ? 'disabled' : ''}>
                    <span id="fan-speed-value">${speed}%</span>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="control-btn ${running ? 'stop' : 'start'}" 
                            onclick="window.App.controlFan('${device.device_id}', ${!running})">
                        ${running ? '停止风机' : '启动风机'}
                    </button>
                    ${running ? `<button class="control-btn start" onclick="window.App.setFanSpeed('${device.device_id}')">
                        应用转速
                    </button>` : ''}
                </div>
            `;
        } else if (device.type === 'pump') {
            const running = device.properties?.running || false;
            
            controlsHtml = `
                <div style="display: flex; gap: 10px;">
                    <button class="control-btn ${running ? 'stop' : 'start'}" 
                            onclick="window.App.controlPump('${device.device_id}', ${!running})">
                        ${running ? '停止水泵' : '启动水泵'}
                    </button>
                    <button class="control-btn" style="background: #60a5fa; color: white;"
                            onclick="window.App.setPumpAutoMode('${device.device_id}')">
                        自动模式
                    </button>
                </div>
            `;
        }
        
        container.innerHTML = controlsHtml;
        
        const slider = document.getElementById('fan-speed-slider');
        if (slider) {
            slider.addEventListener('input', (e) => {
                document.getElementById('fan-speed-value').textContent = e.target.value + '%';
            });
        }
    }

    async controlFan(deviceId, running) {
        const speed = document.getElementById('fan-speed-slider')?.value || 50;
        
        try {
            const response = await fetch(`/api/control/fan/${deviceId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    running: running,
                    speed: running ? parseInt(speed) : 0
                })
            });
            
            if (response.ok) {
                this.showDeviceDetail(deviceId);
            }
        } catch (e) {
            console.error('Failed to control fan:', e);
        }
    }

    async setFanSpeed(deviceId) {
        const speed = document.getElementById('fan-speed-slider')?.value || 50;
        
        try {
            const response = await fetch(`/api/control/fan/${deviceId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    running: true,
                    speed: parseInt(speed)
                })
            });
            
            if (response.ok) {
                this.showDeviceDetail(deviceId);
            }
        } catch (e) {
            console.error('Failed to set fan speed:', e);
        }
    }

    async controlPump(deviceId, running) {
        try {
            const response = await fetch(`/api/control/pump/${deviceId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ running: running })
            });
            
            if (response.ok) {
                this.showDeviceDetail(deviceId);
            }
        } catch (e) {
            console.error('Failed to control pump:', e);
        }
    }

    async setPumpAutoMode(deviceId) {
        try {
            const response = await fetch(`/api/control/pump/${deviceId}/auto-mode`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (response.ok) {
                this.showDeviceDetail(deviceId);
            }
        } catch (e) {
            console.error('Failed to set auto mode:', e);
        }
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
