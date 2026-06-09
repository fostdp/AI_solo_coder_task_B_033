const db = db.getSiblingDB('utility_tunnel');

db.dropDatabase();
db = db.getSiblingDB('utility_tunnel');

function generateTunnelGeoJSON() {
    const startLng = 116.40;
    const startLat = 39.90;
    const lengthKm = 15;
    const points = [];
    const numPoints = 100;
    
    for (let i = 0; i <= numPoints; i++) {
        const ratio = i / numPoints;
        const lng = startLng + ratio * 0.15 + Math.sin(ratio * Math.PI) * 0.02;
        const lat = startLat + ratio * 0.08 + Math.cos(ratio * Math.PI * 2) * 0.01;
        points.push([lng, lat]);
    }
    return {
        type: "Feature",
        properties: {
            name: "地下综合管廊",
            length: 15,
            chambers: ["电力舱", "水信舱", "燃气舱"]
        },
        geometry: {
            type: "LineString",
            coordinates: points
        }
    };
}

function generateDevices(tunnelPoints, numDevices, type, chamber, startId) {
    const devices = [];
    for (let i = 0; i < numDevices; i++) {
        const ratio = i / numDevices;
        const idx1 = Math.floor(ratio * (tunnelPoints.length - 1));
        const idx2 = Math.min(idx1 + 1, tunnelPoints.length - 1);
        const t = (ratio * (tunnelPoints.length - 1)) - idx1;
        
        const p1 = tunnelPoints[idx1];
        const p2 = tunnelPoints[idx2];
        const lng = p1[0] + (p2[0] - p1[0]) * t + (Math.random() - 0.5) * 0.001;
        const lat = p1[1] + (p2[1] - p1[1]) * t + (Math.random() - 0.5) * 0.001;
        
        const distance = ratio * 15;
        
        let device = {
            device_id: `${type}_${String(startId + i).padStart(4, '0')}`,
            type: type,
            chamber: chamber,
            name: `${type}${startId + i}`,
            status: "normal",
            distance_km: distance.toFixed(2),
            location: {
                type: "Point",
                coordinates: [lng, lat]
            },
            properties: {}
        };
        
        if (type === "env_sensor") {
            device.properties = {
                temperature: 25,
                humidity: 60,
                oxygen: 20.5,
                methane: 0.05,
                h2s: 2
            };
        } else if (type === "manhole") {
            device.properties = {
                cover_open: false,
                last_open_time: null
            };
        } else if (type === "pump") {
            device.properties = {
                running: false,
                level: 40,
                last_start: null,
                last_stop: null
            };
        } else if (type === "fan") {
            device.properties = {
                running: false,
                speed: 0,
                last_control_time: null
            };
        } else if (type === "fiber_sensor") {
            device.properties = {
                strain: 50 + Math.random() * 50,
                fiber_temperature: 20 + Math.random() * 10,
                crack_width: 0,
                last_strain: 50,
                last_crack_width: 0,
                risk_level: "normal",
                last_reading: null
            };
        } else if (type === "smoke_sensor") {
            device.properties = {
                temperature: 25,
                smoke_density: 0,
                temperature_rate: 0,
                last_reading: null
            };
        } else if (type === "inspection_robot") {
            device.properties = {
                status: "idle",
                battery: 100,
                current_distance_km: 0,
                mission_id: null,
                current_waypoint: null,
                total_waypoints: null,
                speed: 1.0
            };
        } else if (type === "fire_door") {
            device.properties = {
                status: "open",
                auto_mode: true,
                last_operation_time: null,
                zone_id: null
            };
        } else if (type === "fire_extinguisher") {
            device.properties = {
                status: "ready",
                last_activation_time: null,
                pressure: "normal",
                zone_id: null
            };
        }
        
        devices.push(device);
    }
    return devices;
}

function generateAssets(devices) {
    const assets = [];
    const manufacturers = ["华为技术", "西门子", "施耐德电气", "霍尼韦尔", "ABB", "三菱电机", "通用电气"];
    const now = new Date();
    
    devices.forEach((device, idx) => {
        const installYears = 1 + Math.random() * 8;
        const installDate = new Date(now.getTime() - installYears * 365 * 24 * 60 * 60 * 1000);
        const designLife = 8 + Math.random() * 12;
        
        const asset = {
            device_id: device.device_id,
            name: device.name,
            type: device.type,
            manufacturer: manufacturers[Math.floor(Math.random() * manufacturers.length)],
            model: `${device.type.toUpperCase()}-${Math.floor(1000 + Math.random() * 9000)}`,
            serial_number: `SN${device.type.toUpperCase().substring(0, 3)}${Date.now()}${idx}`,
            installation_date: installDate,
            design_life_years: Math.round(designLife * 10) / 10,
            last_maintenance_date: Math.random() > 0.3 
                ? new Date(installDate.getTime() + (installYears - 0.5) * 365 * 24 * 60 * 60 * 1000)
                : null,
            purchase_cost: Math.round((500 + Math.random() * 10000) * 100) / 100,
            location: device.location,
            chamber: device.chamber,
            specifications: {
                "额定电压": "220V",
                "防护等级": "IP65",
                "工作温度": "-20°C ~ 60°C"
            },
            status: "active",
            warranty_end_date: new Date(installDate.getTime() + 3 * 365 * 24 * 60 * 60 * 1000),
            maintenance_count: Math.floor(Math.random() * 10),
            failure_count: Math.floor(Math.random() * 3)
        };
        assets.push(asset);
    });
    return assets;
}

const tunnelGeoJSON = generateTunnelGeoJSON();
const tunnelPoints = tunnelGeoJSON.geometry.coordinates;

db.tunnel_route.insertOne(tunnelGeoJSON);

const envSensors = [
    ...generateDevices(tunnelPoints, 67, "env_sensor", "电力舱", 1),
    ...generateDevices(tunnelPoints, 67, "env_sensor", "水信舱", 100),
    ...generateDevices(tunnelPoints, 66, "env_sensor", "燃气舱", 200)
];

const manholeSensors = generateDevices(tunnelPoints, 100, "manhole", "综合", 1);
const pumps = generateDevices(tunnelPoints, 50, "pump", "水信舱", 1);
const fans = generateDevices(tunnelPoints, 30, "fan", "综合", 1);

const fiberSensors = [
    ...generateDevices(tunnelPoints, 34, "fiber_sensor", "电力舱", 1),
    ...generateDevices(tunnelPoints, 33, "fiber_sensor", "水信舱", 100),
    ...generateDevices(tunnelPoints, 33, "fiber_sensor", "燃气舱", 200)
];

const smokeSensors = [
    ...generateDevices(tunnelPoints, 20, "smoke_sensor", "电力舱", 1),
    ...generateDevices(tunnelPoints, 20, "smoke_sensor", "水信舱", 100),
    ...generateDevices(tunnelPoints, 20, "smoke_sensor", "燃气舱", 200)
];

const robots = generateDevices(tunnelPoints, 5, "inspection_robot", "综合", 1);
const fireDoors = [
    ...generateDevices(tunnelPoints, 5, "fire_door", "电力舱", 1),
    ...generateDevices(tunnelPoints, 5, "fire_door", "水信舱", 100),
    ...generateDevices(tunnelPoints, 6, "fire_door", "燃气舱", 200)
];
const fireExtinguishers = [
    ...generateDevices(tunnelPoints, 17, "fire_extinguisher", "电力舱", 1),
    ...generateDevices(tunnelPoints, 17, "fire_extinguisher", "水信舱", 100),
    ...generateDevices(tunnelPoints, 16, "fire_extinguisher", "燃气舱", 200)
];

const allDevices = [
    ...envSensors,
    ...manholeSensors,
    ...pumps,
    ...fans,
    ...fiberSensors,
    ...smokeSensors,
    ...robots,
    ...fireDoors,
    ...fireExtinguishers
];

db.devices.insertMany(allDevices);

const assets = generateAssets(allDevices);
db.assets.insertMany(assets);

const inspectionRobots = robots.map(r => ({
    robot_id: r.device_id,
    name: r.name,
    status: "idle",
    battery: 100,
    current_distance_km: parseFloat(r.distance_km),
    location: r.location,
    current_waypoint: null,
    total_waypoints: null,
    mission_id: null
}));
db.inspection_robots.insertMany(inspectionRobots);

db.createCollection("sensor_data");
db.sensor_data.createIndex({ device_id: 1, timestamp: -1 });
db.sensor_data.createIndex({ timestamp: -1 });
db.sensor_data.createIndex({ location: "2dsphere" });

db.createCollection("alerts");
db.alerts.createIndex({ timestamp: -1 });
db.alerts.createIndex({ level: 1 });
db.alerts.createIndex({ acknowledged: 1 });

db.createCollection("control_commands");
db.control_commands.createIndex({ timestamp: -1 });
db.control_commands.createIndex({ device_id: 1 });

db.createCollection("operation_logs");
db.operation_logs.createIndex({ timestamp: -1 });
db.operation_logs.createIndex({ device_id: 1 });

db.createCollection("health_scores");
db.health_scores.createIndex({ timestamp: -1 });

db.createCollection("structure_alerts");
db.structure_alerts.createIndex({ timestamp: -1 });
db.structure_alerts.createIndex({ risk_level: 1 });
db.structure_alerts.createIndex({ acknowledged: 1 });
db.structure_alerts.createIndex({ device_id: 1 });

db.createCollection("fiber_sensor_data");
db.fiber_sensor_data.createIndex({ device_id: 1, timestamp: -1 });
db.fiber_sensor_data.createIndex({ timestamp: -1 });
db.fiber_sensor_data.createIndex({ distance_km: 1 });

db.createCollection("inspection_missions");
db.inspection_missions.createIndex({ mission_id: 1 }, { unique: true });
db.inspection_missions.createIndex({ robot_id: 1 });
db.inspection_missions.createIndex({ status: 1 });
db.inspection_missions.createIndex({ start_time: -1 });

db.createCollection("robot_positions");
db.robot_positions.createIndex({ robot_id: 1, timestamp: -1 });
db.robot_positions.createIndex({ timestamp: -1 });

db.createCollection("fire_alerts");
db.fire_alerts.createIndex({ alert_id: 1 }, { unique: true });
db.fire_alerts.createIndex({ timestamp: -1 });
db.fire_alerts.createIndex({ risk_level: 1 });
db.fire_alerts.createIndex({ acknowledged: 1 });
db.fire_alerts.createIndex({ chamber: 1 });

db.createCollection("fire_zone_status");
db.fire_zone_status.createIndex({ zone_id: 1 }, { unique: true });
db.fire_zone_status.createIndex({ chamber: 1 });

db.createCollection("maintenance_records");
db.maintenance_records.createIndex({ record_id: 1 }, { unique: true });
db.maintenance_records.createIndex({ device_id: 1 });
db.maintenance_records.createIndex({ status: 1 });
db.maintenance_records.createIndex({ start_time: -1 });

db.createCollection("maintenance_plans");
db.maintenance_plans.createIndex({ plan_id: 1 }, { unique: true });
db.maintenance_plans.createIndex({ year: 1, month: 1 });
db.maintenance_plans.createIndex({ status: 1 });

db.createCollection("life_predictions");
db.life_predictions.createIndex({ device_id: 1, timestamp: -1 });
db.life_predictions.createIndex({ risk_level: 1 });
db.life_predictions.createIndex({ timestamp: -1 });

db.devices.createIndex({ location: "2dsphere" });
db.devices.createIndex({ type: 1 });
db.devices.createIndex({ device_id: 1 }, { unique: true });

db.assets.createIndex({ device_id: 1 }, { unique: true });
db.assets.createIndex({ type: 1 });
db.assets.createIndex({ chamber: 1 });
db.assets.createIndex({ status: 1 });

db.inspection_robots.createIndex({ robot_id: 1 }, { unique: true });
db.inspection_robots.createIndex({ status: 1 });

print("数据库初始化完成！");
print(`环境传感器: ${db.devices.countDocuments({type: 'env_sensor'})}`);
print(`井盖传感器: ${db.devices.countDocuments({type: 'manhole'})}`);
print(`排水泵: ${db.devices.countDocuments({type: 'pump'})}`);
print(`风机: ${db.devices.countDocuments({type: 'fan'})}`);
print(`光纤传感器: ${db.devices.countDocuments({type: 'fiber_sensor'})}`);
print(`烟雾传感器: ${db.devices.countDocuments({type: 'smoke_sensor'})}`);
print(`巡检机器人: ${db.devices.countDocuments({type: 'inspection_robot'})}`);
print(`防火门: ${db.devices.countDocuments({type: 'fire_door'})}`);
print(`灭火装置: ${db.devices.countDocuments({type: 'fire_extinguisher'})}`);
print(`资产总数: ${db.assets.countDocuments()}`);
print(`管廊路径点: ${tunnelPoints.length}`);
