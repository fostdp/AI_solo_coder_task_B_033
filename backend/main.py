import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from config.database import connect_to_mongo, close_mongo_connection
from utils.mqtt_client import mqtt_client
from utils.redis_client import redis_client
from controllers.alarm_manager import alarm_manager
from controllers.ventilation_control import ventilation_controller
from controllers.pump_control import pump_controller
from routes.api import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"正在启动 {settings.APP_NAME} v{settings.APP_VERSION}...")

    await connect_to_mongo()
    print("MongoDB连接成功")

    await redis_client.connect()
    print("Redis连接成功")

    await mqtt_client.connect()
    print("MQTT客户端已启动")

    await ventilation_controller.start_subscription()
    print("通风控制器已启动并订阅Redis")

    await pump_controller.start_subscription()
    print("排水泵控制器已启动并订阅Redis")

    await alarm_manager.start_subscription()
    print("告警管理器已启动并订阅Redis")

    asyncio.create_task(alarm_manager.cleanup_old_alarms())
    print("告警清理任务已启动")

    print("=" * 60)
    print(f"{settings.APP_NAME} 启动完成")
    print(f"版本: v{settings.APP_VERSION}")
    print(f"API文档: http://localhost:8000/docs")
    print("=" * 60)

    yield

    await mqtt_client.disconnect()
    print("MQTT客户端已断开")

    await redis_client.disconnect()
    print("Redis连接已关闭")

    await close_mongo_connection()
    print("MongoDB连接已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="地下管廊综合监控与智能运维系统API - 微服务架构版",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
