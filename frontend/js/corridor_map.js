class CorridorMap {
    constructor() {
        this.map = null;
        this.tunnelLayer = null;
        this.deviceLayers = {};
        this.deviceMarkers = {};
        this.currentFilter = {
            type: 'all',
            chamber: 'all'
        };
        this.deviceIcons = {
            env_sensor: '📡',
            manhole: '⭕',
            pump: '💧',
            fan: '🌀'
        };
        this.onDeviceClick = null;
        this.canvasLayer = null;
    }

    init(mapContainerId = 'map') {
        this.map = L.map(mapContainerId, {
            center: [39.92, 116.45],
            zoom: 12,
            zoomControl: true,
            attributionControl: true
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19
        }).addTo(this.map);

        this._createCanvasOverlay();
        this.loadTunnelRoute();
        this.loadDevices();
    }

    _createCanvasOverlay() {
        this.canvasLayer = L.canvasOverlay({
            drawing: this._drawOnCanvas.bind(this)
        });
        this.canvasLayer.addTo(this.map);
    }

    _drawOnCanvas(options) {
        const canvas = options.canvas;
        const ctx = canvas.getContext('2d');
        const map = options.map;
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        if (this.tunnelLayer && this.tunnelLayer.geometry) {
            const coords = this.tunnelLayer.geometry.coordinates;
            if (coords && coords.length > 1) {
                ctx.beginPath();
                ctx.lineWidth = 8;
                ctx.strokeStyle = 'rgba(233, 69, 96, 0.8)';
                ctx.lineCap = 'round';
                ctx.lineJoin = 'round';
                
                for (let i = 0; i < coords.length; i++) {
                    const point = map.latLngToContainerPoint([coords[i][1], coords[i][0]]);
                    if (i === 0) {
                        ctx.moveTo(point.x, point.y);
                    } else {
                        ctx.lineTo(point.x, point.y);
                    }
                }
                ctx.stroke();
                
                ctx.beginPath();
                ctx.lineWidth = 4;
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
                ctx.setLineDash([10, 10]);
                
                for (let i = 0; i < coords.length; i++) {
                    const point = map.latLngToContainerPoint([coords[i][1], coords[i][0]]);
                    if (i === 0) {
                        ctx.moveTo(point.x, point.y);
                    } else {
                        ctx.lineTo(point.x, point.y);
                    }
                }
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }
    }

    async loadTunnelRoute() {
        try {
            const response = await fetch('/api/devices/tunnel-route');
            if (response.ok) {
                this.tunnelLayer = await response.json();
                this._drawTunnelLine();
                if (this.tunnelLayer.geometry && this.tunnelLayer.geometry.coordinates.length > 0) {
                    const coords = this.tunnelLayer.geometry.coordinates;
                    const bounds = L.latLngBounds(
                        coords.map(c => [c[1], c[0]])
                    );
                    this.map.fitBounds(bounds, { padding: [50, 50] });
                }
            }
        } catch (e) {
            console.error('Failed to load tunnel route:', e);
        }
    }

    _drawTunnelLine() {
        if (this.tunnelLayer && this.tunnelLayer.geometry) {
            const coords = this.tunnelLayer.geometry.coordinates;
            const latlngs = coords.map(c => [c[1], c[0]]);
            
            L.polyline(latlngs, {
                color: '#e94560',
                weight: 8,
                opacity: 0.8,
                lineCap: 'round',
                lineJoin: 'round',
                dashArray: null
            }).addTo(this.map);
            
            L.polyline(latlngs, {
                color: '#ffffff',
                weight: 3,
                opacity: 0.9,
                dashArray: '15, 10',
                lineCap: 'round',
                lineJoin: 'round'
            }).addTo(this.map);
        }
    }

    async loadDevices() {
        try {
            const response = await fetch('/api/devices/geojson');
            if (response.ok) {
                const geojson = await response.json();
                this._createDeviceMarkers(geojson.features);
                this._updateFilteredMarkers();
            }
        } catch (e) {
            console.error('Failed to load devices:', e);
        }
    }

    _createDeviceMarkers(features) {
        features.forEach(feature => {
            const deviceId = feature.id;
            const props = feature.properties;
            const coords = feature.geometry.coordinates;
            
            const icon = this._createDeviceIcon(props);
            const marker = L.marker([coords[1], coords[0]], { icon });
            
            marker.bindPopup(this._createPopupContent(props));
            
            marker.on('click', () => {
                if (this.onDeviceClick) {
                    this.onDeviceClick(deviceId, props);
                }
            });
            
            this.deviceMarkers[deviceId] = {
                marker,
                feature,
                properties: props
            };
        });
    }

    _createDeviceIcon(props) {
        const status = props.status || 'normal';
        const type = props.type;
        const running = props.running;
        
        const classes = [`device-marker`, type, status];
        if (running) {
            classes.push('running');
        }
        
        const iconHtml = `<div class="${classes.join(' ')}"></div>`;
        
        return L.divIcon({
            className: 'custom-device-icon',
            html: iconHtml,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
            popupAnchor: [0, -14]
        });
    }

    _createPopupContent(props) {
        const statusText = {
            'normal': '正常',
            'warning': '预警',
            'fault': '故障'
        };
        
        let content = `<div class="device-popup">`;
        content += `<h4>${props.name}</h4>`;
        content += `<span class="popup-status ${props.status}">${statusText[props.status] || props.status}</span>`;
        
        content += `<div class="popup-row"><strong>类型:</strong> ${props.type}</div>`;
        content += `<div class="popup-row"><strong>舱室:</strong> ${props.chamber}</div>`;
        content += `<div class="popup-row"><strong>里程:</strong> ${props.distance_km} km</div>`;
        
        if (props.temperature !== undefined) {
            content += `<div class="popup-row"><strong>温度:</strong> ${props.temperature}°C</div>`;
        }
        if (props.humidity !== undefined) {
            content += `<div class="popup-row"><strong>湿度:</strong> ${props.humidity}%</div>`;
        }
        if (props.oxygen !== undefined) {
            content += `<div class="popup-row"><strong>氧气:</strong> ${props.oxygen}%</div>`;
        }
        if (props.methane !== undefined) {
            content += `<div class="popup-row"><strong>甲烷:</strong> ${props.methane}%</div>`;
        }
        if (props.h2s !== undefined) {
            content += `<div class="popup-row"><strong>硫化氢:</strong> ${props.h2s} ppm</div>`;
        }
        if (props.running !== undefined) {
            content += `<div class="popup-row"><strong>状态:</strong> ${props.running ? '运行中' : '已停止'}</div>`;
        }
        if (props.speed !== undefined) {
            content += `<div class="popup-row"><strong>转速:</strong> ${props.speed}%</div>`;
        }
        if (props.level !== undefined) {
            content += `<div class="popup-row"><strong>液位:</strong> ${props.level}%</div>`;
        }
        if (props.cover_open !== undefined) {
            content += `<div class="popup-row"><strong>井盖:</strong> ${props.cover_open ? '已开启' : '已关闭'}</div>`;
        }
        
        content += `<button class="view-detail-btn" onclick="event.stopPropagation(); window.CorridorMap.handleDeviceClick('${props.device_id}')">查看详情</button>`;
        content += `</div>`;
        
        return content;
    }

    setFilter(type, chamber) {
        if (type) this.currentFilter.type = type;
        if (chamber) this.currentFilter.chamber = chamber;
        this._updateFilteredMarkers();
    }

    _updateFilteredMarkers() {
        Object.values(this.deviceMarkers).forEach(({ marker, properties }) => {
            const typeMatch = this.currentFilter.type === 'all' || properties.type === this.currentFilter.type;
            const chamberMatch = this.currentFilter.chamber === 'all' || properties.chamber === this.currentFilter.chamber;
            
            if (typeMatch && chamberMatch) {
                if (!this.map.hasLayer(marker)) {
                    marker.addTo(this.map);
                }
            } else {
                if (this.map.hasLayer(marker)) {
                    this.map.removeLayer(marker);
                }
            }
        });
    }

    updateDeviceStatus(deviceId, newProperties) {
        const device = this.deviceMarkers[deviceId];
        if (device) {
            Object.assign(device.properties, newProperties);
            
            const newIcon = this._createDeviceIcon(device.properties);
            device.marker.setIcon(newIcon);
            
            device.marker.setPopupContent(this._createPopupContent(device.properties));
        }
    }

    refresh() {
        this.loadDevices();
    }

    setOnDeviceClick(callback) {
        this.onDeviceClick = callback;
    }

    getDevice(deviceId) {
        return this.deviceMarkers[deviceId];
    }

    getAllDevices() {
        return Object.values(this.deviceMarkers);
    }

    fitToTunnel() {
        if (this.tunnelLayer && this.tunnelLayer.geometry) {
            const coords = this.tunnelLayer.geometry.coordinates;
            const bounds = L.latLngBounds(
                coords.map(c => [c[1], c[0]])
            );
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }
}

L.CanvasOverlay = L.Layer.extend({
    initialize: function (options) {
        L.setOptions(this, options);
    },

    onAdd: function (map) {
        this._map = map;
        
        const canvas = L.DomUtil.create('canvas', 'leaflet-canvas-overlay');
        const size = map.getSize();
        
        canvas.width = size.x;
        canvas.height = size.y;
        canvas.style.position = 'absolute';
        canvas.style.top = 0;
        canvas.style.left = 0;
        canvas.style.pointerEvents = 'none';
        
        this._canvas = canvas;
        map.getPanes().overlayPane.appendChild(canvas);
        
        map.on('move', this._reset, this);
        map.on('resize', this._resize, this);
        map.on('zoomend', this._reset, this);
        
        this._reset();
    },

    onRemove: function (map) {
        L.DomUtil.remove(this._canvas);
        map.off('move', this._reset, this);
        map.off('resize', this._resize, this);
        map.off('zoomend', this._reset, this);
    },

    _reset: function () {
        const topLeft = this._map.containerPointToLayerPoint([0, 0]);
        L.DomUtil.setPosition(this._canvas, topLeft);
        
        const size = this._map.getSize();
        this._canvas.width = size.x;
        this._canvas.height = size.y;
        
        this._draw();
    },

    _resize: function (e) {
        this._canvas.width = e.newSize.x;
        this._canvas.height = e.newSize.y;
        this._draw();
    },

    _draw: function () {
        if (this.options.drawing) {
            this.options.drawing({
                canvas: this._canvas,
                map: this._map,
                bounds: this._map.getBounds(),
                size: this._map.getSize(),
                zoom: this._map.getZoom()
            });
        }
    }
});

L.canvasOverlay = function (options) {
    return new L.CanvasOverlay(options);
};

window.CorridorMap = CorridorMap;
window.CorridorMap.handleDeviceClick = function(deviceId) {
    if (window.DeviceDetail && window.DeviceDetail.show) {
        window.DeviceDetail.show(deviceId);
    } else if (window.App && window.App.showDeviceDetail) {
        window.App.showDeviceDetail(deviceId);
    }
};
