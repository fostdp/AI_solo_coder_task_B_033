import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from config.database import connect_to_mongo, close_mongo_connection
from utils.mqtt_client import mqtt_client
from controllers.alarm_manager import alarm_manager
from routes.api import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"正在启动 {settings.APP_NAME} v{settings.APP_VERSION}...")
    await connect_to_mongo()
    print("MongoDB连接成功")
    await mqtt_client.connect()
    print("MQTT客户端已启动")
    asyncio.create_task(alarm_manager.cleanup_old_alarms())
    print("告警管理器已启动")
    yield
    await mqtt_client.disconnect()
    print("MQTT客户端已断开")
    await close_mongo_connection()
    print("MongoDB连接已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="地下管廊综合监控与智能运维系统API",
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
