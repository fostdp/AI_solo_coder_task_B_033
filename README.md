# 地下管廊综合监控与智能运维系统

## 目录
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [部署步骤](#部署步骤)
- [模拟器配置说明](#模拟器配置说明)
- [服务说明](#服务说明)
- [API接口](#api接口)

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                 Nginx                                    │
│  (Gzip压缩 / 静态资源缓存 / 反向代理 / WebSocket代理)                    │
└─────────────┬───────────────────────────────────┬───────────────────────┘
              │                                   │
              ▼                                   ▼
┌──────────────────────┐            ┌──────────────────────────────┐
│      Frontend        │            │         FastAPI              │
│  (Leaflet + Canvas)  │            │ (Gunicorn + Uvicorn Workers) │
└──────────────────────┘            └──────────┬───────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
        ┌──────────────────┐      ┌──────────────────┐        ┌──────────────────┐
        │  LoRa Receiver   │      │Ventilation Ctrl  │        │   Pump Ctrl      │
        │  (数据接收/校验) │      │  (模糊推理)      │        │  (液位控制)      │
        └─────────┬────────┘      └─────────┬────────┘        └─────────┬────────┘
                  │                          │                          │
                  └──────────────────────────┼──────────────────────────┘
                                             │
                                             ▼
                                  ┌──────────────────┐
                                  │  Redis Pub/Sub   │
                                  │  (模块间通信)    │
                                  └─────────┬────────┘
                                            │
                        ┌───────────────────┼───────────────────┐
                        │                   │                   │
                        ▼                   ▼                   ▼
              ┌──────────────┐   ┌──────────────┐    ┌──────────────┐
              │  MongoDB     │   │   MQTT       │    │ Alarm Manager│
              │ (副本集+分片)│   │  (Eclipse     │    │ (告警分级/    │
              │              │   │   Mosquitto)  │    │  通知路由)   │
              └──────────────┘   └──────┬───────┘    └──────┬───────┘
                                        │                   │
                                        └─────────┬─────────┘
                                                  │
                                                  ▼
                                        ┌──────────────────┐
                                        │  PLC Simulator   │
                                        │ (风机/水泵模拟)  │
                                        └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                              LoRa Simulator                             │
│  (200环境传感器 + 100井盖传感器, 1分钟间隔上报, 可配置气体浓度)         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Leaflet + Canvas + Chart.js | 管廊地图可视化、设备状态展示、趋势图 |
| 反向代理 | Nginx | Gzip压缩、静态资源缓存、API缓存、WebSocket代理 |
| 后端 | FastAPI + Gunicorn + Uvicorn | 异步Web服务，多Worker模式 |
| 数据库 | MongoDB 6 | 副本集 + 自动分片，存储时序数据 |
| 消息队列 | Redis 7 | Pub/Sub模块间通信，LRU缓存策略 |
| 消息协议 | MQTT (Eclipse Mosquitto) | 设备控制指令下发、状态上报 |
| 容器化 | Docker + docker-compose | 多阶段构建、服务编排 |
| 控制算法 | 模糊控制(Mamdani) + PID | 通风智能控制 |
| 控制策略 | 施密特触发器(滞后控制) | 排水泵控制，防频繁启停 |

## 部署步骤

### 前置要求
- Docker Engine >= 20.10
- Docker Compose >= 2.0
- 至少4核CPU、8GB内存、20GB磁盘空间

### 1. 克隆项目
```bash
git clone <repository-url>
cd AI_solo_coder_task_A_033
```

### 2. 配置环境变量
编辑 `.env` 文件，根据需要调整配置：
```bash
cp .env.example .env  # 如果需要示例文件
vim .env
```

### 3. 初始化MongoDB数据
```bash
docker compose run --rm mongo1 mongosh --eval "
  rs.initiate({
    _id: 'rs0',
    members: [
      { _id: 0, host: 'mongo1:27017' },
      { _id: 1, host: 'mongo2:27017' },
      { _id: 2, host: 'mongo3:27017' }
    ]
  });
"
```

### 4. 启动所有服务
```bash
# 构建并启动所有服务
docker compose up -d --build

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f
```

### 5. 验证部署
```bash
# 检查FastAPI健康状态
curl http://localhost/health

# 检查MongoDB副本集状态
docker compose exec mongo1 mongosh --eval "rs.status()"

# 检查Redis状态
docker compose exec redis redis-cli ping

# 检查MQTT Broker
docker compose exec mqtt mosquitto_sub -t '$SYS/broker/version' -C 1
```

### 6. 初始化数据库（首次部署）
```bash
# 执行MongoDB初始化脚本
docker compose exec mongo1 mongosh /docker-entrypoint-initdb.d/replicaset-init.js

# 执行分片初始化
docker compose exec mongos mongosh --port 27018 /docker-entrypoint-initdb.d/shard-init.js
```

### 7. 访问系统
- 前端界面: http://localhost
- API文档: http://localhost/docs
- 健康检查: http://localhost/health

### 常用操作命令
```bash
# 停止所有服务
docker compose down

# 重启特定服务
docker compose restart fastapi

# 查看服务日志
docker compose logs -f fastapi
docker compose logs -f lora-simulator
docker compose logs -f plc-simulator

# 清理资源（保留数据卷）
docker compose down

# 清理所有资源（包括数据卷）
docker compose down -v

# 升级服务
docker compose pull
docker compose up -d --build
```

## 模拟器配置说明

### LoRa网关模拟器

#### 功能特性
- 模拟200个环境传感器（温度、湿度、氧气、甲烷、硫化氢）
- 模拟100个井盖状态传感器
- 1分钟数据上报间隔
- 可配置的气体浓度范围
- 支持异常模式（按概率生成超限数据）

#### 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LORA_API_URL` | `http://fastapi:8000/api/sensor/data` | 数据上报API地址 |
| `LORA_INTERVAL` | `60` | 上报间隔（秒） |
| `LORA_NUM_ENV_SENSORS` | `200` | 环境传感器数量 |
| `LORA_NUM_MANHOLE_SENSORS` | `100` | 井盖传感器数量 |
| `LORA_METHANE_NORMAL_MIN` | `0.0` | 甲烷正常范围最小值(%) |
| `LORA_METHANE_NORMAL_MAX` | `0.1` | 甲烷正常范围最大值(%) |
| `LORA_METHANE_ANOMALY_MIN` | `0.8` | 甲烷异常范围最小值(%) |
| `LORA_METHANE_ANOMALY_MAX` | `1.5` | 甲烷异常范围最大值(%) |
| `LORA_H2S_NORMAL_MIN` | `0.0` | 硫化氢正常范围最小值(ppm) |
| `LORA_H2S_NORMAL_MAX` | `5.0` | 硫化氢正常范围最大值(ppm) |
| `LORA_H2S_ANOMALY_MIN` | `12.0` | 硫化氢异常范围最小值(ppm) |
| `LORA_H2S_ANOMALY_MAX` | `20.0` | 硫化氢异常范围最大值(ppm) |
| `LORA_OXYGEN_NORMAL_MIN` | `19.5` | 氧气正常范围最小值(%) |
| `LORA_OXYGEN_NORMAL_MAX` | `20.5` | 氧气正常范围最大值(%) |
| `LORA_OXYGEN_ANOMALY_MIN` | `16.0` | 氧气异常范围最小值(%) |
| `LORA_OXYGEN_ANOMALY_MAX` | `17.5` | 氧气异常范围最大值(%) |
| `LORA_TEMPERATURE_NORMAL_MIN` | `18.0` | 温度正常范围最小值(°C) |
| `LORA_TEMPERATURE_NORMAL_MAX` | `28.0` | 温度正常范围最大值(°C) |
| `LORA_HUMIDITY_NORMAL_MIN` | `40.0` | 湿度正常范围最小值(%) |
| `LORA_HUMIDITY_NORMAL_MAX` | `70.0` | 湿度正常范围最大值(%) |
| `LORA_ANOMALY_PROBABILITY` | `0.05` | 异常数据概率(0.05=5%) |

#### 配置示例
```bash
# 提高异常概率到10%，甲烷告警阈值设置为0.5%
LORA_ANOMALY_PROBABILITY=0.1
LORA_METHANE_ANOMALY_MIN=0.5
LORA_METHANE_ANOMALY_MAX=1.0
```

### PLC模拟器

#### 功能特性
- 模拟30台风机、50台排水泵
- 接收MQTT控制指令
- 实时反馈设备状态
- 发布遥测数据（电流、电压、温度）
- 支持HTTP fallback模式

#### MQTT主题定义

| 主题 | 方向 | 说明 |
|------|------|------|
| `tunnel/control` | 下行 | 控制指令下发 |
| `tunnel/status` | 上行 | 设备状态上报 |
| `tunnel/telemetry` | 上行 | 遥测数据发布 |
| `tunnel/response/{device_id}` | 上行 | 指令响应 |

#### 控制指令格式
```json
{
  "device_id": "fan_001",
  "command": "start",
  "params": {
    "speed": 75.0
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

#### 支持的指令

| 指令 | 适用设备 | 说明 |
|------|----------|------|
| `start` | 风机/水泵 | 启动设备 |
| `stop` | 风机/水泵 | 停止设备 |
| `set_speed` | 风机 | 设置转速(0-100%) |
| `get_status` | 所有 | 查询设备状态 |
| `reset_fault` | 所有 | 重置故障状态 |

#### 状态反馈格式
```json
{
  "device_id": "fan_001",
  "type": "fan",
  "running": true,
  "speed": 75.0,
  "fault": false,
  "fault_code": null,
  "telemetry": {
    "current": 25.5,
    "voltage": 380.0,
    "temperature": 45.2
  },
  "last_update": "2024-01-01T00:00:00Z"
}
```

#### 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PLC_MQTT_BROKER` | `mqtt` | MQTT Broker地址 |
| `PLC_MQTT_PORT` | `1883` | MQTT端口 |
| `PLC_CONTROL_TOPIC` | `tunnel/control` | 控制指令主题 |
| `PLC_STATUS_TOPIC` | `tunnel/status` | 状态上报主题 |
| `PLC_TELEMETRY_TOPIC` | `tunnel/telemetry` | 遥测数据主题 |
| `PLC_NUM_FANS` | `30` | 风机数量 |
| `PLC_NUM_PUMPS` | `50` | 水泵数量 |
| `PLC_STATUS_INTERVAL` | `10` | 状态上报间隔(秒) |
| `PLC_TELEMETRY_INTERVAL` | `60` | 遥测数据间隔(秒) |
| `PLC_ENABLE_MQTT` | `true` | 启用MQTT |
| `PLC_ENABLE_HTTP_FALLBACK` | `true` | 启用HTTP fallback |

## 服务说明

### FastAPI服务
- **部署模式**: Gunicorn管理多个Uvicorn Worker进程
- **Worker数量**: 默认为4，可通过 `FASTAPI_WORKERS` 调整
- **健康检查**: `/health` 端点
- **API文档**: `/docs` (Swagger UI) 和 `/redoc` (ReDoc)

### MongoDB集群
- **副本集**: 3节点(1主2从)，自动故障转移
- **读偏好**: `nearest`，优先读取就近节点
- **写关注**: `majority`，确保数据一致性
- **分片策略**:
  - `sensor_data`: 按 `device_id` 哈希分片
  - `alarms`: 按 `timestamp` 范围分片
  - `devices`: 按 `chamber + type` 复合分片

### Redis
- **持久化**: AOF + RDB混合模式
- **内存限制**: 512MB，LRU淘汰策略
- **用途**: 模块间Pub/Sub通信、临时数据缓存

### Nginx
- **Gzip压缩**: 支持20+种文件类型，压缩级别6
- **静态资源缓存**:
  - JS/CSS/图片: 1年，immutable
  - HTML: 不缓存
- **API缓存**: 传感器数据等读多写少接口缓存1分钟
- **WebSocket代理**: 支持长连接，超时时间24小时

## 告警策略

| 告警级别 | 触发条件 | 通知方式 |
|----------|----------|----------|
| 一级(气体) | 甲烷≥1% 或 硫化氢≥10ppm | WebSocket推送 |
| 二级(窒息) | 氧气≤18% | WebSocket推送 + 短信通知 |
| 安防 | 井盖非法开启 | WebSocket推送 |

## 模块架构

### 后端模块
- `lora_receiver`: LoRa数据接收、校验、批量写入
- `ventilation_controller`: 模糊推理、风机控制
- `pump_controller`: 液位检测、水泵控制(滞后控制)
- `alarm_manager`: 告警分级、通知路由

### 前端组件
- `corridor_map.js`: 管廊地图(Canvas+Leaflet)
- `device_detail.js`: 设备详情面板、趋势图

## 性能优化

1. **批量写入**: 传感器数据批量插入，减少DB调用
2. **分舱推理**: 通风控制按舱室独立推理，控制规则空间从2^30降至2^10
3. **短信分级**: 仅二级告警发送短信，节省70-80%费用
4. **读写分离**: MongoDB副本集读分流
5. **数据分片**: 时序数据按时间分片，查询性能提升
6. **前端缓存**: 静态资源长期缓存，Gzip压缩减少传输体积

## 故障排查

### 服务无法启动
```bash
# 查看具体错误
docker compose logs <service-name>

# 检查端口占用
netstat -tlnp | grep -E ":(80|27017|6379|1883)"
```

### MongoDB副本集异常
```bash
# 检查副本集状态
docker compose exec mongo1 mongosh --eval "rs.status()"

# 重新初始化副本集
docker compose exec mongo1 mongosh /docker-entrypoint-initdb.d/replicaset-init.js
```

### 模拟器数据不上报
```bash
# 检查模拟器日志
docker compose logs lora-simulator
docker compose logs plc-simulator

# 检查MQTT连接
docker compose exec mqtt mosquitto_sub -t 'tunnel/#' -v
```

## 许可
MIT License
