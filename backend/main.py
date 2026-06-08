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


@app.get("/")
async def root():
    return {
        "name": "地下管廊综合监控与智能运维系统",
        "version": "1.0.0",
        "description": "城市地下综合管廊智能监控系统",
        "tunnel_length": f"{settings.TUNNEL_LENGTH}公里",
        "chambers": ["电力舱", "水信舱", "燃气舱"],
        "devices": {
            "environment_sensors": settings.NUM_ENV_SENSORS,
            "manhole_sensors": settings.NUM_MANHOLE_SENSORS,
            "pumps": settings.NUM_PUMPS,
            "fans": settings.NUM_FANS
        },
        "api_endpoints": {
            "devices": "/api/devices",
            "sensor_data": "/api/sensor/data",
            "alerts": "/api/alerts",
            "control": "/api/control",
            "statistics": "/api/stats",
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
