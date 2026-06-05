const DB_NAME = "pipe_corridor";

db = db.getSiblingDB(DB_NAME);

print("=" * 60);
print("正在初始化地下管廊综合监控系统数据库...");
print("=" * 60);

const collections = [
    { name: "devices", indexes: [
        { key: { device_id: 1 }, unique: true },
        { key: { type: 1 } },
        { key: { cabin: 1 } },
        { key: { status: 1 } },
        { key: { location: "2dsphere" } }
    ]},
    { name: "environment_data", indexes: [
        { key: { device_id: 1, timestamp: -1 } },
        { key: { timestamp: -1 } },
        { key: { cabin: 1, timestamp: -1 } }
    ]},
    { name: "manhole_data", indexes: [
        { key: { device_id: 1, timestamp: -1 } },
        { key: { timestamp: -1 } },
        { key: { is_open: 1, timestamp: -1 } }
    ]},
    { name: "fan_data", indexes: [
        { key: { device_id: 1, timestamp: -1 } },
        { key: { timestamp: -1 } },
        { key: { is_running: 1 } }
    ]},
    { name: "pump_data", indexes: [
        { key: { device_id: 1, timestamp: -1 } },
        { key: { timestamp: -1 } },
        { key: { is_running: 1 } }
    ]},
    { name: "alarms", indexes: [
        { key: { timestamp: -1 } },
        { key: { level: 1, timestamp: -1 } },
        { key: { device_id: 1, timestamp: -1 } },
        { key: { acknowledged: 1, timestamp: -1 } },
        { key: { alarm_type: 1, timestamp: -1 } }
    ]},
    { name: "operation_history", indexes: [
        { key: { device_id: 1, timestamp: -1 } },
        { key: { timestamp: -1 } },
        { key: { operator: 1, timestamp: -1 } }
    ]},
    { name: "corridor_geojson", indexes: [] },
    { name: "system_logs", indexes: [
        { key: { timestamp: -1 } },
        { key: { level: 1, timestamp: -1 } }
    ]}
];

collections.forEach(col => {
    const existing = db.getCollectionNames().includes(col.name);
    if (!existing) {
        db.createCollection(col.name);
        print(`[创建] 集合: ${col.name}`);
    } else {
        print(`[已存在] 集合: ${col.name}`);
    }

    col.indexes.forEach(idx => {
        try {
            db[col.name].createIndex(idx.key, idx.unique ? { unique: true } : {});
            print(`  [索引] ${JSON.stringify(idx.key)}`);
        } catch (e) {
            print(`  [索引跳过] ${JSON.stringify(idx.key)}: ${e.message}`);
        }
    });
});

print("\n" + "=" * 60);
print("正在初始化设备数据...");
print("=" + 60);

const cabins = ["power", "water", "gas"];
const cabinNames = { power: "电力舱", water: "水信舱", gas: "燃气舱" };
const startLng = 116.397;
const startLat = 39.908;

function generateCorridorPath() {
    const features = [];

    for (let c = 0; c < cabins.length; c++) {
        const cabin = cabins[c];
        const latOffset = c * 0.002;
        const coordinates = [];

        for (let i = 0; i <= 150; i++) {
            const lng = startLng + i * 0.001;
            const lat = startLat + latOffset + Math.sin(i * 0.1) * 0.0005;
            coordinates.push([lng, lat]);
        }

        features.push({
            type: "Feature",
            properties: {
                name: `${cabinNames[cabin]}主通道`,
                cabin: cabin,
                length_km: 15,
                type: "main_corridor"
            },
            geometry: {
                type: "LineString",
                coordinates: coordinates
            }
        });

        for (let s = 0; s < 15; s++) {
            const idx = s * 10 + 5;
            const entryLng = startLng + idx * 0.001;
            const entryLat = startLat + latOffset + Math.sin(idx * 0.1) * 0.0005;

            features.push({
                type: "Feature",
                properties: {
                    name: `${cabinNames[cabin]}出入口 #${s + 1}`,
                    cabin: cabin,
                    type: "entrance"
                },
                geometry: {
                    type: "Point",
                    coordinates: [entryLng, entryLat]
                }
            });
        }
    }

    return {
        type: "FeatureCollection",
        name: "管廊走向图",
        features: features
    };
}

const corridorGeoJSON = generateCorridorPath();
db.corridor_geojson.deleteMany({});
db.corridor_geojson.insertOne(corridorGeoJSON);
print("[完成] 管廊GeoJSON数据已初始化");

db.devices.deleteMany({});

const devices = [];
let deviceIndex = 1;

for (let c = 0; c < cabins.length; c++) {
    const cabin = cabins[c];
    const latOffset = c * 0.002;

    for (let i = 0; i < 67; i++) {
        if (c === 2 && i >= 66) break;

        const lng = startLng + (i * 0.224 + Math.random() * 0.05) * 0.001;
        const lat = startLat + latOffset + Math.sin(i * 0.1) * 0.0005 + (Math.random() - 0.5) * 0.0003;

        devices.push({
            device_id: `ENV-${String(deviceIndex).padStart(4, '0')}`,
            name: `${cabinNames[cabin]}环境传感器 #${i + 1}`,
            type: "env_sensor",
            cabin: cabin,
            location: [lng, lat],
            status: "normal",
            description: "五参数环境传感器（温度、湿度、氧气、甲烷、硫化氢）",
            last_update: null
        });
        deviceIndex++;
    }
}

print(`[完成] 已创建 ${devices.length} 个环境传感器`);

let manholeCount = 0;
for (let c = 0; c < cabins.length; c++) {
    const cabin = cabins[c];
    const latOffset = c * 0.002;

    for (let i = 0; i < 34; i++) {
        if (c === 2 && i >= 32) break;

        const lng = startLng + (i * 0.45 + Math.random() * 0.03) * 0.001;
        const lat = startLat + latOffset + 0.0003 + Math.sin(i * 0.15) * 0.0002;

        devices.push({
            device_id: `MH-${String(manholeCount + 1).padStart(4, '0')}`,
            name: `${cabinNames[cabin]}井盖传感器 #${i + 1}`,
            type: "manhole",
            cabin: cabin,
            location: [lng, lat],
            status: "normal",
            description: "智能井盖状态监测传感器",
            last_update: null
        });
        manholeCount++;
    }
}

print(`[完成] 已创建 ${manholeCount} 个井盖传感器`);

let fanCount = 0;
for (let c = 0; c < cabins.length; c++) {
    const cabin = cabins[c];
    const latOffset = c * 0.002;

    for (let i = 0; i < 10; i++) {
        const lng = startLng + (i * 1.5 + 0.5) * 0.001;
        const lat = startLat + latOffset + Math.sin(i * 0.2) * 0.0004;

        devices.push({
            device_id: `FAN-${String(fanCount + 1).padStart(3, '0')}`,
            name: `${cabinNames[cabin]}轴流风机 #${i + 1}`,
            type: "fan",
            cabin: cabin,
            location: [lng, lat],
            status: "normal",
            description: "智能通风系统轴流风机，变频调速",
            last_update: null
        });
        fanCount++;
    }
}

print(`[完成] 已创建 ${fanCount} 台风机`);

let pumpCount = 0;
for (let c = 0; c < cabins.length; c++) {
    const cabin = cabins[c];
    const latOffset = c * 0.002;
    const count = c === 1 ? 20 : 15;

    for (let i = 0; i < count; i++) {
        const lng = startLng + (i * (15 / count) + 0.3) * 0.001;
        const lat = startLat + latOffset - 0.0002 + Math.cos(i * 0.25) * 0.0003;

        devices.push({
            device_id: `PUMP-${String(pumpCount + 1).padStart(3, '0')}`,
            name: `${cabinNames[cabin]}排水泵 #${i + 1}`,
            type: "pump",
            cabin: cabin,
            location: [lng, lat],
            status: "normal",
            description: "集水坑自动排水泵",
            last_update: null
        });
        pumpCount++;
    }
}

print(`[完成] 已创建 ${pumpCount} 台排水泵`);

db.devices.insertMany(devices);
print(`\n[完成] 共初始化 ${devices.length} 个设备`);
print(`  - 环境传感器: 200个`);
print(`  - 井盖传感器: ${manholeCount}个`);
print(`  - 风机: ${fanCount}台`);
print(`  - 排水泵: ${pumpCount}台`);

const sampleTime = new Date();
const sampleEnvData = [];
for (let i = 0; i < 10; i++) {
    sampleEnvData.push({
        device_id: `ENV-${String(i + 1).padStart(4, '0')}`,
        cabin: "power",
        timestamp: new Date(sampleTime.getTime() - i * 60000),
        temperature: 25 + Math.random() * 5,
        humidity: 50 + Math.random() * 20,
        oxygen: 20.5 + Math.random() * 0.5,
        methane: Math.random() * 0.1,
        hydrogen_sulfide: Math.random() * 2,
        rssi: -60 + Math.random() * 20
    });
}
db.environment_data.insertMany(sampleEnvData);
print("\n[完成] 已插入10条环境数据样本");

print("\n" + "=" * 60);
print("数据库初始化完成！");
print("=" * 60);
print(`数据库名称: ${DB_NAME}`);
print(`集合数量: ${db.getCollectionNames().length}`);
print(`设备总数: ${db.devices.countDocuments()}`);
print("=" * 60);
