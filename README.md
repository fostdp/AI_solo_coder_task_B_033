# 地下管廊综合监控与智能运维系统

## 系统架构

```
┌─────────────────┐     LoRa      ┌───────────────┐     HTTP      ┌──────────────┐
│ 环境传感器x200  │ ────────────► │ LoRa网关模拟器 │ ───────────► │              │
├─────────────────┤               └───────────────┘               │              │
│ 井盖传感器x100  │ ────────────┐                                 │  FastAPI     │
├─────────────────┤               └─────────────────────────────► │  后端服务     │
│  风机x30        │ ◄─────────── MQTT ◄─────────── PLC模拟器     │  (8000端口)   │
├─────────────────┤                                               │              │
│  排水泵x50      │ ◄─────────── MQTT ◄─────────── PLC模拟器     │              │
└─────────────────┘                                               └──────┬───────┘
                                                                         │
                                                                         │ WebSocket
                                                                         ▼
                                                               ┌───────────────┐
                                                               │  前端界面      │
                                                               │  (Leaflet地图) │
                                                               └───────────────┘
```

## 目录结构

```
AI_solo_coder_task_A_033/
├── backend/                 # Python FastAPI 后端
│   ├── main.py             # 主入口文件
│   ├── requirements.txt    # Python依赖
│   ├── .env.example        # 环境变量示例
│   ├── config/             # 配置模块
│   │   ├── settings.py     # 系统配置
│   │   └── database.py     # 数据库连接
│   ├── models/             # 数据模型
│   │   └── models.py       # Pydantic模型定义
│   ├── routes/             # API路由
│   │   └── api.py          # 所有API端点
│   ├── controllers/        # 控制逻辑
│   │   ├── ventilation_control.py  # 通风控制（模糊控制）
│   │   ├── pump_control.py         # 排水泵控制
│   │   ├── alarm_manager.py        # 告警管理
│   │   └── health_score.py         # 健康度评分
│   └── utils/              # 工具类
│       ├── mqtt_client.py  # MQTT客户端
│       └── websocket.py    # WebSocket管理
├── frontend/               # 前端应用
│   ├── index.html          # 主页面
│   ├── css/
│   │   └── style.css       # 样式文件
│   └── js/
│       ├── config.js       # 前端配置
│       ├── api.js          # API封装
│       ├── map.js          # Leaflet地图模块
│       ├── websocket.js    # WebSocket客户端
│       ├── charts.js       # Chart.js图表模块
│       └── app.js          # 主应用逻辑
├── scripts/                # 模拟器脚本
│   ├── lora_gateway_simulator.py   # LoRa网关模拟器
│   ├── mqtt_plc_simulator.py       # MQTT PLC模拟器
│   └── sms_simulator.py            # 短信服务模拟器
├── mongodb/                # MongoDB脚本
│   └── init.js             # 数据库初始化脚本
└── data/                   # 数据目录
```

## 功能特性

### 1. 设备监控
- **200个环境传感器**：监测温度、湿度、氧气、甲烷、硫化氢
- **100个井盖传感器**：监测井盖状态（开启/关闭、合法/非法）
- **30台风机**：智能通风控制，变频调速
- **50台排水泵**：自动排水控制，带延时保护

### 2. 智能控制模型
#### 通风控制（模糊控制算法）
- 输入：氧气浓度、温度、湿度
- 输出：风机启停、转速（0-100%）
- 目标：氧气19%-21%，温度≤35℃
- 模糊规则表：5×4×4=80条规则

#### 排水泵控制
- 启动液位：0.8m
- 停止液位：0.3m
- 延时关闭：30秒（避免频繁启停）

### 3. 告警系统
#### 一级气体告警（严重）
- 甲烷浓度 ≥ 1%
- 硫化氢 ≥ 10ppm

#### 二级窒息告警（严重）
- 氧气浓度 ≤ 18%

#### 安防告警（警告）
- 井盖非法开启

#### 告警推送
- WebSocket实时推送到前端弹窗
- 短信接口调用（模拟）
- 告警去重（30秒窗口）
- 短信限流（5分钟间隔）

### 4. 健康度评分
- 综合评分（0-100）
  - 环境监测：25%权重
  - 井盖状态：15%权重
  - 通风系统：25%权重
  - 排水系统：20%权重
  - 告警状态：15%权重
- 分舱室评分（电力舱、水信舱、燃气舱）
- 本月故障统计

### 5. 前端功能
- Leaflet地图展示管廊走向（15公里，3个舱室）
- GeoJSON加载设备坐标
- 设备状态图标颜色：绿=正常，黄=预警，红=故障，灰=离线
- 点击设备弹出详情面板
  - 近24小时环境参数趋势图（Chart.js）
  - 设备操作历史
  - 手动控制按钮
- 实时告警弹窗（带声音提醒）
- 管廊健康度仪表盘
- 图层过滤控制

## 快速启动

### 前置要求
- Python 3.9+
- MongoDB 4.0+
- Mosquitto (MQTT Broker) 或其他MQTT服务器
- Node.js (可选，用于启动前端静态服务器)

### 步骤1：启动MongoDB并初始化数据
```bash
# 启动MongoDB
mongod

# 初始化数据库（在mongodb目录下执行）
mongo < init.js
```

### 步骤2：启动MQTT Broker
```bash
# 使用Mosquitto
mosquitto -p 1883

# 或使用Docker
docker run -d -p 1883:1883 eclipse-mosquitto
```

### 步骤3：安装Python依赖
```bash
cd backend
pip install -r requirements.txt
copy .env.example .env
```

### 步骤4：启动所有服务（建议使用4个独立终端）

```bash
# 终端1：启动短信模拟器
cd scripts
python sms_simulator.py

# 终端2：启动后端API服务
cd backend
python main.py

# 终端3：启动MQTT PLC模拟器
cd scripts
python mqtt_plc_simulator.py

# 终端4：启动LoRa网关模拟器
cd scripts
python lora_gateway_simulator.py
```

### 步骤5：启动前端
```bash
# 方式1：使用Python内置HTTP服务器
cd frontend
python -m http.server 8080

# 方式2：使用Node.js的http-server
cd frontend
npx http-server -p 8080
```

### 访问系统
- 前端界面：http://localhost:8080
- API文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/

## API接口说明

### 数据上报接口
- `POST /api/data/lora` - 环境传感器数据上报
- `POST /api/data/manhole` - 井盖传感器数据上报
- `POST /api/data/pump` - 水泵数据上报

### 设备管理接口
- `GET /api/devices` - 获取设备列表（支持按类型/舱室/状态过滤）
- `GET /api/devices/{device_id}` - 获取设备详情
- `GET /api/devices/{device_id}/trend?hours=24` - 获取设备24小时趋势数据
- `GET /api/devices/{device_id}/history` - 获取设备操作历史
- `POST /api/devices/{device_id}/control` - 设备手动控制

### 告警接口
- `GET /api/alarms` - 获取告警列表
- `POST /api/alarms/{alarm_id}/acknowledge` - 确认告警

### 健康度接口
- `GET /api/health/score` - 获取管廊健康度评分
- `GET /api/health/fault-stats` - 获取本月故障统计

### GeoJSON接口
- `GET /api/geojson/devices` - 获取设备GeoJSON数据
- `GET /api/geojson/corridor` - 获取管廊走向GeoJSON

### WebSocket接口
- `ws://localhost:8000/api/ws` - 实时数据推送（告警、设备更新）

## 模拟器参数说明

### LoRa网关模拟器
- 上报间隔：60秒
- 环境传感器：200个（五参数）
- 井盖传感器：100个
- 异常模拟：
  - 甲烷峰值：2%概率，持续3-8个周期
  - 硫化氢峰值：2%概率，持续3-8个周期
  - 氧气下降：1.5%概率，持续5-12个周期
  - 井盖非法开启：0.3%概率

### MQTT PLC模拟器
- 遥测上报：5秒
- 状态上报：30秒
- 设备：30台风机 + 50台排水泵
- 控制命令主题：`fan/{id}/command`、`pump/{id}/command`
- 状态上报主题：`fan/{id}/status`、`pump/{id}/status`

## 技术栈

### 后端
- **FastAPI** - 高性能Web框架
- **Motor** - 异步MongoDB驱动
- **Paho MQTT** - MQTT客户端
- **Pydantic** - 数据验证
- **Uvicorn** - ASGI服务器

### 前端
- **Leaflet 1.9** - 交互式地图
- **Chart.js 4** - 图表可视化
- **原生JavaScript** - 无框架依赖
- **CSS3** - 响应式设计

### 数据库
- **MongoDB** - 时序数据存储
- 索引优化：设备ID+时间戳复合索引

## 配置参数

可在 `backend/.env` 中调整以下参数：

```ini
# 控制参数
OXYGEN_MIN=19.0          # 氧气下限
OXYGEN_MAX=21.0          # 氧气上限
TEMP_MAX=35.0            # 温度上限

# 告警阈值
METHANE_ALARM=1.0        # 甲烷告警阈值(%)
H2S_ALARM=10.0           # 硫化氢告警阈值(ppm)
OXYGEN_DANGER=18.0       # 氧气危险阈值(%)

# 水泵参数
PUMP_START_LEVEL=0.8     # 启泵液位(m)
PUMP_STOP_LEVEL=0.3      # 停泵液位(m)
PUMP_DELAY=30            # 停泵延时(s)
```

## 注意事项

1. 生产环境请替换模拟器为真实硬件接入
2. 短信接口需替换为实际的短信网关API
3. 建议使用MongoDB副本集提高数据可靠性
4. MQTT建议启用TLS加密和用户名认证
5. 生产环境前端需构建并使用Nginx部署
6. 定期备份MongoDB数据

## 故障排查

### 后端无法连接MongoDB
- 检查MongoDB是否启动
- 检查MONGODB_URL配置

### WebSocket连接失败
- 检查后端服务是否启动
- 检查防火墙是否允许8000端口

### 设备不显示在地图上
- 检查MongoDB是否正确初始化设备数据
- 检查浏览器控制台是否有错误

### 告警不触发
- 检查LoRa模拟器是否正常上报数据
- 检查告警阈值配置是否正确
