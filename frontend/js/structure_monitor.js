class StructureMonitor {
    constructor() {
        this.heatmapLayer = null;
        this.heatmapData = [];
        this.structureAlerts = [];
        this.activeOverlay = false;
    }

    async fetchHeatmapData() {
        try {
            const response = await fetch('/api/structure/heatmap');
            if (response.ok) {
                const data = await response.json();
                this.heatmapData = data.heatmap || [];
                if (this.activeOverlay) {
                    this.updateHeatmapLayer();
                }
            }
        } catch (error) {
            console.error('Failed to fetch structure heatmap:', error);
        }
    }

    async fetchStructureAlerts() {
        try {
            const response = await fetch('/api/structure/alerts?limit=20');
            if (response.ok) {
                const data = await response.json();
                this.structureAlerts = data.alerts || [];
                this.updateStructureAlertCount();
            }
        } catch (error) {
            console.error('Failed to fetch structure alerts:', error);
        }
    }

    updateStructureAlertCount() {
        const criticalCount = this.structureAlerts.filter(a => 
            a.risk_level === 'critical' || a.risk_level === 'warning'
        ).length;
        const elem = document.getElementById('structure-alert-count');
        if (elem) {
            elem.textContent = criticalCount;
        }
        const stat = document.getElementById('structure-alert-stat');
        if (stat) {
            stat.classList.toggle('has-alert', criticalCount > 0);
        }
    }

    toggleHeatmap(show) {
        this.activeOverlay = show;
        if (show) {
            this.fetchHeatmapData().then(() => {
                this.updateHeatmapLayer();
            });
        } else {
            this.removeHeatmapLayer();
        }
    }

    updateHeatmapLayer() {
        if (window.map && this.heatmapData.length > 0) {
            this.removeHeatmapLayer();
            
            const heatMapPoints = this.heatmapData.map(point => {
                const riskColor = this.getRiskColor(point.risk_level);
                return L.circleMarker([point.location.coordinates[1], point.location.coordinates[0]], {
                    radius: 12,
                    fillColor: riskColor,
                    color: riskColor,
                    weight: 2,
                    opacity: 0.8,
                    fillOpacity: 0.6
                }).bindPopup(`
                    <strong>光纤传感器: ${point.device_id}</strong><br/>
                    位置: ${point.distance_km.toFixed(2)} km<br/>
                    应变: ${point.strain.toFixed(1)} με<br/>
                    裂缝: ${point.crack_width.toFixed(4)} mm<br/>
                    风险等级: <span style="color: ${riskColor}; font-weight: bold;">${point.risk_level}</span>
                `);
            });
            
            this.heatmapLayer = L.layerGroup(heatMapPoints).addTo(window.map);
        }
    }

    removeHeatmapLayer() {
        if (this.heatmapLayer && window.map) {
            window.map.removeLayer(this.heatmapLayer);
            this.heatmapLayer = null;
        }
    }

    getRiskColor(riskLevel) {
        const colors = {
            'normal': '#22c55e',
            'attention': '#eab308',
            'warning': '#f97316',
            'critical': '#ef4444'
        };
        return colors[riskLevel] || '#22c55e';
    }

    async fetchStructureTrend(deviceId, hours = 24) {
        try {
            const response = await fetch(
                `/api/structure/trend?device_id=${deviceId}&hours=${hours}`
            );
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.error('Failed to fetch structure trend:', error);
        }
        return null;
    }
}

window.structureMonitor = new StructureMonitor();
