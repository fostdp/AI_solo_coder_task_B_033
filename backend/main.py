import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.config import settings
from backend.services.mqtt_service import mqtt_service
from backend.services.control_service import control_service
from backend.services.alert_service import websocket_manager
from backend.modules import (
    lora_receiver,
    ventilation_controller,
    pump_controller_module,
    alarm_manager
)
from structural_monitor.core import structure_monitor
from structural_monitor.api import router as structure_router
from robot_planner.core import robot_planner
from robot_planner.api import router as robots_router
from robot_planner.path_process import (
    start_path_planner_process,
    stop_path_planner_process
)
from fire_early_warning.core import fire_early_warning
from fire_early_warning.api import router as fire_router
from fire_early_warning.inference_service import (
    start_inference_service,
    stop_inference_service
)
from asset_manager.core import asset_manager
from asset_manager.api import router as assets_router
from backend.routes import devices, sensor, alerts, control, stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting underground utility tunnel monitoring system...")
    
    await mqtt_service.connect()
    
    await lora_receiver.connect_redis()
    await ventilation_controller.connect_redis()
    await pump_controller_module.connect_redis()
    await alarm_manager.connect_redis()
    await structure_monitor.connect_redis()
    await robot_planner.connect_redis()
    await fire_early_warning.connect_redis()
    await asset_manager.connect_redis()
    
    logger.info("Starting robot path planner process...")
    try:
        process_started = start_path_planner_process()
        if process_started:
            logger.info("Robot path planner process started successfully")
        else:
            logger.warning("Robot path planner process failed to start")
    except Exception as e:
        logger.error(f"Error starting robot path planner process: {e}")
    
    logger.info("Starting fire inference service...")
    try:
        service_started = start_inference_service()
        if service_started:
            logger.info("Fire inference service started successfully")
        else:
            logger.warning("Fire inference service failed to start")
    except Exception as e:
        logger.error(f"Error starting fire inference service: {e}")
    
    redis_listener_task = asyncio.create_task(lora_receiver.start_redis_listener())
    ventilation_task = asyncio.create_task(ventilation_controller.start_control_loop())
    pump_task = asyncio.create_task(pump_controller_module.start_control_loop())
    alarm_task = asyncio.create_task(alarm_manager.start_listener())
    structure_task = asyncio.create_task(structure_monitor.start_listener())
    robot_task = asyncio.create_task(robot_planner.start_control_loop())
    fire_task = asyncio.create_task(fire_early_warning.start_listener())
    life_prediction_task = asyncio.create_task(asset_manager.start_life_prediction_service())
    maintenance_plan_task = asyncio.create_task(asset_manager.start_monthly_plan_generator())
    replacement_scan_task = asyncio.create_task(asset_manager.start_replacement_scan_service())
    
    async def periodic_health_check():
        while True:
            try:
                await control_service.calculate_health_score()
            except Exception as e:
                logger.error(f"Error in health check: {e}")
            await asyncio.sleep(300)
    
    async def broadcast_device_updates():
        while True:
            try:
                from backend.models.database import devices_collection
                from backend.models.schemas import DeviceStatus
                
                stats = await devices_collection.aggregate([
                    {"$group": {
                        "_id": {"type": "$type", "status": "$status"},
                        "count": {"$sum": 1}
                    }}
                ]).to_list(length=100)
                
                summary = {}
                for item in stats:
                    t = item["_id"]["type"]
                    s = item["_id"]["status"]
                    if t not in summary:
                        summary[t] = {"total": 0, "normal": 0, "warning": 0, "fault": 0}
                    summary[t]["total"] += item["count"]
                    if s in summary[t]:
                        summary[t][s] += item["count"]
                
                running_fans = await devices_collection.count_documents({
                    "type": "fan", "properties.running": True
                })
                running_pumps = await devices_collection.count_documents({
                    "type": "pump", "properties.running": True
                })
                
                await websocket_manager.broadcast({
                    "type": "device_status",
                    "data": {
                        "by_type": summary,
                        "equipment": {
                            "fans_running": running_fans,
                            "pumps_running": running_pumps
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    }
                })
            except Exception as e:
                logger.error(f"Error broadcasting device updates: {e}")
            await asyncio.sleep(5)
    
    health_task = asyncio.create_task(periodic_health_check())
    broadcast_task = asyncio.create_task(broadcast_device_updates())
    
    logger.info("System started successfully")
    
    yield
    
    logger.info("Shutting down...")
    health_task.cancel()
    broadcast_task.cancel()
    redis_listener_task.cancel()
    ventilation_task.cancel()
    pump_task.cancel()
    alarm_task.cancel()
    structure_task.cancel()
    robot_task.cancel()
    fire_task.cancel()
    life_prediction_task.cancel()
    maintenance_plan_task.cancel()
    replacement_scan_task.cancel()
    
    logger.info("Stopping robot path planner process...")
    try:
        stop_path_planner_process()
        logger.info("Robot path planner process stopped")
    except Exception as e:
        logger.error(f"Error stopping robot path planner process: {e}")
    
    logger.info("Stopping fire inference service...")
    try:
        stop_inference_service()
        logger.info("Fire inference service stopped")
    except Exception as e:
        logger.error(f"Error stopping fire inference service: {e}")
    
    await lora_receiver.disconnect_redis()
    await ventilation_controller.disconnect_redis()
    await pump_controller_module.disconnect_redis()
    await alarm_manager.disconnect_redis()
    await structure_monitor.disconnect_redis()
    await robot_planner.disconnect_redis()
    await fire_early_warning.disconnect_redis()
    await asset_manager.disconnect_redis()
    await mqtt_service.disconnect()
    logger.info("System shutdown complete")


app = FastAPI(
    title="地下管廊综合监控与智能运维系统",
    description="城市地下综合管廊全长15公里，包含电力舱、水信舱、燃气舱三个舱室的智能监控系统",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

app.include_router(devices.router)
app.include_router(sensor.router)
app.include_router(alerts.router)
app.include_router(control.router)
app.include_router(stats.router)
app.include_router(structure_router)
app.include_router(robots_router)
app.include_router(fire_router)
app.include_router(assets_router)


@app.get("/")
async def root():
    return {
        "name": "地下管廊综合监控与智能运维系统",
        "version": "2.0.0",
        "description": "城市地下综合管廊智能监控系统 - 包含结构健康监测、机器人巡检、火灾预警、资产管理四大新功能",
        "tunnel_length": f"{settings.TUNNEL_LENGTH}公里",
        "chambers": ["电力舱", "水信舱", "燃气舱", "综合"],
        "devices": {
            "environment_sensors": settings.NUM_ENV_SENSORS,
            "manhole_sensors": settings.NUM_MANHOLE_SENSORS,
            "pumps": settings.NUM_PUMPS,
            "fans": settings.NUM_FANS,
            "fiber_sensors": settings.NUM_FIBER_SENSORS,
            "smoke_sensors": settings.NUM_SMOKE_SENSORS,
            "inspection_robots": settings.NUM_INSPECTION_ROBOTS,
            "fire_doors": settings.NUM_FIRE_DOORS,
            "fire_extinguishers": settings.NUM_FIRE_EXTINGUISHERS
        },
        "new_features": [
            "结构健康监测 - 分布式光纤应变/温度监测，布里渊散射原理",
            "机器人巡检 - 智能路径规划，自动避开危险区域",
            "火灾早期预警 - 贝叶斯网络推理，自动联动防火分区",
            "资产管理 - 剩余寿命预测，月度维修计划自动生成"
        ],
        "api_endpoints": {
            "devices": "/api/devices",
            "sensor_data": "/api/sensor/data",
            "alerts": "/api/alerts",
            "control": "/api/control",
            "statistics": "/api/stats",
            "structure_monitoring": "/api/structure",
            "robot_inspection": "/api/robots",
            "fire_detection": "/api/fire",
            "asset_management": "/api/assets",
            "websocket": "/api/alerts/ws"
        },
        "docs": "/docs"
    }


@app.get("/api/health")
async def health_check():
    mqtt_connected = mqtt_service.connected
    
    try:
        from backend.models.database import client
        await client.admin.command("ping")
        mongo_connected = True
    except Exception:
        mongo_connected = False
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "mqtt": mqtt_connected,
            "mongodb": mongo_connected,
            "websocket_connections": len(websocket_manager.active_connections)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
