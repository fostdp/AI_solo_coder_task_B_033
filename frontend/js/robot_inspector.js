class RobotPlannerComponent {
    constructor() {
        this.robots = [];
        this.robotMarkers = {};
        this.trackLayers = {};
        this.activeMissions = [];
        this.selectedRobot = null;
        this.activeOverlay = false;
        this.updateInterval = null;
        this.containerId = 'robot-inspector';
        this.isInitialized = false;
    }

    init(options = {}) {
        if (this.isInitialized) return;

        this.containerId = options.containerId || this.containerId;
        this.robots = options.initialRobots || [];
        this.activeMissions = options.initialMissions || [];
        this.updateIntervalMs = options.updateIntervalMs || 3000;

        this.bindEvents();
        this.isInitialized = true;
        console.log('RobotPlannerComponent initialized');
    }

    render() {
        if (!this.isInitialized) {
            this.init();
        }

        this.renderRobotMarkers();
        this.renderRobotStats();
        if (this.activeOverlay) {
            this.renderAllTracks();
        }
    }

    update(data = {}) {
        if (data.robots !== undefined) {
            this.robots = data.robots;
        }
        if (data.missions !== undefined) {
            this.activeMissions = data.missions;
        }
        if (data.activeOverlay !== undefined) {
            this.activeOverlay = data.activeOverlay;
        }
        if (data.selectedRobot !== undefined) {
            this.selectedRobot = data.selectedRobot;
        }

        this.render();
    }

    bindEvents() {
        const toggleBtn = document.getElementById('toggle-robot-tracks');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', (e) => {
                const show = e.target.checked || e.target.dataset.show === 'true';
                this.toggleTracks(show);
            });
        }

        const startUpdatesBtn = document.getElementById('start-robot-updates');
        if (startUpdatesBtn) {
            startUpdatesBtn.addEventListener('click', () => {
                this.startRealTimeUpdates();
            });
        }

        const stopUpdatesBtn = document.getElementById('stop-robot-updates');
        if (stopUpdatesBtn) {
            stopUpdatesBtn.addEventListener('click', () => {
                this.stopRealTimeUpdates();
            });
        }
    }

    async fetchRobots() {
        try {
            const response = await fetch('/api/robots');
            if (response.ok) {
                const data = await response.json();
                this.update({ robots: data.robots || [] });
                return this.robots;
            }
        } catch (error) {
            console.error('Failed to fetch robots:', error);
        }
        return [];
    }

    async fetchRobotPositions(robotId, limit = 50) {
        try {
            const response = await fetch(
                `/api/robots/${robotId}/trajectory?hours=${Math.ceil(limit / 60)}`
            );
            if (response.ok) {
                const data = await response.json();
                return data.trajectory || [];
            }
        } catch (error) {
            console.error('Failed to fetch robot positions:', error);
        }
        return [];
    }

    async fetchMissions(robotId = null) {
        try {
            const url = robotId
                ? `/api/robots/${robotId}/missions`
                : '/api/robots/missions';
            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                this.update({ missions: data.missions || [] });
                return this.activeMissions;
            }
        } catch (error) {
            console.error('Failed to fetch missions:', error);
        }
        return [];
    }

    renderRobotMarkers() {
        if (!window.map) return;

        Object.values(this.robotMarkers).forEach(marker => {
            window.map.removeLayer(marker);
        });
        this.robotMarkers = {};

        this.robots.forEach(robot => {
            if (robot.location && robot.location.coordinates) {
                const icon = this.getRobotIcon(robot.status);
                const marker = L.marker(
                    [robot.location.coordinates[1], robot.location.coordinates[0]],
                    { icon: icon }
                ).addTo(window.map);

                marker.bindPopup(this.getRobotPopup(robot));
                marker.on('click', () => this.showRobotDetail(robot));

                this.robotMarkers[robot.robot_id] = marker;
            }
        });
    }

    getRobotIcon(status) {
        const colors = {
            idle: '#6b7280',
            working: '#22c55e',
            charging: '#eab308',
            paused: '#f97316',
            error: '#ef4444'
        };
        const color = colors[status] || '#6b7280';

        return L.divIcon({
            html: `<div style="
                width: 32px;
                height: 32px;
                background: ${color};
                border-radius: 50%;
                border: 3px solid white;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 18px;
            ">🤖</div>`,
            className: 'robot-marker',
            iconSize: [32, 32],
            iconAnchor: [16, 16]
        });
    }

    getRobotPopup(robot) {
        const missionInfo = robot.mission_id
            ? `<br/>任务: ${robot.mission_id}<br/>进度: ${robot.current_waypoint || 0}/${robot.total_waypoints || 0}`
            : '';

        return `
            <strong>🤖 ${robot.name}</strong><br/>
            编号: ${robot.robot_id}<br/>
            状态: ${this.getStatusText(robot.status)}<br/>
            电量: ${robot.battery.toFixed(1)}%<br/>
            位置: ${robot.current_distance_km.toFixed(2)} km
            ${missionInfo}
        `;
    }

    getStatusText(status) {
        const texts = {
            idle: '空闲',
            working: '巡检中',
            charging: '充电中',
            paused: '已暂停',
            error: '故障',
            returning: '返回基地'
        };
        return texts[status] || status;
    }

    renderRobotStats() {
        const workingCount = this.robots.filter(r => r.status === 'working').length;
        const totalCount = this.robots.length;

        const workingElem = document.getElementById('working-robots');
        if (workingElem) {
            workingElem.textContent = `${workingCount} / ${totalCount || 5}`;
        }

        const activeElem = document.getElementById('active-robots');
        if (activeElem) {
            activeElem.textContent = `${workingCount} / ${totalCount || 5}`;
        }
    }

    toggleTracks(show) {
        this.update({ activeOverlay: show });

        if (show) {
            this.renderAllTracks();
        } else {
            this.clearAllTracks();
        }
    }

    async renderAllTracks() {
        this.clearAllTracks();

        for (const robot of this.robots) {
            const positions = await this.fetchRobotPositions(robot.robot_id);
            if (positions.length > 1) {
                const latlngs = positions.map(p => [
                    p.location.coordinates[1],
                    p.location.coordinates[0]
                ]);

                const polyline = L.polyline(latlngs, {
                    color: '#3b82f6',
                    weight: 3,
                    opacity: 0.7,
                    dashArray: '10, 10'
                }).addTo(window.map);

                this.trackLayers[robot.robot_id] = polyline;
            }
        }
    }

    clearAllTracks() {
        Object.values(this.trackLayers).forEach(layer => {
            if (window.map) {
                window.map.removeLayer(layer);
            }
        });
        this.trackLayers = {};
    }

    showRobotDetail(robot) {
        this.update({ selectedRobot: robot });

        const modal = document.getElementById('robot-modal');
        if (modal) {
            document.getElementById('robot-modal-title').textContent =
                `🤖 ${robot.name} - 巡检机器人详情`;
            document.getElementById('robot-id').textContent = robot.robot_id;
            document.getElementById('robot-status').textContent =
                this.getStatusText(robot.status);
            document.getElementById('robot-position').textContent =
                `${robot.current_distance_km.toFixed(2)} km`;
            document.getElementById('robot-mission').textContent =
                robot.mission_id || '无';

            this.renderBatteryDisplay(robot.battery);
            this.renderProgressDisplay(robot);

            modal.style.display = 'block';
        }
    }

    renderBatteryDisplay(battery) {
        const fill = document.getElementById('battery-fill');
        const text = document.getElementById('battery-text');
        if (fill) {
            fill.style.width = `${battery}%`;
            fill.style.background = battery > 50 ? '#22c55e' :
                battery > 20 ? '#eab308' : '#ef4444';
        }
        if (text) {
            text.textContent = `${battery.toFixed(1)}%`;
        }
    }

    renderProgressDisplay(robot) {
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');

        if (robot.total_waypoints && robot.current_waypoint) {
            const progress = (robot.current_waypoint / robot.total_waypoints) * 100;
            if (fill) {
                fill.style.width = `${progress}%`;
            }
            if (text) {
                text.textContent = `${progress.toFixed(1)}%`;
            }
        } else {
            if (fill) {
                fill.style.width = '0%';
            }
            if (text) {
                text.textContent = '0%';
            }
        }
    }

    async startMission(robotId, startDistance = 0, endDistance = 15) {
        try {
            const response = await fetch(
                `/api/robots/missions/plan?robot_id=${robotId}&start_km=${startDistance}&end_km=${endDistance}&chamber=电力舱`,
                { method: 'POST' }
            );

            if (response.ok) {
                const data = await response.json();
                if (data.mission) {
                    const missionId = data.mission.mission_id;

                    await fetch(`/api/robots/missions/${missionId}/start`, {
                        method: 'POST'
                    });

                    alert('巡检任务已启动');
                    this.fetchRobots();
                }
            }
        } catch (error) {
            console.error('Failed to start mission:', error);
            alert('启动任务失败');
        }
    }

    async controlRobot(robotId, action) {
        try {
            const endpoint = action === 'pause' ? 'pause' :
                           action === 'resume' ? 'resume' :
                           action === 'return' ? 'return' : 'pause';

            const response = await fetch(`/api/robots/${robotId}/${endpoint}`, {
                method: 'POST'
            });

            if (response.ok) {
                alert(`操作成功: ${action}`);
                this.fetchRobots();
            }
        } catch (error) {
            console.error(`Failed to ${action} robot:`, error);
            alert('操作失败');
        }
    }

    startRealTimeUpdates(intervalMs = null) {
        const ms = intervalMs || this.updateIntervalMs || 3000;
        this.stopRealTimeUpdates();

        this.updateInterval = setInterval(() => {
            this.fetchRobots();
        }, ms);

        console.log(`Robot real-time updates started (${ms}ms)`);
    }

    stopRealTimeUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
            console.log('Robot real-time updates stopped');
        }
    }

    destroy() {
        this.stopRealTimeUpdates();
        this.clearAllTracks();
        Object.values(this.robotMarkers).forEach(marker => {
            if (window.map) {
                window.map.removeLayer(marker);
            }
        });
        this.robotMarkers = {};
        this.isInitialized = false;
        console.log('RobotPlannerComponent destroyed');
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = RobotPlannerComponent;
} else {
    window.RobotPlannerComponent = RobotPlannerComponent;
    window.robotInspector = new RobotPlannerComponent();
}
