import asyncio
import json
import logging
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from bson import ObjectId

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from backend.config import settings
from backend.models.schemas import Alert, AlertLevel, SensorData
from backend.models.database import (
    alerts_collection,
    devices_collection,
    serialize_document,
    serialize_documents
)
from backend.services.alert_service import websocket_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALERT_NOTIFICATION_STRATEGY = {
    "level1": {"websocket": True, "sms": False},
    "level2": {"websocket": True, "sms": True},
    "security": {"websocket": True, "sms": False}
}

ALERT_COOLDOWN_MINUTES = 5
SMS_COOLDOWN_MINUTES = 15
SMS_PHONE_NUMBERS = ["13800138000", "13900139000"]

LEVEL_NAMES = {
    AlertLevel.LEVEL1: "一级气体告警",
    AlertLevel.LEVEL2: "二级窒息告警",
    AlertLevel.SECURITY: "安防告警"
}


class AlarmManager:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.running = False
        self.alert_cooldown: Dict[str, datetime] = {}
        self.sms_cooldown: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def start(self):
        if not REDIS_AVAILABLE:
            logger.error("Redis not available, cannot start AlarmManager")
            return

        await self._connect_redis()
        self.running = True
        await self._subscribe()
        logger.info("AlarmManager started successfully")

    async def stop(self):
        self.running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
        if self.redis_client:
            await self.redis_client.close()
        logger.info("AlarmManager stopped")

    async def _connect_redis(self):
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("AlarmManager connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def _subscribe(self):
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(**{
            settings.REDIS_CHANNEL_SENSOR_DATA: self._handle_sensor_data
        })

        asyncio.create_task(self._listen())
        logger.info(f"Subscribed to channel: {settings.REDIS_CHANNEL_SENSOR_DATA}")

    async def _listen(self):
        while self.running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                if message:
                    asyncio.create_task(self._handle_sensor_data(message))
            except Exception as e:
                logger.error(f"Error listening to Redis messages: {e}")
                await asyncio.sleep(1.0)

    async def _handle_sensor_data(self, message: Dict[str, Any]):
        try:
            if message["type"] != "message":
                return

            data = json.loads(message["data"])
            sensor_data = self._parse_sensor_data(data)
            await self.process_sensor_data(sensor_data, data)
        except Exception as e:
            logger.error(f"Error handling sensor data: {e}")

    def _parse_sensor_data(self, data: Dict[str, Any]) -> SensorData:
        sensor_values = data.get("data", {})
        return SensorData(
            device_id=data.get("device_id", ""),
            type=data.get("type"),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
            temperature=sensor_values.get("temperature"),
            humidity=sensor_values.get("humidity"),
            oxygen=sensor_values.get("oxygen"),
            methane=sensor_values.get("methane"),
            h2s=sensor_values.get("h2s"),
            level=sensor_values.get("level"),
            cover_open=sensor_values.get("cover_open"),
            running=sensor_values.get("running"),
            speed=sensor_values.get("speed")
        )

    async def process_sensor_data(self, sensor_data: SensorData, raw_data: Dict[str, Any] = None) -> List[Alert]:
        alerts = []
        device_id = sensor_data.device_id

        device = await devices_collection.find_one({"device_id": device_id})
        if not device:
            logger.warning(f"Device {device_id} not found in database")
            return alerts

        device = serialize_document(device)

        if sensor_data.methane is not None and sensor_data.methane > settings.METHANE_ALARM:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.LEVEL1,
                alert_type="methane_high",
                message=f"甲烷浓度超标: {sensor_data.methane}%",
                value=sensor_data.methane,
                threshold=settings.METHANE_ALARM,
                device=device,
                raw_data=raw_data
            )
            if alert:
                alerts.append(alert)

        if sensor_data.h2s is not None and sensor_data.h2s > settings.H2S_ALARM:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.LEVEL1,
                alert_type="h2s_high",
                message=f"硫化氢浓度超标: {sensor_data.h2s}ppm",
                value=sensor_data.h2s,
                threshold=settings.H2S_ALARM,
                device=device,
                raw_data=raw_data
            )
            if alert:
                alerts.append(alert)

        if sensor_data.oxygen is not None and sensor_data.oxygen < settings.OXYGEN_ALARM_LOW:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.LEVEL2,
                alert_type="oxygen_low",
                message=f"氧气浓度过低: {sensor_data.oxygen}%",
                value=sensor_data.oxygen,
                threshold=settings.OXYGEN_ALARM_LOW,
                device=device,
                raw_data=raw_data
            )
            if alert:
                alerts.append(alert)

        if sensor_data.cover_open is not None and sensor_data.cover_open:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.SECURITY,
                alert_type="manhole_open",
                message="井盖非法开启",
                value=1.0,
                threshold=0.0,
                device=device,
                raw_data=raw_data
            )
            if alert:
                alerts.append(alert)

        for alert in alerts:
            await self._process_alert(alert, device, raw_data)

        return alerts

    async def _create_alert(self, device_id: str, level: AlertLevel, alert_type: str,
                            message: str, value: float, threshold: float,
                            device: Dict[str, Any], raw_data: Dict[str, Any] = None) -> Optional[Alert]:
        alert_key = f"{device_id}_{alert_type}"

        async with self._lock:
            if alert_key in self.alert_cooldown:
                if datetime.utcnow() < self.alert_cooldown[alert_key]:
                    return None

            alert = Alert(
                device_id=device_id,
                level=level,
                type=alert_type,
                message=message,
                value=value,
                threshold=threshold
            )

            self.alert_cooldown[alert_key] = datetime.utcnow() + timedelta(minutes=ALERT_COOLDOWN_MINUTES)

        return alert

    async def _process_alert(self, alert: Alert, device: Dict[str, Any], raw_data: Dict[str, Any] = None):
        alert_dict = alert.dict(by_alias=True, exclude_none=True)

        result = await alerts_collection.insert_one(alert_dict)
        alert.id = result.inserted_id
        alert_dict["_id"] = str(alert.id)

        strategy = ALERT_NOTIFICATION_STRATEGY.get(alert.level, {"websocket": True, "sms": False})

        if strategy.get("websocket"):
            await self._send_websocket_alert(alert_dict)

        if strategy.get("sms"):
            await self._send_sms_alert(alert)

        await self._publish_alarm_event(alert_dict, device, raw_data)
        await self._update_device_status(device, alert)

        logger.info(f"Alert generated: [{LEVEL_NAMES.get(alert.level)}] {alert.message}")

    async def _send_websocket_alert(self, alert_dict: Dict[str, Any]):
        await websocket_manager.broadcast({
            "type": "alert",
            "data": alert_dict
        })

    async def _send_sms_alert(self, alert: Alert):
        alert_key = f"{alert.device_id}_{alert.alert_type}"

        async with self._lock:
            if alert_key in self.sms_cooldown:
                if datetime.utcnow() < self.sms_cooldown[alert_key]:
                    logger.info(f"SMS skipped for {alert_key} (in cooldown)")
                    return

            self.sms_cooldown[alert_key] = datetime.utcnow() + timedelta(minutes=SMS_COOLDOWN_MINUTES)

        sms_message = f"[{LEVEL_NAMES.get(alert.level, '告警')}] {alert.message}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    settings.SMS_API_URL,
                    json={
                        "message": sms_message,
                        "phones": SMS_PHONE_NUMBERS,
                        "alert_id": str(alert.id)
                    }
                )
            logger.info(f"SMS sent for alert: {alert.message}")
        except Exception as e:
            logger.warning(f"Failed to send SMS: {e} (simulated SMS sending)")

    async def _publish_alarm_event(self, alert_dict: Dict[str, Any], device: Dict[str, Any], raw_data: Dict[str, Any] = None):
        if not self.redis_client:
            return

        event = {
            "alert_id": alert_dict["_id"],
            "device_id": alert_dict["device_id"],
            "level": alert_dict["level"],
            "type": alert_dict["type"],
            "message": alert_dict["message"],
            "value": alert_dict["value"],
            "threshold": alert_dict["threshold"],
            "timestamp": alert_dict["timestamp"],
            "device_info": {
                "chamber": device.get("chamber"),
                "type": device.get("type"),
                "name": device.get("name"),
                "location": device.get("location")
            },
            "raw_data": raw_data
        }

        try:
            await self.redis_client.publish(
                settings.REDIS_CHANNEL_ALARM_EVENT,
                json.dumps(event, default=str)
            )
        except Exception as e:
            logger.error(f"Failed to publish alarm event: {e}")

    async def _update_device_status(self, device: Dict[str, Any], alert: Alert):
        if not self.redis_client:
            return

        status_update = {
            "device_id": device["device_id"],
            "status": "warning",
            "alert_level": alert.level,
            "alert_type": alert.alert_type,
            "timestamp": datetime.utcnow().isoformat(),
            "device_info": {
                "chamber": device.get("chamber"),
                "type": device.get("type"),
                "name": device.get("name")
            }
        }

        try:
            await self.redis_client.publish(
                settings.REDIS_CHANNEL_DEVICE_STATUS,
                json.dumps(status_update, default=str)
            )
        except Exception as e:
            logger.error(f"Failed to publish device status: {e}")

    async def acknowledge_alert(self, alert_id: str, operator: str) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(alert_id)
        except Exception:
            logger.error(f"Invalid alert ID: {alert_id}")
            return None

        result = await alerts_collection.update_one(
            {"_id": object_id},
            {"$set": {
                "acknowledged": True,
                "acknowledged_by": operator,
                "acknowledged_at": datetime.utcnow()
            }}
        )

        if result.modified_count > 0:
            alert = await alerts_collection.find_one({"_id": object_id})
            if alert:
                alert = serialize_document(alert)
                await websocket_manager.broadcast({
                    "type": "alert_acknowledged",
                    "data": alert
                })
                logger.info(f"Alert {alert_id} acknowledged by {operator}")
                return alert

        return None

    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        cursor = alerts_collection.find({
            "acknowledged": False,
            "timestamp": {"$gte": datetime.utcnow() - timedelta(hours=24)}
        }).sort("timestamp", -1)

        alerts = await cursor.to_list(length=100)
        return serialize_documents(alerts)

    async def get_alert_history(self, start_time: datetime, end_time: datetime,
                                level: Optional[AlertLevel] = None) -> List[Dict[str, Any]]:
        query = {"timestamp": {"$gte": start_time, "$lte": end_time}}
        if level:
            query["level"] = level

        cursor = alerts_collection.find(query).sort("timestamp", -1)
        alerts = await cursor.to_list(length=1000)
        return serialize_documents(alerts)

    def get_cooldown_status(self) -> Dict[str, Any]:
        now = datetime.utcnow()
        return {
            "alert_cooldowns": {
                k: (v - now).total_seconds()
                for k, v in self.alert_cooldown.items()
                if v > now
            },
            "sms_cooldowns": {
                k: (v - now).total_seconds()
                for k, v in self.sms_cooldown.items()
                if v > now
            }
        }
    
    async def connect_redis(self):
        await self._connect_redis()
    
    async def disconnect_redis(self):
        if self.pubsub:
            await self.pubsub.unsubscribe()
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            self.pubsub = None
    
    async def start_listener(self):
        await self.start()
    
    async def stop_listener(self):
        await self.stop()


alarm_manager = AlarmManager()
