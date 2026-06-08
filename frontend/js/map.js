console.log('map.js loaded - using CorridorMap component');

if (typeof CorridorMap === 'undefined') {
    console.error('CorridorMap not loaded! Make sure corridor_map.js is included before map.js');
}

class TunnelMap {
    constructor() {
        this._corridorMap = window.CorridorMap ? new window.CorridorMap() : null;
        
        if (!this._corridorMap) {
            console.warn('CorridorMap not available, using fallback');
            this._fallbackInit();
            return;
        }
        
        this._corridorMap.setOnDeviceClick((deviceId, props) => {
            if (this.onDeviceClick) {
                this.onDeviceClick(deviceId, props);
            }
            if (window.App && window.App.showDeviceDetail) {
                window.App.showDeviceDetail(deviceId);
            }
        });
    }
    
    get map() {
        return this._corridorMap ? this._corridorMap.map : this._map;
    }
    
    set map(val) {
        if (this._corridorMap) {
            this._corridorMap.map = val;
        } else {
            this._map = val;
        }
    }
    
    get tunnelLayer() {
        return this._corridorMap ? this._corridorMap.tunnelLayer : this._tunnelLayer;
    }
    
    get deviceMarkers() {
        return this._corridorMap ? this._corridorMap.deviceMarkers : this._deviceMarkers;
    }
    
    get currentFilter() {
        return this._corridorMap ? this._corridorMap.currentFilter : this._currentFilter;
    }
    
    init() {
        if (this._corridorMap) {
            this._corridorMap.init('map');
        } else {
            this._fallbackInit();
        }
    }
    
    setFilter(type, chamber) {
        if (this._corridorMap) {
            this._corridorMap.setFilter(type, chamber);
        }
    }
    
    updateDeviceStatus(deviceId, newProperties) {
        if (this._corridorMap) {
            this._corridorMap.updateDeviceStatus(deviceId, newProperties);
        }
    }
    
    refresh() {
        if (this._corridorMap) {
            this._corridorMap.refresh();
        }
    }
    
    async loadTunnelRoute() {
        if (this._corridorMap) {
            await this._corridorMap.loadTunnelRoute();
        }
    }
    
    async loadDevices() {
        if (this._corridorMap) {
            await this._corridorMap.loadDevices();
        }
    }
    
    _fallbackInit() {
        console.warn('Fallback initialization - limited functionality');
        this._deviceMarkers = {};
        this._tunnelLayer = null;
        this._currentFilter = { type: 'all', chamber: 'all' };
    }
}

window.TunnelMap = TunnelMap;
