const DeviceDetailModule = {
    currentDeviceId: null,

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
                    <button class="control-btn start" onclick="DeviceDetailModule.controlDevice('${device.device_id}', 'start')">启动</button>
                    <button class="control-btn stop" onclick="DeviceDetailModule.controlDevice('${device.device_id}', 'stop')">停止</button>
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
