import json
import asyncio
from typing import Dict, Callable, Optional, Any
from datetime import datetime
from redis import asyncio as aioredis
from config.settings import settings


class RedisMessage:
    def __init__(self, channel: str, data: dict, timestamp: Optional[datetime] = None):
        self.channel = channel
        self.data = data
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "data": self.data,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, msg_dict: dict) -> "RedisMessage":
        return cls(
            channel=msg_dict["channel"],
            data=msg_dict["data"],
            timestamp=datetime.fromisoformat(msg_dict["timestamp"])
        )


class RedisClient:
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.pubsub: Optional[aioredis.PubSub] = None
        self.subscribers: Dict[str, Callable] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._connected: bool = False

    async def connect(self):
        try:
            self.redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            await self.redis.ping()
            self.pubsub = self.redis.pubsub()
            self._connected = True
            print(f"[Redis] 连接成功: {settings.REDIS_URL}")
        except Exception as e:
            print(f"[Redis] 连接失败: {e}")
            self._connected = False

    async def disconnect(self):
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()
        self._connected = False
        print("[Redis] 连接已关闭")

    async def publish(self, channel: str, data: dict):
        if not self._connected or not self.redis:
            return False
        try:
            message = RedisMessage(channel=channel, data=data)
            await self.redis.publish(channel, json.dumps(message.to_dict()))
            return True
        except Exception as e:
            print(f"[Redis] 发布消息失败 (channel={channel}): {e}")
            return False

    async def subscribe(self, channel: str, callback: Callable[[dict], Any]):
        if not self._connected or not self.pubsub:
            return False
        try:
            self.subscribers[channel] = callback
            await self.pubsub.subscribe(channel)
            print(f"[Redis] 订阅频道: {channel}")

            if not self._listener_task or self._listener_task.done():
                self._listener_task = asyncio.create_task(self._listen_loop())

            return True
        except Exception as e:
            print(f"[Redis] 订阅失败 (channel={channel}): {e}")
            return False

    async def unsubscribe(self, channel: str):
        if not self._connected or not self.pubsub:
            return
        try:
            await self.pubsub.unsubscribe(channel)
            if channel in self.subscribers:
                del self.subscribers[channel]
            print(f"[Redis] 取消订阅: {channel}")
        except Exception as e:
            print(f"[Redis] 取消订阅失败: {e}")

    async def _listen_loop(self):
        if not self.pubsub:
            return
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    try:
                        msg_data = json.loads(message["data"])
                        callback = self.subscribers.get(channel)
                        if callback:
                            if asyncio.iscoroutinefunction(callback):
                                asyncio.create_task(callback(msg_data["data"]))
                            else:
                                callback(msg_data["data"])
                    except Exception as e:
                        print(f"[Redis] 处理消息失败 (channel={channel}): {e}")
        except asyncio.CancelledError:
            print("[Redis] 监听器任务已取消")
        except Exception as e:
            print(f"[Redis] 监听循环异常: {e}")

    async def set(self, key: str, value: str, expire: Optional[int] = None):
        if not self._connected or not self.redis:
            return False
        try:
            await self.redis.set(key, value, ex=expire)
            return True
        except Exception as e:
            print(f"[Redis] SET失败: {e}")
            return False

    async def get(self, key: str) -> Optional[str]:
        if not self._connected or not self.redis:
            return None
        try:
            return await self.redis.get(key)
        except Exception as e:
            print(f"[Redis] GET失败: {e}")
            return None

    async def delete(self, key: str):
        if not self._connected or not self.redis:
            return False
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            print(f"[Redis] DELETE失败: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected


redis_client = RedisClient()


class RedisChannels:
    ENV_DATA = "env_data"
    MANHOLE_DATA = "manhole_data"
    PUMP_DATA = "pump_data"
    FAN_DATA = "fan_data"
    ALARM = "alarm"
    DEVICE_UPDATE = "device_update"
    FAN_CONTROL = "fan_control"
    PUMP_CONTROL = "pump_control"
