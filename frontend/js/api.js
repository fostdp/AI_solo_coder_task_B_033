const API = {
    async get(endpoint) {
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`API GET ${endpoint} error:`, error);
            throw error;
        }
    },

    async post(endpoint, data) {
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`API POST ${endpoint} error:`, error);
            throw error;
        }
    },

    async getDevices(type = null, cabin = null, status = null) {
        const params = new URLSearchParams();
        if (type) params.append('type', type);
        if (cabin) params.append('cabin', cabin);
        if (status) params.append('status', status);
        const query = params.toString() ? `?${params.toString()}` : '';
        return await this.get(`/devices${query}`);
    },

    async getDevice(deviceId) {
        return await this.get(`/devices/${deviceId}`);
    },

    async getDeviceTrend(deviceId, hours = 24) {
        return await this.get(`/devices/${deviceId}/trend?hours=${hours}`);
    },

    async getDeviceHistory(deviceId, limit = 50) {
        return await this.get(`/devices/${deviceId}/history?limit=${limit}`);
    },

    async controlDevice(deviceId, command, operator = 'admin') {
        return await this.post(`/devices/${deviceId}/control`, { command, operator });
    },

    async getAlarms(level = null, acknowledged = null, limit = 100) {
        const params = new URLSearchParams();
        if (level) params.append('level', level);
        if (acknowledged !== null) params.append('acknowledged', acknowledged);
        if (limit) params.append('limit', limit);
        const query = params.toString() ? `?${params.toString()}` : '';
        return await this.get(`/alarms${query}`);
    },

    async acknowledgeAlarm(alarmId, user = 'admin') {
        return await this.post(`/alarms/${alarmId}/acknowledge`, { user });
    },

    async getHealthScore() {
        return await this.get('/health/score');
    },

    async getFaultStats() {
        return await this.get('/health/fault-stats');
    },

    async getDevicesGeoJSON() {
        return await this.get('/geojson/devices');
    },

    async getCorridorGeoJSON() {
        return await this.get('/geojson/corridor');
    }
};
