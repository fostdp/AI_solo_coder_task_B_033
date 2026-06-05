const App = {
    alarms: [],
    currentAlarmId: null,
    refreshTimers: {},

    init() {
        console.log('地下管廊综合监控系统启动...');

        CorridorMapModule.init((deviceId) => DeviceDetailModule.showDeviceDetail(deviceId));
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
            CorridorMapModule.refresh();
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
