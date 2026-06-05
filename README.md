# 地下管廊综合监控与智能运维系统 v3.0

基于Docker容器化部署的地下综合管廊全栈监控系统，支持200+传感器实时数据采集、智能通风控制、自动排水、多级告警推送。

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                        用户浏览器                                     │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ 管廊地图    │  │ 设备详情面板    │  │ 告警弹窗     │  │ 健康度仪表盘       │ │
│  │ (Leaflet)   │  │ (Chart.js)      │  │ (WebSocket)  │  │ (实时统计)         │ │
│  └──────┬──────┘  └────────┬─────────┘  └──────┬───────┘  └──────────┬───────────┘ │
└─────────┼───────────────────┼───────────────────┼───────────────────────┼───────────────┘
          │                   │                   │                       │
          │ HTTP/WebSocket    │                   │                       │
┌─────────▼───────────────────▼───────────────────▼───────────────────────▼───────────────┐
│                                        Nginx (8080)                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Gzip压缩 | 静态资源缓存(30天) | API代理 | WebSocket代理                         │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┬──────────────────────────────────────┘
                                                     │
                        ┌────────────────────────────┴────────────────────────────┐
                        │                        FastAPI (8000)                    │
                        │  ┌───────────────────────────────────────────────────────┐ │
                        │  │ gunicorn + uvicorn workers (4进程)                    │ │
                        │  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │ │
                        │  │  │ lora_receiver│  │ventilation_  │  │pump_        │ │ │
                        │  │  │ (数据接收)   │  │controller    │  │controller   │ │ │
                        │  │  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │ │
                        │  └─────────┼──────────────────┼───────────────────┼────────┘ │
                        │            │ Redis Pub/Sub    │                   │          │
                        │     ┌──────▼──────────────────▼───────────────────▼──────┐   │
                        │     │                 Redis (6379)                        │   │
                        │     │  数据总线 | 缓存 | 消息队列                        │   │
                        │     └──────────────────────────────────────────────────────┘   │
                        └────────────────────────────────────────────────────────────────┘
                             │                          │                          │
                             │ MQTT                     │ MongoDB                  │ HTTP
                             ▼                          ▼                          ▼
                    ┌─────────────────┐       ┌───────────────────┐      ┌──────────────────┐
                    │  MQTT Broker    │       │  MongoDB Cluster  │      │  SMS Simulator   │
                    │  (Mosquitto)    │       │  (副本集+分片)    │      │  (端口8001)      │
                    │  1883 / 9001    │       │  27017-27020      │      └──────────────────┘
                    └──────┬──────────┘       └─────────┬─────────┘
                           │                            │
                           │ MQTT 控制指令              │ 时序数据存储
                           ▼                            ▼
                    ┌─────────────────┐       ┌───────────────────┐
                    │  PLC Simulator  │       │  mongo1 (Primary)  │
                    │  30风机 + 50水泵│       │  mongo2 (Secondary)│
                    │  (风机/水泵状态)│       │  mongo3 (Secondary)│
                    └─────────────────┘       │  mongos (Router)   │
                                               │  mongocfg1 (Config)│
                                               └───────────────────┘
                             ▲
                             │ HTTP
                    ┌─────────────────┐
                    │ LoRa Simulator  │
                    │ 200传感器+100井盖│
                    │ (1分钟上报)     │
                    └─────────────────┘
```

### 模块间通信架构

```
LoRa模拟器 ──► lora_receiver ──► ENV_DATA ──┬──► ventilation_controller ──► FAN_CONTROL ──► PLC
                                             ├──► pump_controller        ──► PUMP_CONTROL ──► PLC
                                             └──► alarm_manager         ──► ALARM        ──► WebSocket + SMS

                           Redis Pub/Sub 8个通道:
                           ENV_DATA, MANHOLE_DATA, PUMP_DATA, FAN_DATA,
                           FAN_CONTROL, PUMP_CONTROL, ALARM, DEVICE_UPDATE
```

---

## 快速启动

### 前置要求

- Docker 20.10+
- Docker Compose v2.0+
- 至少4核CPU / 8GB内存 / 20GB磁盘空间

### 一键部署

```bash
# 1. 克隆项目并进入目录
cd AI_solo_coder_task_A_033

# 2. 复制环境变量配置
copy .env.example .env

# 3. 构建并启动所有服务（首次构建可能需要5-10分钟）
docker-compose up -d --build

# 4. 查看服务状态
docker-compose ps

# 5. 查看日志
docker-compose logs -f backend
docker-compose logs -f lora-simulator
docker-compose logs -f plc-simulator
```

### 访问系统

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端界面 | http://localhost:8080 | 主监控界面 |
| API文档 | http://localhost:8000/docs | Swagger交互式文档 |
| 健康检查 | http://localhost:8000/api/health | 后端健康状态 |
| MongoDB | mongodb://localhost:27020 | 连接mongos路由 |
| Redis | redis://localhost:6379 | 缓存和消息队列 |
| MQTT | tcp://localhost:1883 | MQTT Broker |
| MQTT WebSocket | ws://localhost:9001 | MQTT WebSocket |
| 短信模拟器 | http://localhost:8001 | 模拟短信网关 |

### 常用操作

```bash
# 停止所有服务
docker-compose down

# 停止并清除数据（谨慎使用）
docker-compose down -v

# 查看服务状态
docker-compose ps

# 查看实时日志
docker-compose logs -f [服务名]

# 重启某个服务
docker-compose restart backend

# 进入容器
docker-compose exec backend bash
docker-compose exec mongos mongosh --port 27020

# 查看资源使用
docker stats
```

---

## Docker Compose 服务说明

| 服务名 | 镜像 | 端口 | 说明 |
|--------|------|------|------|
| **mongo1/2/3** | mongo:7.0 | 27017/27018/27019 | MongoDB三节点副本集 |
| **mongocfg1** | mongo:7.0 | - | 分片配置服务器 |
| **mongos** | mongo:7.0 | 27020 | 分片路由服务器 |
| **mongo-init** | mongo:7.0 | - | 一次性初始化容器 |
| **redis** | redis:7.2-alpine | 6379 | Redis缓存和Pub/Sub |
| **mqtt-broker** | eclipse-mosquitto:2.0.18 | 1883, 9001 | MQTT消息代理 |
| **backend** | 自定义(Dockerfile.backend) | 8000 | FastAPI后端服务 |
| **frontend** | 自定义(Dockerfile.frontend) | 8080 | Nginx前端服务器 |
| **lora-simulator** | 自定义(Dockerfile.simulator) | - | LoRa网关模拟器 |
| **plc-simulator** | 自定义(Dockerfile.simulator) | - | PLC设备模拟器 |
| **sms-simulator** | 自定义(Dockerfile.simulator) | 8001 | 短信网关模拟器 |

### 网络与存储

- **网络**: `pipe-corridor-network` (172.28.0.0/16)
- **数据卷**: 自动创建命名卷存储MongoDB、Redis、MQTT数据

---

## 模拟器配置说明

### LoRa网关模拟器

**作用**: 模拟200个环境传感器和100个井盖传感器，每1分钟通过HTTP上报数据。

#### 配置参数（环境变量）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LORA_SENSOR_COUNT` | 200 | 环境传感器数量 |
| `LORA_MANHOLE_COUNT` | 100 | 井盖传感器数量 |
| `LORA_INTERVAL` | 60 | 上报间隔（秒） |
| `LORA_BATCH_SIZE` | 50 | 批量上报大小 |
| `LORA_USE_BATCH` | true | 是否启用批量上报 |
| `LORA_API_URL` | http://backend:8000/api | 后端API地址 |

#### 气体浓度范围配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LORA_OXYGEN_MIN` / `LORA_OXYGEN_MAX` | 19.5 / 21.0 | 氧气浓度正常范围(%) |
| `LORA_OXYGEN_DROP_MIN` / `LORA_OXYGEN_DROP_MAX` | 1.5 / 3.0 | 氧气下降幅度(%) |
| `LORA_METHANE_MIN` / `LORA_METHANE_MAX` | 0.0 / 0.1 | 甲烷正常范围(%) |
| `LORA_METHANE_ALARM_MIN` / `LORA_METHANE_ALARM_MAX` | 0.8 / 2.5 | 甲烷告警峰值(%) |
| `LORA_H2S_MIN` / `LORA_H2S_MAX` | 0.0 / 5.0 | 硫化氢正常范围(ppm) |
| `LORA_H2S_ALARM_MIN` / `LORA_H2S_ALARM_MAX` | 8.0 / 25.0 | 硫化氢告警峰值(ppm) |
| `LORA_TEMP_MIN` / `LORA_TEMP_MAX` | 22.0 / 28.0 | 温度范围(°C) |
| `LORA_HUMIDITY_MIN` / `LORA_HUMIDITY_MAX` | 45.0 / 65.0 | 湿度范围(%) |

#### 异常模拟概率

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LORA_METHANE_PEAK_PROB` | 0.02 | 甲烷峰值概率(2%) |
| `LORA_H2S_PEAK_PROB` | 0.02 | 硫化氢峰值概率(2%) |
| `LORA_OXYGEN_DROP_PROB` | 0.015 | 氧气下降概率(1.5%) |
| `LORA_PEAK_DURATION_MIN`/`MAX` | 3 / 8 | 峰值持续周期 |
| `LORA_DROP_DURATION_MIN`/`MAX` | 5 / 12 | 氧气下降持续周期 |
| `LORA_MANHOLE_OPEN_PROB` | 0.01 | 井盖开启概率(1%) |
| `LORA_ILLEGAL_OPEN_PROB` | 0.3 | 非法开启概率(30%) |

#### 使用示例

```bash
# 打印当前配置
docker-compose run --rm lora-simulator python scripts/lora_gateway_simulator.py --print-config

# 自定义参数运行（测试100个传感器，30秒间隔）
LORA_SENSOR_COUNT=100 LORA_INTERVAL=30 docker-compose up -d lora-simulator

# 调整气体浓度范围模拟高风险场景
LORA_METHANE_MAX=0.5 LORA_H2S_MAX=15.0 docker-compose up -d lora-simulator
```

### PLC设备模拟器

**作用**: 模拟30台风机和50台排水泵，接收MQTT控制指令并反馈设备状态。

#### 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PLC_FAN_COUNT` | 30 | 风机数量 |
| `PLC_PUMP_COUNT` | 50 | 水泵数量 |
| `PLC_TELEMETRY_INTERVAL` | 5 | 遥测数据上报间隔(秒) |
| `PLC_STATUS_INTERVAL` | 30 | 状态上报间隔(秒) |
| `PLC_LEVEL_CHANGE_PROB` | 0.05 | 液位变化概率 |
| `PLC_LEVEL_UP_MAX` | 0.005 | 液位最大上升幅度 |
| `PLC_LEVEL_DOWN_MAX` | 0.003 | 液位最大下降幅度 |
| `PLC_PUMP_RATE` | 0.002 | 水泵排水速率(m/s) |

#### MQTT Topic 规范

**订阅的命令Topic**:
```
fan/{device_id}/command      # 单台风机控制
pump/{device_id}/command     # 单台水泵控制
plc/broadcast/#              # 广播命令
```

**发布的状态Topic**:
```
fan/{device_id}/status       # 风机状态（30秒间隔+命令响应）
fan/{device_id}/telemetry    # 风机遥测（5秒间隔）
fan/{device_id}/response     # 风机命令响应
pump/{device_id}/status      # 水泵状态
pump/{device_id}/telemetry   # 水泵遥测
pump/{device_id}/response    # 水泵命令响应
```

#### 控制命令格式

```json
// 单台控制
{
  "command": "start",      // start, stop, set_speed, status, reset
  "speed": 75              // 转速 0-100（可选）
}

// 广播控制
{
  "command": "start_all",  // start_all, stop_all, status_all, emergency_stop
  "device_type": "fan",    // fan, pump（可选，为空则控制所有）
  "speed": 50
}
```

#### 状态响应格式

```json
// 风机状态
{
  "device_id": "FAN-001",
  "cabin": "power",
  "is_running": true,
  "speed": 75,
  "target_speed": 75,
  "current": 8.5,
  "vibration": 3.2,
  "running_hours": 1256.5,
  "status": "running",
  "timestamp": "2024-01-15T10:30:00.000Z"
}

// 水泵状态
{
  "device_id": "PUMP-001",
  "cabin": "water",
  "is_running": true,
  "level": 0.75,
  "flow_rate": 52.3,
  "current": 8.2,
  "running_hours": 892.3,
  "status": "running",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

#### 使用示例

```bash
# 打印配置
docker-compose run --rm plc-simulator python scripts/mqtt_plc_simulator.py --print-config

# 测试MQTT命令（需要安装mosquitto客户端）
mosquitto_pub -h localhost -t "fan/FAN-001/command" -m '{"command":"start","speed":75}'
mosquitto_pub -h localhost -t "plc/broadcast/stop_all" -m '{"command":"stop_all","device_type":"pump"}'

# 监听状态
mosquitto_sub -h localhost -t "fan/+/status" -v
mosquitto_sub -h localhost -t "pump/+/telemetry" -v
```

---

## MongoDB 集群配置

### 副本集架构

```
                             ┌─────────────────┐
                             │   mongos (Router)│
                             │   port: 27020    │
                             └────────┬────────┘
                                      │
                                      │ 查询/写入路由
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼────────┐   ┌──────────▼──────────┐   ┌────────▼─────────┐
    │  mongo1 (Primary)│   │  mongo2 (Secondary)  │   │ mongo3 (Secondary)│
    │  port: 27017      │   │  port: 27018        │   │ port: 27019       │
    │  priority: 2      │   │  priority: 1        │   │ priority: 1       │
    │  (优先选举主节点) │   │  (只读副本)         │   │ (只读副本)        │
    └─────────┬─────────┘   └──────────┬──────────┘   └────────┬─────────┘
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      │
                                      ▼
                          数据同步（异步复制）
```

### 分片配置

- **配置服务器**: mongocfg1:27019 (副本集cfg0)
- **分片集群**: rs0 (mongo1-3组成)
- **分片键**: `{ device_id: 1, timestamp: 1 }`
- **分片集合**: environment_data, manhole_data, alarms, operation_history

### 自动清理（TTL索引）

| 集合 | 保留时间 | 说明 |
|------|----------|------|
| environment_data | 30天 | 环境传感器数据 |
| manhole_data | 30天 | 井盖状态数据 |
| alarms | 90天 | 告警记录 |

### 索引优化

```javascript
// 设备ID+时间戳复合索引（提高查询效率）
db.environment_data.createIndex({ device_id: 1, timestamp: -1 })
db.environment_data.createIndex({ cabin: 1, timestamp: -1 })

// TTL索引（自动过期）
db.environment_data.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000 })

// 告警索引
db.alarms.createIndex({ status: 1, level: 1, timestamp: -1 })
```

### 连接MongoDB

```bash
# 连接mongos路由
docker-compose exec mongos mongosh --port 27020

# 连接主节点
docker-compose exec mongo1 mongosh --port 27017

# 查看副本集状态
rs.status()

# 查看分片状态
sh.status()

# 查看数据库
use pipe_corridor
show collections
db.devices.count()
db.environment_data.find().sort({timestamp: -1}).limit(5)
```

---

## 前端性能优化

### Nginx Gzip 压缩

**压缩类型**:
- 文本文件: html, css, js, xml, json
- 字体文件: svg, ttf, woff
- 压缩级别: 6
- 最小压缩: 1KB

### 缓存策略

| 资源类型 | 缓存时间 | 策略 |
|----------|----------|------|
| CSS/JS/图片/字体 | 30天 | public, immutable |
| JSON数据 | 1小时 | public, max-age=3600 |
| HTML页面 | 不缓存 | no-store, no-cache |

### 配置验证

```bash
# 测试Gzip压缩
curl -I -H "Accept-Encoding: gzip" http://localhost:8080/css/style.css
# 响应头应包含: Content-Encoding: gzip

# 测试缓存
curl -I http://localhost:8080/js/app.js
# 响应头应包含: Cache-Control: public, immutable
```

---

## 后端配置

### Gunicorn 多Worker模式

```python
# backend/gunicorn.conf.py
workers = CPU * 2 + 1  # 默认4核→9个worker
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000     # 自动重启防止内存泄漏
max_requests_jitter = 100
timeout = 120
keepalive = 5
```

### 环境变量

```bash
# Gunicorn配置
GUNICORN_WORKERS=4
GUNICORN_TIMEOUT=120
GUNICORN_MAX_REQUESTS=1000
GUNICORN_LOGLEVEL=info

# 业务配置
OXYGEN_MIN=19.0
OXYGEN_MAX=21.0
TEMP_MAX=35.0
METHANE_ALARM=1.0
H2S_ALARM=10.0
OXYGEN_DANGER=18.0
PUMP_START_LEVEL=0.8
PUMP_STOP_LEVEL=0.3
PUMP_DELAY=30
```

---

## 部署架构建议

### 开发环境

```
单台机器 (Docker Desktop)
├── 所有服务运行在一个Compose堆栈
├── MongoDB单副本集3节点
└── 适合开发、测试、演示
```

### 生产环境建议

```
Docker Swarm / Kubernetes
├── 后端: 多副本部署 + 负载均衡
├── MongoDB: 跨可用区部署副本集
├── Redis: 主从复制 + 哨兵模式
├── MQTT Broker: 集群模式
├── 监控: Prometheus + Grafana
└── 日志: ELK Stack
```

### 安全加固建议

1. **MongoDB**: 启用认证、TLS加密、IP白名单
2. **Redis**: 设置密码、禁用危险命令
3. **MQTT**: 启用用户名认证、TLS 1.3加密
4. **API**: JWT认证、速率限制、CORS配置
5. **前端**: HTTPS、CSP、XSS防护

---

## 目录结构

```
AI_solo_coder_task_A_033/
├── backend/                    # FastAPI后端
│   ├── main.py                # 入口文件
│   ├── requirements.txt       # Python依赖
│   ├── gunicorn.conf.py       # Gunicorn配置
│   ├── config/                # 配置模块
│   │   ├── settings.py
│   │   └── fuzzy_logic.yaml   # 模糊控制配置
│   ├── models/                # 数据模型
│   ├── routes/                # API路由
│   ├── controllers/           # 控制逻辑
│   │   ├── ventilation_control.py
│   │   ├── pump_control.py
│   │   └── alarm_manager.py
│   ├── services/              # 服务模块
│   │   └── lora_receiver.py
│   └── utils/                 # 工具类
│       ├── redis_client.py
│       ├── mqtt_client.py
│       └── websocket.py
├── frontend/                   # 前端应用
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── corridor_map.js    # 地图组件
│       ├── device_detail.js   # 设备详情组件
│       ├── app.js             # 主应用
│       └── ...
├── scripts/                    # 模拟器脚本
│   ├── lora_gateway_simulator.py
│   ├── mqtt_plc_simulator.py
│   └── sms_simulator.py
├── mongodb/                    # MongoDB脚本
│   └── init.js                # 数据库初始化
├── docker/                     # Docker配置
│   ├── nginx.conf             # Nginx配置
│   ├── nginx-gzip.conf        # Gzip配置
│   ├── mosquitto.conf         # MQTT配置
│   └── mongo-init.sh          # MongoDB初始化脚本
├── Dockerfile.backend         # 后端Dockerfile
├── Dockerfile.frontend        # 前端Dockerfile
├── Dockerfile.simulator       # 模拟器Dockerfile
├── docker-compose.yml         # 服务编排
├── .env.example               # 环境变量模板
└── README.md                  # 本文件
```

---

## 故障排查

### 服务无法启动

```bash
# 查看具体错误
docker-compose logs backend
docker-compose logs mongos

# 检查端口占用
netstat -ano | findstr :8000
netstat -ano | findstr :8080
netstat -ano | findstr :27020

# 检查磁盘空间
docker system df
```

### MongoDB副本集异常

```bash
# 进入主节点检查状态
docker-compose exec mongo1 mongosh --port 27017
rs.status()

# 如果副本集未初始化，手动执行
rs.initiate({
    _id: "rs0",
    members: [
        { _id: 0, host: "mongo1:27017", priority: 2 },
        { _id: 1, host: "mongo2:27018" },
        { _id: 2, host: "mongo3:27019" }
    ]
})
```

### 模拟器无数据上报

```bash
# 检查模拟器日志
docker-compose logs lora-simulator
docker-compose logs plc-simulator

# 检查后端是否健康
curl http://localhost:8000/api/health

# 检查Redis连接
docker-compose exec redis redis-cli ping
```

### 设备不显示在地图上

1. 检查MongoDB是否有设备数据
2. 检查前端控制台是否有JS错误
3. 确认GeoJSON数据正确加载

---

## 性能指标参考

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 后端API响应 | <100ms | P95延迟 |
| 控制指令延迟 | <3s | 从传感器数据到MQTT指令 |
| 数据写入吞吐 | >500条/秒 | MongoDB写入 |
| 前端页面加载 | <2s | 首屏时间 |
| Gzip压缩率 | 60-80% | 静态资源 |
| 缓存命中率 | >90% | 静态资源 |

---

## 技术栈

### 后端
- **FastAPI** 0.115+ - 高性能Web框架
- **Gunicorn** + **Uvicorn** - ASGI服务器
- **Motor** 3.5+ - 异步MongoDB驱动
- **Paho MQTT** - MQTT客户端
- **aioredis** - 异步Redis客户端
- **PyYAML** - YAML配置解析

### 前端
- **Leaflet** 1.9 - 交互式地图
- **Chart.js** 4 - 图表可视化
- **原生JavaScript** - 无框架依赖
- **Nginx** - 静态服务器

### 基础设施
- **MongoDB** 7.0 - 副本集 + 分片
- **Redis** 7.2 - 缓存 + Pub/Sub
- **Eclipse Mosquitto** 2.0 - MQTT Broker
- **Docker** + **Docker Compose** - 容器编排

---

## 版本历史

- **v3.0** - 工程化重构：Docker容器化、MongoDB副本集+分片、Nginx Gzip+缓存、模拟器可配置化
- **v2.0** - 模块化重构：拆分为4个服务模块，Redis Pub/Sub通信，YAML配置
- **v1.0** - 初始版本：单体架构，基础功能实现

---

## License

MIT License
