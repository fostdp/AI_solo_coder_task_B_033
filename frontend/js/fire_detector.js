class FireDetector {
    constructor() {
        this.fireAlerts = [];
        this.zoneStatus = [];
        this.fireZoneLayer = null;
        this.activeOverlay = false;
    }

    async fetchFireAlerts(limit = 20) {
        try {
            const response = await fetch(`/api/fire/alerts?limit=${limit}`);
            if (response.ok) {
                const data = await response.json();
                this.fireAlerts = data.alerts || [];
                this.updateFireAlertCount();
            }
        } catch (error) {
            console.error('Failed to fetch fire alerts:', error);
        }
    }

    async fetchZoneStatus() {
        try {
            const response = await fetch('/api/fire/zones');
            if (response.ok) {
                const data = await response.json();
                this.zoneStatus = data.zones || [];
                this.updateZoneStats();
                if (this.activeOverlay) {
                    this.updateFireZoneLayer();
                }
            }
        } catch (error) {
            console.error('Failed to fetch zone status:', error);
        }
    }

    updateFireAlertCount() {
        const activeCount = this.fireAlerts.filter(a => 
            !a.acknowledged && 
            (a.risk_level === 'critical' || a.risk_level === 'warning')
        ).length;
        
        const elem = document.getElementById('fire-alert-count');
        if (elem) {
            elem.textContent = activeCount;
        }
        
        const stat = document.getElementById('fire-alert-stat');
        if (stat) {
            stat.classList.toggle('has-alert', activeCount > 0);
        }
        
        const faultElem = document.getElementById('fault-fire');
        if (faultElem) {
            faultElem.textContent = this.fireAlerts.filter(a => 
                a.risk_level === 'critical' || a.risk_level === 'warning'
            ).length;
        }
    }

    updateZoneStats() {
        const closedCount = this.zoneStatus.filter(z => z.status === 'closed').length;
        const totalCount = this.zoneStatus.length;
        
        const elem = document.getElementById('closed-fire-zones');
        if (elem) {
            elem.textContent = `${closedCount} / ${totalCount || 16}`;
        }
    }

    toggleFireZones(show) {
        this.activeOverlay = show;
        if (show) {
            this.fetchZoneStatus().then(() => {
                this.updateFireZoneLayer();
            });
        } else {
            this.removeFireZoneLayer();
        }
    }

    updateFireZoneLayer() {
        if (!window.map) return;
        
        this.removeFireZoneLayer();
        
        const zoneMarkers = [];
        this.zoneStatus.forEach(zone => {
            if (zone.location && zone.location.coordinates) {
                const isClosed = zone.status === 'closed';
                const color = isClosed ? '#ef4444' : '#22c55e';
                
                const marker = L.circleMarker(
                    [zone.location.coordinates[1], zone.location.coordinates[0]],
                    {
                        radius: 10,
                        fillColor: color,
                        color: isClosed ? '#b91c1c' : '#15803d',
                        weight: 3,
                        opacity: 0.9,
                        fillOpacity: 0.8
                    }
                ).bindPopup(`
                    <strong>防火分区: ${zone.zone_id}</strong><br/>
                    舱室: ${zone.chamber}<br/>
                    位置: ${zone.distance_km.toFixed(2)} km<br/>
                    状态: <span style="color: ${color}; font-weight: bold;">
                        ${isClosed ? '已关闭' : '正常开放'}
                    </span><br/>
                    防火门: ${zone.fire_doors_closed || 0} / ${zone.fire_doors_total || 0}<br/>
                    灭火装置: ${zone.extinguishers_ready || 0} / ${zone.extinguishers_total || 0}
                    ${zone.last_activation ? `<br/>最后动作: ${new Date(zone.last_activation).toLocaleString()}` : ''}
                `);
                
                zoneMarkers.push(marker);
            }
        });
        
        if (zoneMarkers.length > 0) {
            this.fireZoneLayer = L.layerGroup(zoneMarkers).addTo(window.map);
        }
    }

    removeFireZoneLayer() {
        if (this.fireZoneLayer && window.map) {
            window.map.removeLayer(this.fireZoneLayer);
            this.fireZoneLayer = null;
        }
    }

    async calculateFireProbability(deviceId) {
        try {
            const response = await fetch(
                `/api/fire/probability?device_id=${deviceId}`
            );
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.error('Failed to calculate fire probability:', error);
        }
        return null;
    }

    getFireRiskColor(riskLevel) {
        const colors = {
            'normal': '#22c55e',
            'monitoring': '#eab308',
            'warning': '#f97316',
            'critical': '#ef4444'
        };
        return colors[riskLevel] || '#22c55e';
    }

    getFireRiskText(riskLevel) {
        const texts = {
            'normal': '正常',
            'monitoring': '监控中',
            'warning': '预警',
            'critical': '严重'
        };
        return texts[riskLevel] || riskLevel;
    }

    async acknowledgeFireAlert(alertId) {
        try {
            const response = await fetch(`/api/fire/alerts/${alertId}/acknowledge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (response.ok) {
                this.fetchFireAlerts();
                return true;
            }
        } catch (error) {
            console.error('Failed to acknowledge fire alert:', error);
        }
        return false;
    }

    async activateFireResponse(zoneId) {
        if (confirm(`确认要启动 ${zoneId} 分区的火灾响应吗？\n这将关闭防火门并启动灭火装置。`)) {
            try {
                const response = await fetch('/api/fire/response/activate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ zone_id: zoneId })
                });
                if (response.ok) {
                    alert('火灾响应已启动');
                    this.fetchZoneStatus();
                    return true;
                }
            } catch (error) {
                console.error('Failed to activate fire response:', error);
                alert('启动失败');
            }
        }
        return false;
    }

    async resetZone(zoneId) {
        if (confirm(`确认要重置 ${zoneId} 分区吗？\n这将打开防火门并重置灭火装置。`)) {
            try {
                const response = await fetch('/api/fire/zones/reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ zone_id: zoneId })
                });
                if (response.ok) {
                    alert('分区已重置');
                    this.fetchZoneStatus();
                    return true;
                }
            } catch (error) {
                console.error('Failed to reset zone:', error);
                alert('重置失败');
            }
        }
        return false;
    }

    getFireAlertCard(alert) {
        const color = this.getFireRiskColor(alert.risk_level);
        const time = new Date(alert.timestamp).toLocaleString();
        
        return `
            <div class="alert-card fire-alert ${alert.risk_level} ${alert.acknowledged ? 'acknowledged' : ''}">
                <div class="alert-header">
                    <span class="alert-icon">🔥</span>
                    <span class="alert-level" style="color: ${color};">
                        ${this.getFireRiskText(alert.risk_level).toUpperCase()}
                    </span>
                    <span class="alert-time">${time}</span>
                </div>
                <div class="alert-body">
                    <div><strong>传感器:</strong> ${alert.device_id}</div>
                    <div><strong>舱室:</strong> ${alert.chamber}</div>
                    <div><strong>位置:</strong> ${alert.distance_km?.toFixed(2) || '--'} km</div>
                    ${alert.fire_probability !== undefined ? 
                        `<div><strong>火灾概率:</strong> ${(alert.fire_probability * 100).toFixed(1)}%</div>` : ''}
                    ${alert.temperature !== undefined ? 
                        `<div><strong>温度:</strong> ${alert.temperature.toFixed(1)}°C</div>` : ''}
                    ${alert.temperature_rate !== undefined ? 
                        `<div><strong>温度变化率:</strong> ${alert.temperature_rate.toFixed(2)}°C/min</div>` : ''}
                    ${alert.smoke_density !== undefined ? 
                        `<div><strong>烟雾浓度:</strong> ${alert.smoke_density.toFixed(1)}%</div>` : ''}
                    ${alert.is_equipment_overheat !== undefined ? 
                        `<div><strong>类型:</strong> ${alert.is_equipment_overheat ? '设备过热' : '火灾征兆'}</div>` : ''}
                </div>
                <div class="alert-actions">
                    ${!alert.acknowledged ? `
                        <button class="alert-btn acknowledge" 
                            onclick="fireDetector.acknowledgeFireAlert('${alert.alert_id}')">
                            确认告警
                        </button>
                    ` : '<span class="acknowledged-badge">✓ 已确认</span>'}
                    ${alert.zone_id ? `
                        <button class="alert-btn response" 
                            onclick="fireDetector.activateFireResponse('${alert.zone_id}')">
                            启动响应
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }
}

window.fireDetector = new FireDetector();
