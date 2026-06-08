class DeviceDetail {
    constructor() {
        this.selectedDeviceId = null;
        this.trendChart = null;
        this.refreshTimer = null;
        this.onClose = null;
    }

    init() {
        this._initTrendChart();
        this._bindEvents();
    }

    _initTrendChart() {
        const trendCtx = document.getElementById('trend-chart');
        if (!trendCtx) {
            console.warn('Trend chart canvas not found');
            return;
        }
        
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

    _bindEvents() {
        const closeBtn = document.getElementById('close-detail');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                this.hide();
            });
        }

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
    }

    async show(deviceId) {
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
            
            this._startAutoRefresh();
            
        } catch (e) {
            console.error('Failed to load device detail:', e);
        }
    }

    hide() {
        document.getElementById('device-detail-panel').style.display = 'none';
        this.selectedDeviceId = null;
        this._stopAutoRefresh();
        
        if (this.onClose) {
            this.onClose();
        }
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
        if (!this.trendChart) {
            this._initTrendChart();
        }
        
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
                            onclick="window.DeviceDetail.controlFan('${device.device_id}', ${!running})">
                        ${running ? '停止风机' : '启动风机'}
                    </button>
                    ${running ? `<button class="control-btn start" onclick="window.DeviceDetail.setFanSpeed('${device.device_id}')">
                        应用转速
                    </button>` : ''}
                </div>
            `;
        } else if (device.type === 'pump') {
            const running = device.properties?.running || false;
            
            controlsHtml = `
                <div style="display: flex; gap: 10px;">
                    <button class="control-btn ${running ? 'stop' : 'start'}" 
                            onclick="window.DeviceDetail.controlPump('${device.device_id}', ${!running})">
                        ${running ? '停止水泵' : '启动水泵'}
                    </button>
                    <button class="control-btn" style="background: #60a5fa; color: white;"
                            onclick="window.DeviceDetail.setPumpAutoMode('${device.device_id}')">
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
                this.show(deviceId);
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
                this.show(deviceId);
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
                this.show(deviceId);
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
                this.show(deviceId);
            }
        } catch (e) {
            console.error('Failed to set auto mode:', e);
        }
    }

    _startAutoRefresh() {
        this._stopAutoRefresh();
        this.refreshTimer = setInterval(() => {
            if (this.selectedDeviceId) {
                this._loadDeviceTrends(this.selectedDeviceId);
                this._refreshDeviceInfo();
            }
        }, 5000);
    }

    _stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    async _refreshDeviceInfo() {
        if (!this.selectedDeviceId) return;
        
        try {
            const response = await fetch(`/api/devices/${this.selectedDeviceId}`);
            if (response.ok) {
                const deviceData = await response.json();
                this._renderDeviceInfo(deviceData);
                this._renderDeviceControls(deviceData);
            }
        } catch (e) {
            console.error('Failed to refresh device info:', e);
        }
    }

    setOnClose(callback) {
        this.onClose = callback;
    }

    getSelectedDeviceId() {
        return this.selectedDeviceId;
    }

    isVisible() {
        return document.getElementById('device-detail-panel').style.display === 'block';
    }
}

window.DeviceDetail = new DeviceDetail();
