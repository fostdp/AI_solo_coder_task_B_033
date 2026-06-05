const CONFIG = {
    API_BASE_URL: 'http://localhost:8000/api',
    WS_URL: 'ws://localhost:8000/api/ws',
    MAP_CENTER: [39.908, 116.397],
    MAP_ZOOM: 14,
    REFRESH_INTERVAL: 30000,
    HEALTH_REFRESH_INTERVAL: 60000,
    DEVICE_ICONS: {
        env_sensor: {
            normal: createColoredIcon('#00ff88', '🌡️'),
            warning: createColoredIcon('#ffaa00', '🌡️'),
            fault: createColoredIcon('#ff4444', '🌡️'),
            offline: createColoredIcon('#6b7a90', '🌡️')
        },
        manhole: {
            normal: createColoredIcon('#00ff88', '⬛'),
            warning: createColoredIcon('#ffaa00', '⬛'),
            fault: createColoredIcon('#ff4444', '⬛'),
            offline: createColoredIcon('#6b7a90', '⬛')
        },
        fan: {
            normal: createColoredIcon('#00ff88', '🌀'),
            warning: createColoredIcon('#ffaa00', '🌀'),
            fault: createColoredIcon('#ff4444', '🌀'),
            offline: createColoredIcon('#6b7a90', '🌀')
        },
        pump: {
            normal: createColoredIcon('#00ff88', '💧'),
            warning: createColoredIcon('#ffaa00', '💧'),
            fault: createColoredIcon('#ff4444', '💧'),
            offline: createColoredIcon('#6b7a90', '💧')
        }
    },
    CABIN_COLORS: {
        power: '#ff4444',
        water: '#00d4ff',
        gas: '#ffaa00'
    },
    CABIN_NAMES: {
        power: '电力舱',
        water: '水信舱',
        gas: '燃气舱'
    },
    DEVICE_NAMES: {
        env_sensor: '环境传感器',
        manhole: '井盖传感器',
        fan: '风机',
        pump: '排水泵'
    },
    ALARM_NAMES: {
        gas_level1: '一级气体告警',
        gas_level2: '二级气体告警',
        suffocation: '窒息告警',
        security: '安防告警',
        temperature: '温度告警',
        equipment: '设备告警'
    }
};

function createColoredIcon(color, emoji) {
    return L.divIcon({
        className: 'custom-marker',
        html: `<div style="
            width: 32px;
            height: 32px;
            background: ${color};
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            border: 2px solid white;
            box-shadow: 0 0 10px ${color};
            position: relative;
        ">${emoji}<div style="
            position: absolute;
            bottom: -6px;
            left: 50%;
            transform: translateX(-50%);
            width: 0;
            height: 0;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 8px solid ${color};
        "></div></div>`,
        iconSize: [32, 38],
        iconAnchor: [16, 38],
        popupAnchor: [0, -38]
    });
}
