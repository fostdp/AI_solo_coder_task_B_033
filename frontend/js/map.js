const MapModule = {
    map: null,
    corridorLayer: null,
    deviceLayers: {},
    deviceMarkers: {},
    currentFilters: {
        env_sensor: true,
        manhole: true,
        fan: true,
        pump: true
    },

    init() {
        this.map = L.map('map', {
            center: CONFIG.MAP_CENTER,
            zoom: CONFIG.MAP_ZOOM,
            zoomControl: false,
            attributionControl: false
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(this.map);

        this.corridorLayer = L.layerGroup().addTo(this.map);
        this.deviceLayers = {
            env_sensor: L.layerGroup().addTo(this.map),
            manhole: L.layerGroup().addTo(this.map),
            fan: L.layerGroup().addTo(this.map),
            pump: L.layerGroup().addTo(this.map)
        };

        this._bindControls();
        this.loadCorridor();
        this.loadDevices();
    },

    _bindControls() {
        document.getElementById('btnZoomIn').addEventListener('click', () => {
            this.map.zoomIn();
        });

        document.getElementById('btnZoomOut').addEventListener('click', () => {
            this.map.zoomOut();
        });

        document.getElementById('btnFitView').addEventListener('click', () => {
            this.fitView();
        });

        document.getElementById('filterEnv').addEventListener('change', (e) => {
            this.toggleLayer('env_sensor', e.target.checked);
        });

        document.getElementById('filterManhole').addEventListener('change', (e) => {
            this.toggleLayer('manhole', e.target.checked);
        });

        document.getElementById('filterFan').addEventListener('change', (e) => {
            this.toggleLayer('fan', e.target.checked);
        });

        document.getElementById('filterPump').addEventListener('change', (e) => {
            this.toggleLayer('pump', e.target.checked);
        });
    },

    async loadCorridor() {
        try {
            const data = await API.getCorridorGeoJSON();
            if (data && data.features) {
                data.features.forEach(feature => {
                    if (feature.geometry.type === 'LineString') {
                        const cabin = feature.properties.cabin;
                        const color = CONFIG.CABIN_COLORS[cabin] || '#00d4ff';

                        L.polyline(feature.geometry.coordinates.map(c => [c[1], c[0]]), {
                            color: color,
                            weight: 4,
                            opacity: 0.8,
                            dashArray: feature.properties.type === 'main_corridor' ? null : '10, 10'
                        }).addTo(this.corridorLayer);
                    } else if (feature.geometry.type === 'Point') {
                        const cabin = feature.properties.cabin;
                        const color = CONFIG.CABIN_COLORS[cabin] || '#00d4ff';

                        L.circleMarker([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], {
                            radius: 6,
                            fillColor: color,
                            color: '#fff',
                            weight: 2,
                            opacity: 1,
                            fillOpacity: 0.8
                        }).addTo(this.corridorLayer)
                        .bindPopup(`<div class="popup-title">${feature.properties.name}</div>`);
                    }
                });
            }
        } catch (error) {
            console.error('加载管廊数据失败:', error);
        }
    },

    async loadDevices() {
        try {
            const geojson = await API.getDevicesGeoJSON();
            this._addDeviceMarkers(geojson);
        } catch (error) {
            console.error('加载设备数据失败:', error);
        }
    },

    _addDeviceMarkers(geojson) {
        Object.values(this.deviceLayers).forEach(layer => layer.clearLayers());
        this.deviceMarkers = {};

        geojson.features.forEach(feature => {
            const props = feature.properties;
            const deviceType = props.type;
            const status = props.status || 'normal';
            const icon = CONFIG.DEVICE_ICONS[deviceType]?.[status] || CONFIG.DEVICE_ICONS.env_sensor.normal;

            const marker = L.marker(
                [feature.geometry.coordinates[1], feature.geometry.coordinates[0]],
                { icon }
            );

            marker.on('click', () => {
                this._onDeviceClick(props.device_id);
            });

            marker.bindPopup(this._createPopupContent(props));

            marker.addTo(this.deviceLayers[deviceType]);
            this.deviceMarkers[props.device_id] = marker;
        });
    },

    _createPopupContent(props) {
        const statusText = {
            normal: '正常',
            warning: '预警',
            fault: '故障',
            offline: '离线'
        }[props.status] || props.status;

        const statusColor = {
            normal: '#00ff88',
            warning: '#ffaa00',
            fault: '#ff4444',
            offline: '#6b7a90'
        }[props.status] || '#00d4ff';

        return `
            <div class="popup-title">${props.name}</div>
            <div class="popup-data">
                <div><span class="label">设备ID:</span> <span class="value">${props.device_id}</span></div>
                <div><span class="label">类型:</span> <span class="value">${CONFIG.DEVICE_NAMES[props.type] || props.type}</span></div>
                <div><span class="label">舱室:</span> <span class="value">${CONFIG.CABIN_NAMES[props.cabin] || props.cabin}</span></div>
                <div><span class="label">状态:</span> <span class="value" style="color: ${statusColor}">${statusText}</span></div>
                ${props.description ? `<div><span class="label">说明:</span> <span class="value">${props.description}</span></div>` : ''}
            </div>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,212,255,0.2); font-size: 11px; color: #00d4ff;">
                点击查看详细信息 →
            </div>
        `;
    },

    async _onDeviceClick(deviceId) {
        App.showDeviceDetail(deviceId);
    },

    updateDeviceStatus(deviceId, status, data = null) {
        const marker = this.deviceMarkers[deviceId];
        if (!marker) return;

        const deviceType = Object.keys(this.deviceMarkers).find(id => id === deviceId) ?
            (Object.values(this.deviceMarkers).find(m => m === marker)?.options?.type) : 'env_sensor';

        const markerData = marker.feature?.properties || {};
        const actualType = markerData.type || 'env_sensor';

        const icon = CONFIG.DEVICE_ICONS[actualType]?.[status] || CONFIG.DEVICE_ICONS.env_sensor.normal;
        marker.setIcon(icon);

        marker.setPopupContent(this._createPopupContent({
            ...markerData,
            device_id: deviceId,
            status: status
        }));

        if (data) {
            this._showQuickInfo(deviceId, data);
        }
    },

    _showQuickInfo(deviceId, data) {
        const overlay = document.getElementById('deviceInfoOverlay');
        const content = document.getElementById('overlayContent');

        let html = `<div style="display: flex; gap: 20px; flex-wrap: wrap;">`;
        html += `<div><strong>设备ID:</strong> ${deviceId}</div>`;

        if (data.temperature !== undefined) {
            html += `<div>🌡️ 温度: <b style="color: ${data.temperature > 35 ? '#ff4444' : '#00ff88'}">${data.temperature}℃</b></div>`;
        }
        if (data.humidity !== undefined) {
            html += `<div>💧 湿度: <b>${data.humidity}%</b></div>`;
        }
        if (data.oxygen !== undefined) {
            const o2Color = data.oxygen < 18 ? '#ff4444' : data.oxygen < 19 ? '#ffaa00' : '#00ff88';
            html += `<div>🫧 氧气: <b style="color: ${o2Color}">${data.oxygen}%</b></div>`;
        }
        if (data.methane !== undefined) {
            const ch4Color = data.methane >= 1 ? '#ff4444' : '#00ff88';
            html += `<div>🔥 甲烷: <b style="color: ${ch4Color}">${data.methane}%</b></div>`;
        }
        if (data.hydrogen_sulfide !== undefined) {
            const h2sColor = data.hydrogen_sulfide >= 10 ? '#ff4444' : '#00ff88';
            html += `<div>⚠️ 硫化氢: <b style="color: ${h2sColor}">${data.hydrogen_sulfide}ppm</b></div>`;
        }
        if (data.is_open !== undefined) {
            html += `<div>🚪 井盖: <b style="color: ${data.is_open && !data.is_legal ? '#ff4444' : '#00ff88'}">${data.is_open ? (data.is_legal ? '合法开启' : '非法开启!') : '关闭'}</b></div>`;
        }

        html += `</div>`;
        content.innerHTML = html;
        overlay.classList.add('active');

        clearTimeout(this._overlayTimeout);
        this._overlayTimeout = setTimeout(() => {
            overlay.classList.remove('active');
        }, 5000);
    },

    toggleLayer(layerName, visible) {
        this.currentFilters[layerName] = visible;
        if (visible) {
            this.map.addLayer(this.deviceLayers[layerName]);
        } else {
            this.map.removeLayer(this.deviceLayers[layerName]);
        }
    },

    fitView() {
        const allMarkers = Object.values(this.deviceMarkers);
        if (allMarkers.length > 0) {
            const group = L.featureGroup(allMarkers);
            this.map.fitBounds(group.getBounds().pad(0.1));
        }
    },

    refresh() {
        this.loadDevices();
    }
};
