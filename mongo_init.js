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
        }
        
        devices.push(device);
    }
    return devices;
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

db.devices.insertMany(envSensors);
db.devices.insertMany(manholeSensors);
db.devices.insertMany(pumps);
db.devices.insertMany(fans);

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

db.devices.createIndex({ location: "2dsphere" });
db.devices.createIndex({ type: 1 });
db.devices.createIndex({ device_id: 1 }, { unique: true });

print("数据库初始化完成！");
print(`环境传感器: ${db.devices.countDocuments({type: 'env_sensor'})}`);
print(`井盖传感器: ${db.devices.countDocuments({type: 'manhole'})}`);
print(`排水泵: ${db.devices.countDocuments({type: 'pump'})}`);
print(`风机: ${db.devices.countDocuments({type: 'fan'})}`);
print(`管廊路径点: ${tunnelPoints.length}`);
