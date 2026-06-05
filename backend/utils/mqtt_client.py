import json
import asyncio
from datetime import datetime
from typing import Callable
import paho.mqtt.client as mqtt
from config.settings import settings
from config.database import get_collection
from models.models import FanData, PumpData
from utils.redis_client import redis_client, RedisChannels


class MQTTClient:
    def __init__(self):
        self.client = mqtt.Client()
        if settings.MQTT_USERNAME:
            self.client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        self.callbacks = {}
        self.connected = False

    def on_connect(self, client, userdata, flags, rc):
        print(f"MQTT连接成功，返回码: {rc}")
        self.connected = True
        client.subscribe("fan/+/status")
        client.subscribe("pump/+/status")
        client.subscribe("fan/+/telemetry")
        client.subscribe("pump/+/telemetry")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            parts = topic.split("/")
            device_type = parts[0]
            device_id = parts[1]
            msg_type = parts[2]

            asyncio.create_task(self._handle_message(device_type, device_id, msg_type, payload))

            if topic in self.callbacks:
                for callback in self.callbacks[topic]:
                    callback(payload)
        except Exception as e:
            print(f"MQTT消息处理错误: {e}")

    async def _handle_message(self, device_type, device_id, msg_type, payload):
        try:
            if device_type == "fan":
                data = FanData(
                    device_id=device_id,
                    cabin=payload.get("cabin", "power"),
                    is_running=payload.get("is_running", False),
                    speed=payload.get("speed", 0),
                    current=payload.get("current"),
                    vibration=payload.get("vibration")
                )
                await get_collection("fan_data").insert_one(data.dict())
                await get_collection("devices").update_one(
                    {"device_id": device_id},
                    {"$set": {"last_update": datetime.utcnow(), "status": data.is_running}}
                )
                await redis_client.publish(RedisChannels.FAN_DATA, {
                    "device_id": device_id,
                    "cabin": payload.get("cabin", "power"),
                    "is_running": payload.get("is_running", False),
                    "speed": payload.get("speed", 0),
                    "timestamp": datetime.utcnow().isoformat()
                })
            elif device_type == "pump":
                data = PumpData(
                    device_id=device_id,
                    cabin=payload.get("cabin", "water"),
                    is_running=payload.get("is_running", False),
                    level=payload.get("level", 0.0),
                    flow_rate=payload.get("flow_rate"),
                    current=payload.get("current")
                )
                await get_collection("pump_data").insert_one(data.dict())
                await get_collection("devices").update_one(
                    {"device_id": device_id},
                    {"$set": {"last_update": datetime.utcnow()}}
                )
                await redis_client.publish(RedisChannels.PUMP_DATA, {
                    "device_id": device_id,
                    "cabin": payload.get("cabin", "water"),
                    "is_running": payload.get("is_running", False),
                    "level": payload.get("level", 0.0),
                    "flow_rate": payload.get("flow_rate"),
                    "timestamp": datetime.utcnow().isoformat()
                })
        except Exception as e:
            print(f"存储MQTT数据错误: {e}")

    async def connect(self):
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect_async(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
        self.client.loop_start()

    async def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        self.connected = False

    def publish(self, topic: str, payload: dict):
        self.client.publish(topic, json.dumps(payload))

    def subscribe(self, topic: str, callback: Callable):
        if topic not in self.callbacks:
            self.callbacks[topic] = []
        self.callbacks[topic].append(callback)
        self.client.subscribe(topic)

    def send_fan_command(self, device_id: str, command: str, speed: int = 0):
        topic = f"fan/{device_id}/command"
        payload = {
            "command": command,
            "speed": speed,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.publish(topic, payload)

    def send_pump_command(self, device_id: str, command: str):
        topic = f"pump/{device_id}/command"
        payload = {
            "command": command,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.publish(topic, payload)


mqtt_client = MQTTClient()
