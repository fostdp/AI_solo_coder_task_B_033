const WebSocketModule = {
    ws: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 10,
    reconnectInterval: 3000,
    isConnected: false,

    init() {
        this.connect();
    },

    connect() {
        try {
            this.ws = new WebSocket(CONFIG.WS_URL);

            this.ws.onopen = () => {
                console.log('[WebSocket] 连接成功');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this._updateConnectionStatus(true);

                this.heartbeat();
            };

            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this._handleMessage(message);
                } catch (error) {
                    console.error('[WebSocket] 消息解析错误:', error);
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WebSocket] 连接错误:', error);
                this._updateConnectionStatus(false);
            };

            this.ws.onclose = () => {
                console.log('[WebSocket] 连接关闭');
                this.isConnected = false;
                this._updateConnectionStatus(false);
                this._reconnect();
            };
        } catch (error) {
            console.error('[WebSocket] 初始化失败:', error);
            this._reconnect();
        }
    },

    _reconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WebSocket] 达到最大重连次数');
            return;
        }

        this.reconnectAttempts++;
        console.log(`[WebSocket] 尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

        setTimeout(() => {
            this.connect();
        }, this.reconnectInterval);
    },

    heartbeat() {
        if (!this.isConnected) return;

        try {
            this.ws.send(JSON.stringify({ type: 'ping' }));
        } catch (error) {
            console.error('[WebSocket] 心跳发送失败:', error);
        }

        setTimeout(() => {
            this.heartbeat();
        }, 30000);
    },

    _handleMessage(message) {
        switch (message.type) {
            case 'pong':
                break;

            case 'alarm':
                this._handleAlarm(message.data);
                break;

            case 'device_update':
                this._handleDeviceUpdate(message.data);
                break;

            default:
                console.log('[WebSocket] 未知消息类型:', message);
        }
    },

    _handleAlarm(alarmData) {
        console.log('[WebSocket] 收到告警:', alarmData);

        App.addAlarm(alarmData);
        App.showAlarmModal(alarmData);
        App.refreshHealthScore();

        if (alarmData.level === 'critical') {
            this._playAlarmSound();
        }
    },

    _handleDeviceUpdate(deviceData) {
        console.log('[WebSocket] 收到设备更新:', deviceData);

        MapModule.updateDeviceStatus(
            deviceData.device_id,
            deviceData.status,
            deviceData.data
        );

        App.refreshHealthScore();
    },

    _playAlarmSound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);

            oscillator.frequency.value = 800;
            oscillator.type = 'square';
            gainNode.gain.value = 0.3;

            oscillator.start();
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
            oscillator.stop(audioContext.currentTime + 0.5);

            setTimeout(() => {
                const osc2 = audioContext.createOscillator();
                osc2.connect(gainNode);
                osc2.frequency.value = 1000;
                osc2.type = 'square';
                gainNode.gain.value = 0.3;
                osc2.start();
                gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
                osc2.stop(audioContext.currentTime + 0.5);
            }, 600);
        } catch (error) {
            console.error('播放告警声音失败:', error);
        }
    },

    _updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connectionStatus');
        const textEl = statusEl.querySelector('.status-text');

        if (connected) {
            statusEl.classList.remove('disconnected');
            statusEl.classList.add('connected');
            textEl.textContent = '已连接';
        } else {
            statusEl.classList.remove('connected');
            statusEl.classList.add('disconnected');
            textEl.textContent = '连接断开';
        }
    },

    send(data) {
        if (this.isConnected && this.ws) {
            this.ws.send(JSON.stringify(data));
            return true;
        }
        return false;
    },

    close() {
        if (this.ws) {
            this.ws.close();
        }
    }
};
