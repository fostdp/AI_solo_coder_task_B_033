#!/bin/bash
set -e

echo "============================================================"
echo "MongoDB 副本集和分片初始化"
echo "============================================================"

echo "等待MongoDB节点就绪..."
sleep 10

until mongosh --host mongo1:27017 --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
    echo "等待 mongo1..."
    sleep 2
done

until mongosh --host mongo2:27018 --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
    echo "等待 mongo2..."
    sleep 2
done

until mongosh --host mongo3:27019 --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
    echo "等待 mongo3..."
    sleep 2
done

until mongosh --host mongos:27020 --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
    echo "等待 mongos..."
    sleep 2
done

echo "初始化副本集 rs0..."
mongosh --host mongo1:27017 --eval '
rs.initiate({
    _id: "rs0",
    members: [
        { _id: 0, host: "mongo1:27017", priority: 2 },
        { _id: 1, host: "mongo2:27018", priority: 1 },
        { _id: 2, host: "mongo3:27019", priority: 1 }
    ]
})
'

echo "等待副本集选举完成..."
sleep 15

echo "等待mongos就绪..."
sleep 10

echo "添加分片..."
mongosh --host mongos:27020 --eval '
sh.addShard("rs0/mongo1:27017,mongo2:27018,mongo3:27019")
'

echo "检查分片状态..."
mongosh --host mongos:27020 --eval '
sh.status()
'

echo "初始化配置服务器副本集 cfg0..."
mongosh --host mongocfg1:27019 --eval '
rs.initiate({
    _id: "cfg0",
    configsvr: true,
    members: [
        { _id: 0, host: "mongocfg1:27019" }
    ]
})
'

echo "等待配置服务器就绪..."
sleep 10

echo "启用数据库分片..."
mongosh --host mongos:27020 --eval '
sh.enableSharding("pipe_corridor")
'

echo "为集合配置分片键（按设备ID+时间戳分片）..."
mongosh --host mongos:27020 --eval '
sh.shardCollection("pipe_corridor.environment_data", { device_id: 1, timestamp: 1 })
sh.shardCollection("pipe_corridor.manhole_data", { device_id: 1, timestamp: 1 })
sh.shardCollection("pipe_corridor.alarms", { device_id: 1, timestamp: 1 })
sh.shardCollection("pipe_corridor.operation_history", { device_id: 1, timestamp: 1 })
'

echo "创建索引..."
mongosh --host mongos:27020 --eval '
use pipe_corridor
db.environment_data.createIndex({ device_id: 1, timestamp: -1 })
db.environment_data.createIndex({ cabin: 1, timestamp: -1 })
db.environment_data.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000 })
db.manhole_data.createIndex({ device_id: 1, timestamp: -1 })
db.alarms.createIndex({ status: 1, level: 1, timestamp: -1 })
db.operation_history.createIndex({ device_id: 1, timestamp: -1 })
db.devices.createIndex({ device_id: 1 }, { unique: true })
db.devices.createIndex({ type: 1, cabin: 1, status: 1 })
'

echo "初始化设备数据..."
mongosh --host mongos:27020 /docker-entrypoint-initdb.d/init.js

echo "设置TTL索引自动清理30天前的数据..."
mongosh --host mongos:27020 --eval '
use pipe_corridor
db.environment_data.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000, background: true })
db.manhole_data.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000, background: true })
db.alarms.createIndex({ timestamp: 1 }, { expireAfterSeconds: 7776000, background: true })
'

echo "============================================================"
echo "MongoDB 初始化完成！"
echo "副本集 rs0: mongo1:27017, mongo2:27018, mongo3:27019"
echo "mongos路由: mongos:27020"
echo "分片数据库: pipe_corridor"
echo "============================================================"
