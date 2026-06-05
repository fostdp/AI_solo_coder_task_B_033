const App = {
    alarms: [],
    currentAlarmId: null,
    currentDeviceId: null,
    refreshTimers: {},

    init() {
        console.log('地下管廊综合监控系统启动...');

        MapModule.init();
        WebSocketModule.init();

        this._updateSystemTime();
        setInterval(() => this._updateSystemTime(), 1000);

        this.refreshHealthScore();
        this.refreshFaultStats();
        this.refreshAlarms();

        this.refreshTimers.health = setInterval(() => {
            this.refreshHealthScore();
        }, CONFIG.HEALTH_REFRESH_INTERVAL);

        this.refreshTimers.stats = setInterval(() => {
            this.refreshFaultStats();
        }, CONFIG.HEALTH_REFRESH_INTERVAL);

        this.refreshTimers.alarms = setInterval(() => {
            this.refreshAlarms();
        }, CONFIG.REFRESH_INTERVAL);

        this.refreshTimers.map = setInterval(() => {
            MapModule.refresh();
        }, CONFIG.REFRESH_INTERVAL);

        window.addEventListener('beforeunload', () => {
            this.cleanup();
        });
    },

    cleanup() {
        Object.values(this.refreshTimers).forEach(timer => clearInterval(timer));
        WebSocketModule.close();
        ChartModule.destroyCharts();
    },

    _updateSystemTime() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
        document.getElementById('systemTime').textContent = timeStr;
    },

    async refreshHealthScore() {
        try {
            const data = await API.getHealthScore();
            this._updateHealthUI(data);
        } catch (error) {
            console.error('刷新健康度评分失败:', error);
        }
    },

    _updateHealthUI(data) {
        const overallScore = data.overall_score || 0;
        document.getElementById('overallHealthScore').textContent = overallScore;

        const scoreEl = document.getElementById('overallHealthScore');
        if (overallScore >= 80) {
            scoreEl.style.color = '#00ff88';
        } else if (overallScore >= 60) {
            scoreEl.style.color = '#ffaa00';
        } else {
            scoreEl.style.color = '#ff4444';
        }

        const componentScores = data.component_scores || {};
        this._updateHealthBar('envScore', 'envScoreBar', componentScores.env_sensors || 0);
        this._updateHealthBar('manholeScore', 'manholeScoreBar', componentScores.manholes || 0);
        this._updateHealthBar('fanScore', 'fanScoreBar', componentScores.fans || 0);
        this._updateHealthBar('pumpScore', 'pumpScoreBar', componentScores.pumps || 0);

        const cabinScores = data.cabin_scores || {};
        if (cabinScores.power) {
            document.getElementById('powerScore').textContent = cabinScores.power.score;
            document.getElementById('powerDeviceCount').textContent = cabinScores.power.details?.total_devices || '-';
            document.getElementById('powerAlarmCount').textContent = cabinScores.power.details?.active_alarms || 0;
        }
        if (cabinScores.water) {
            document.getElementById('waterScore').textContent = cabinScores.water.score;
            document.getElementById('waterDeviceCount').textContent = cabinScores.water.details?.total_devices || '-';
            document.getElementById('waterAlarmCount').textContent = cabinScores.water.details?.active_alarms || 0;
        }
        if (cabinScores.gas) {
            document.getElementById('gasScore').textContent = cabinScores.gas.score;
            document.getElementById('gasDeviceCount').textContent = cabinScores.gas.details?.total_devices || '-';
            document.getElementById('gasAlarmCount').textContent = cabinScores.gas.details?.active_alarms || 0;
        }
    },

    _updateHealthBar(valueId, barId, value) {
        document.getElementById(valueId).textContent = value;
        document.getElementById(barId).style.width = `${value}%`;

        const bar = document.getElementById(barId);
        if (value >= 80) {
            bar.style.background = 'linear-gradient(90deg, #00d4ff, #00ff88)';
        } else if (value >= 60) {
            bar.style.background = 'linear-gradient(90deg, #ffaa00, #ff6b00)';
        } else {
            bar.style.background = 'linear-gradient(90deg, #ff4444, #ff0000)';
        }
    },

    async refreshFaultStats() {
        try {
            const data = await API.getFaultStats();
            this._updateStatsUI(data);
        } catch (error) {
            console.error('刷新故障统计失败:', error);
        }
    },

    _updateStatsUI(data) {
        document.getElementById('totalAlarms').textContent = data.total_alarms || 0;
        document.getElementById('criticalAlarms').textContent = data.alarms_by_level?.critical || 0;
        document.getElementById('warningAlarms').textContent = data.alarms_by_level?.warning || 0;
        document.getElementById('faultDevices').textContent = data.current_fault_devices || 0;

        const alarmTypeData = data.alarms_by_type || {};
        if (Object.keys(alarmTypeData).length > 0) {
            ChartModule.createAlarmTypeChart(alarmTypeData);
        }
    },

    async refreshAlarms() {
        try {
            const data = await API.getAlarms(null, false, 50);
            this.alarms = data.alarms || [];
            this._renderAlarmList();
        } catch (error) {
            console.error('刷新告警列表失败:', error);
        }
    },

    _renderAlarmList() {
        const listEl = document.getElementById('alarmList');
        const badgeEl = document.getElementById('alarmBadge');

        const unacknowledged = this.alarms.filter(a => !a.acknowledged);
        badgeEl.textContent = unacknowledged.length;
        badgeEl.style.display = unacknowledged.length > 0 ? 'inline-block' : 'none';

        if (this.alarms.length === 0) {
            listEl.innerHTML = '<div class="empty-state">暂无告警</div>';
            return;
        }

        listEl.innerHTML = this.alarms.map(alarm => {
            const time = new Date(alarm.timestamp).toLocaleString('zh-CN');
            const levelText = {
                critical: '严重',
                warning: '警告',
                info: '信息'
            }[alarm.level] || alarm.level;

            const alarmName = CONFIG.ALARM_NAMES[alarm.alarm_type] || alarm.alarm_type;
            const cabinName = CONFIG.CABIN_NAMES[alarm.cabin] || alarm.cabin;

            return `
                <div class="alarm-item ${alarm.level} ${alarm.acknowledged ? 'acknowledged' : ''}" 
                     data-alarm-id="${alarm.id}"
                     onclick="App.onAlarmClick('${alarm.id}')">
                    <div class="alarm-header">
                        <span class="alarm-level ${alarm.level}">${levelText}</span>
                        <span class="alarm-time">${time}</span>
                    </div>
                    <div class="alarm-message">${alarm.message}</div>
                    <div class="alarm-device">${alarmName} · ${cabinName} · ${alarm.device_id}</div>
                </div>
            `;
        }).join('');
    },

    addAlarm(alarmData) {
        this.alarms.unshift({
            ...alarmData,
            acknowledged: false
        });

        if (this.alarms.length > 100) {
            this.alarms.pop();
        }

        this._renderAlarmList();
    },

    onAlarmClick(alarmId) {
        const alarm = this.alarms.find(a => a.id === alarmId);
        if (alarm) {
            this.showAlarmModal(alarm);
        }
    },

    showAlarmModal(alarmData) {
        const modal = document.getElementById('alarmModal');
        this.currentAlarmId = alarmData.id;

        const levelText = {
            critical: '严重告警',
            warning: '警告',
            info: '提示'
        }[alarmData.level] || '告警';

        document.getElementById('alarmModalTitle').textContent = levelText;
        document.getElementById('alarmModalMessage').textContent = alarmData.message;
        document.getElementById('alarmModalDevice').textContent = alarmData.device_id;
        document.getElementById('alarmModalCabin').textContent = CONFIG.CABIN_NAMES[alarmData.cabin] || alarmData.cabin;
        document.getElementById('alarmModalTime').textContent = new Date(alarmData.timestamp).toLocaleString('zh-CN');

        modal.classList.add('active');
    },

    closeAlarmModal() {
        document.getElementById('alarmModal').classList.remove('active');
        this.currentAlarmId = null;
    },

    async acknowledgeModalAlarm() {
        if (this.currentAlarmId) {
            try {
                await API.acknowledgeAlarm(this.currentAlarmId, 'admin');
                const alarm = this.alarms.find(a => a.id === this.currentAlarmId);
                if (alarm) {
                    alarm.acknowledged = true;
                }
                this._renderAlarmList();
                this.closeAlarmModal();
                this.refreshHealthScore();
            } catch (error) {
                console.error('确认告警失败:', error);
                alert('确认告警失败');
            }
        }
    },

    async acknowledgeAllAlarms() {
        if (!confirm('确认全部告警吗？')) return;

        try {
            const unacknowledged = this.alarms.filter(a => !a.acknowledged);
            for (const alarm of unacknowledged) {
                await API.acknowledgeAlarm(alarm.id, 'admin');
                alarm.acknowledged = true;
            }
            this._renderAlarmList();
            this.refreshHealthScore();
        } catch (error) {
            console.error('批量确认告警失败:', error);
        }
    },

    async showDeviceDetail(deviceId) {
        this.currentDeviceId = deviceId;
        const contentEl = document.getElementById('deviceDetailContent');

        try {
            const [device, trendData, historyData] = await Promise.all([
                API.getDevice(deviceId),
                API.getDeviceTrend(deviceId, 24),
                API.getDeviceHistory(deviceId, 20)
            ]);

            this._renderDeviceDetail(device, trendData, historyData);
        } catch (error) {
            console.error('获取设备详情失败:', error);
            contentEl.innerHTML = `
                <div class="empty-state" style="color: #ff4444;">
                    获取设备详情失败<br>
                    <span style="font-size: 11px;">${error.message}</span>
                </div>
            `;
        }
    },

    _renderDeviceDetail(device, trendData, historyData) {
        const contentEl = document.getElementById('deviceDetailContent');
        const deviceType = device.type;
        const deviceName = CONFIG.DEVICE_NAMES[deviceType] || deviceType;
        const cabinName = CONFIG.CABIN_NAMES[device.cabin] || device.cabin;
        const statusText = {
            normal: '正常',
            warning: '预警',
            fault: '故障',
            offline: '离线'
        }[device.status] || device.status;

        const deviceEmoji = {
            env_sensor: '🌡️',
            manhole: '⬛',
            fan: '🌀',
            pump: '💧'
        }[deviceType] || '📱';

        let dataGridHtml = '';
        const latestData = trendData.data && trendData.data.length > 0 
            ? trendData.data[trendData.data.length - 1] 
            : null;

        if (latestData) {
            if (deviceType === 'env_sensor') {
                dataGridHtml = `
                    <div class="device-data-grid">
                        <div class="data-item">
                            <div class="data-label">温度</div>
                            <div class="data-value ${latestData.temperature > 35 ? 'danger' : latestData.temperature > 32 ? 'warning' : ''}">${latestData.temperature}<span class="data-unit">℃</span></div>
                        </div>
                        <div class="data-item">
                            <div class="data-label">湿度</div>
                            <div class="data-value">${latestData.humidity}<span class="data-unit">%</span></div>
                        </div>
                        <div class="data-item">
                            <div class="data-label">氧气</div>
                            <div class="data-value ${latestData.oxygen < 18 ? 'danger' : latestData.oxygen < 19 ? 'warning' : ''}">${latestData.oxygen}<span class="data-unit">%</span></div>
                        </div>
                        <div class="data-item">
                            <div class="data-label">甲烷</div>
                            <div class="data-value ${latestData.methane >= 1 ? 'danger' : ''}">${latestData.methane}<span class="data-unit">%</span></div>
                        </div>
                        <div class="data-item">
                            <div class="data-label">硫化氢</div>
                            <div class="data-value ${latestData.hydrogen_sulfide >= 10 ? 'danger' : ''}">${latestData.hydrogen_sulfide}<span class="data-unit">ppm</span></div>
                        </div>
                        ${latestData.rssi !== undefined ? `
                        <div class="data-item">
                            <div class="data-label">信号</div>
                            <div class="data-value">${latestData.rssi}<span class="data-unit">dBm</span></div>
                        </div>` : ''}
                    </div>
                `;
            } else if (deviceType === 'manhole') {
                dataGridHtml = `
                    <div class="device-data-grid">
                        <div class="data-item">
                            <div class="data-label">井盖状态</div>
                            <div class="data-value ${latestData.is_open && !latestData.is_legal ? 'danger' : ''}">${latestData.is_open ? (latestData.is_legal ? '合法开启' : '非法开启!') : '关闭'}</div>
                        </div>
                        ${latestData.battery_level !== undefined ? `
                        <div class="data-item">
                            <div class="data-label">电池电量</div>
                            <div class="data-value ${latestData.battery_level < 20 ? 'warning' : ''}">${latestData.battery_level}<span class="data-unit">%</span></div>
                        </div>` : ''}
                    </div>
                `;
            } else if (deviceType === 'fan') {
                dataGridHtml = `
                    <div class="device-data-grid">
                        <div class="data-item">
                            <div class="data-label">运行状态</div>
                            <div class="data-value ${latestData.is_running ? '' : 'warning'}">${latestData.is_running ? '运行中' : '已停止'}</div>
                        </div>
                        <div class="data-item">
                            <div class="data-label">转速</div>
                            <div class="data-value">${latestData.speed || 0}<span class="data-unit">%</span></div>
                        </div>
                        ${latestData.current !== undefined ? `
                        <div class="data-item">
                            <div class="data-label">电流</div>
                            <div class="data-value ${latestData.current > 10 ? 'warning' : ''}">${latestData.current}<span class="data-unit">A</span></div>
                        </div>` : ''}
                        ${latestData.vibration !== undefined ? `
                        <div class="data-item">
                            <div class="data-label">振动</div>
                            <div class="data-value ${latestData.vibration > 4 ? 'warning' : ''}">${latestData.vibration}<span class="data-unit">mm/s</span></div>
                        </div>` : ''}
                    </div>
                `;
            } else if (deviceType === 'pump') {
                dataGridHtml = `
                    <div class="device-data-grid">
                        <div class="data-item">
                            <div class="data-label">运行状态</div>
                            <div class="data-value ${latestData.is_running ? '' : 'warning'}">${latestData.is_running ? '运行中' : '已停止'}</div>
                        </div>
                        <div class="data-item">
                            <div class="data-label">液位</div>
                            <div class="data-value ${latestData.level > 0.8 ? 'warning' : latestData.level > 1.0 ? 'danger' : ''}">${latestData.level}<span class="data-unit">m</span></div>
                        </div>
                        ${latestData.flow_rate !== undefined ? `
                        <div class="data-item">
                            <div class="data-label">流量</div>
                            <div class="data-value">${latestData.flow_rate}<span class="data-unit">m³/h</span></div>
                        </div>` : ''}
                        ${latestData.current !== undefined ? `
                        <div class="data-item">
                            <div class="data-label">电流</div>
                            <div class="data-value ${latestData.current > 10 ? 'warning' : ''}">${latestData.current}<span class="data-unit">A</span></div>
                        </div>` : ''}
                    </div>
                `;
            }
        }

        let controlButtonsHtml = '';
        if (deviceType === 'fan' || deviceType === 'pump') {
            controlButtonsHtml = `
                <div class="control-buttons">
                    <button class="control-btn start" onclick="App.controlDevice('${device.device_id}', 'start')">启动</button>
                    <button class="control-btn stop" onclick="App.controlDevice('${device.device_id}', 'stop')">停止</button>
                </div>
            `;
        }

        let historyHtml = '';
        if (historyData.history && historyData.history.length > 0) {
            historyHtml = `
                <div class="operation-history">
                    <h5>操作历史</h5>
                    <div class="history-list">
                        ${historyData.history.slice(0, 10).map(h => `
                            <div class="history-item">
                                <div>
                                    <span class="history-operation">${h.operation}</span>
                                    <span class="history-operator">by ${h.operator}</span>
                                </div>
                                <div class="history-time">${new Date(h.timestamp).toLocaleString('zh-CN')}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        contentEl.innerHTML = `
            <div class="device-detail-header">
                <div class="device-icon ${deviceType}">${deviceEmoji}</div>
                <div class="device-info">
                    <h4>${device.name}</h4>
                    <div class="device-id">${device.device_id}</div>
                    <span class="device-status-badge ${device.status}">${statusText}</span>
                </div>
            </div>

            <div style="font-size: 12px; color: #6b7a90; margin-bottom: 12px;">
                ${deviceName} · ${cabinName}
                ${device.last_update ? `<br>最后更新: ${new Date(device.last_update).toLocaleString('zh-CN')}` : ''}
            </div>

            ${dataGridHtml}

            ${trendData.data && trendData.data.length > 0 ? `
            <div class="chart-container">
                <h5>近24小时趋势</h5>
                <canvas id="trendChart" class="trend-chart"></canvas>
            </div>` : ''}

            ${historyHtml}

            ${controlButtonsHtml}

            ${device.description ? `<div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid rgba(0,212,255,0.2); font-size: 11px; color: #6b7a90;">${device.description}</div>` : ''}
        `;

        if (trendData.data && trendData.data.length > 0) {
            setTimeout(() => {
                ChartModule.createTrendChart('trendChart', trendData.data, deviceType);
            }, 50);
        }
    },

    async controlDevice(deviceId, command) {
        if (!confirm(`确定要${command === 'start' ? '启动' : '停止'}设备 ${deviceId} 吗？`)) return;

        try {
            await API.controlDevice(deviceId, command, 'admin');
            alert('命令已发送');
            this.showDeviceDetail(deviceId);
        } catch (error) {
            console.error('设备控制失败:', error);
            alert('设备控制失败: ' + error.message);
        }
    }
};

function closeDeviceOverlay() {
    document.getElementById('deviceInfoOverlay').classList.remove('active');
}

function closeAlarmModal() {
    App.closeAlarmModal();
}

function acknowledgeModalAlarm() {
    App.acknowledgeModalAlarm();
}

function acknowledgeAllAlarms() {
    App.acknowledgeAllAlarms();
}

document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
