class RobotInspector {
    constructor() {
        this.robots = [];
        this.robotMarkers = {};
        this.trackLayers = {};
        this.activeMissions = [];
        this.selectedRobot = null;
        this.activeOverlay = false;
        this.updateInterval = null;
    }

    async fetchRobots() {
        try {
            const response = await fetch('/api/robots');
            if (response.ok) {
                const data = await response.json();
                this.robots = data.robots || [];
                this.updateRobotMarkers();
                this.updateRobotStats();
            }
        } catch (error) {
            console.error('Failed to fetch robots:', error);
        }
    }

    async fetchRobotPositions(robotId, limit = 50) {
        try {
            const response = await fetch(
                `/api/robots/${robotId}/positions?limit=${limit}`
            );
            if (response.ok) {
                const data = await response.json();
                return data.positions || [];
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
                this.activeMissions = data.missions || [];
            }
        } catch (error) {
            console.error('Failed to fetch missions:', error);
        }
    }

    updateRobotMarkers() {
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

        if (this.activeOverlay) {
            this.drawAllTracks();
        }
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

    updateRobotStats() {
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
        this.activeOverlay = show;
        if (show) {
            this.drawAllTracks();
        } else {
            this.clearAllTracks();
        }
    }

    async drawAllTracks() {
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
        this.selectedRobot = robot;
        
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
            
            this.updateBatteryDisplay(robot.battery);
            this.updateProgressDisplay(robot);
            
            modal.style.display = 'block';
        }
    }

    updateBatteryDisplay(battery) {
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

    updateProgressDisplay(robot) {
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
            const response = await fetch('/api/robots/mission/plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    robot_id: robotId,
                    start_distance_km: startDistance,
                    end_distance_km: endDistance,
                    avoid_hazardous: true
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                const missionId = data.mission_id;
                
                await fetch('/api/robots/mission/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mission_id: missionId })
                });
                
                alert('巡检任务已启动');
                this.fetchRobots();
            }
        } catch (error) {
            console.error('Failed to start mission:', error);
            alert('启动任务失败');
        }
    }

    async controlRobot(robotId, action) {
        try {
            const response = await fetch(`/api/robots/${robotId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action })
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

    startRealTimeUpdates(intervalMs = 3000) {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }
        this.updateInterval = setInterval(() => {
            this.fetchRobots();
        }, intervalMs);
    }

    stopRealTimeUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
}

window.robotInspector = new RobotInspector();
