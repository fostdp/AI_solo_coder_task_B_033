import asyncio
import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from backend.config import settings
from backend.models.database import (
    alerts_collection,
    devices_collection,
    serialize_document,
    serialize_documents
)
from backend.models.schemas import Alert, AlertLevel, SensorData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[Any] = []
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: Any):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: Any):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]):
        async with self._lock:
            connections = list(self.active_connections)
        
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")
                disconnected.append(connection)
        
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)


class AlertService:
    def __init__(self, websocket_manager: WebSocketManager):
        self.websocket_manager = websocket_manager
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_cooldown: Dict[str, datetime] = {}
        self.sms_sent: Dict[str, datetime] = {}
        self.cooldown_period = timedelta(minutes=5)
        self.sms_cooldown = timedelta(minutes=15)
    
    async def check_sensor_data(self, sensor_data: SensorData) -> List[Alert]:
        alerts = []
        device_id = sensor_data.device_id
        
        device = await devices_collection.find_one({"device_id": device_id})
        if not device:
            return alerts
        
        device = serialize_document(device)
        
        if sensor_data.methane is not None and sensor_data.methane >= settings.METHANE_ALARM:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.LEVEL1,
                alert_type="methane_high",
                message=f"甲烷浓度超标: {sensor_data.methane}%",
                value=sensor_data.methane,
                threshold=settings.METHANE_ALARM,
                device=device
            )
            if alert:
                alerts.append(alert)
        
        if sensor_data.h2s is not None and sensor_data.h2s >= settings.H2S_ALARM:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.LEVEL1,
                alert_type="h2s_high",
                message=f"硫化氢浓度超标: {sensor_data.h2s}ppm",
                value=sensor_data.h2s,
                threshold=settings.H2S_ALARM,
                device=device
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
                device=device
            )
            if alert:
                alerts.append(alert)
        
        if sensor_data.temperature is not None and sensor_data.temperature > settings.TEMPERATURE_MAX:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.LEVEL2,
                alert_type="temperature_high",
                message=f"温度过高: {sensor_data.temperature}°C",
                value=sensor_data.temperature,
                threshold=settings.TEMPERATURE_MAX,
                device=device
            )
            if alert:
                alerts.append(alert)
        
        if sensor_data.cover_open is not None and sensor_data.cover_open:
            alert = await self._create_alert(
                device_id=device_id,
                level=AlertLevel.SECURITY,
                alert_type="manhole_open",
                message=f"井盖非法开启",
                value=1.0,
                threshold=0.0,
                device=device
            )
            if alert:
                alerts.append(alert)
        
        for alert in alerts:
            await self._process_alert(alert)
        
        return alerts
    
    async def _create_alert(self, device_id: str, level: AlertLevel, alert_type: str,
                           message: str, value: float, threshold: float,
                           device: Dict[str, Any]) -> Optional[Alert]:
        alert_key = f"{device_id}_{alert_type}"
        
        if alert_key in self.alert_cooldown:
            cooldown_end = self.alert_cooldown[alert_key]
            if datetime.utcnow() < cooldown_end:
                return None
        
        alert = Alert(
            device_id=device_id,
            level=level,
            type=alert_type,
            message=message,
            value=value,
            threshold=threshold
        )
        
        self.alert_cooldown[alert_key] = datetime.utcnow() + self.cooldown_period
        self.active_alerts[alert_key] = alert
        
        return alert
    
    async def _process_alert(self, alert: Alert):
        alert_dict = alert.dict(by_alias=True, exclude_none=True)
        alert_dict["_id"] = str(alert_dict.get("_id", ""))
        
        await alerts_collection.insert_one(alert_dict)
        
        await self.websocket_manager.broadcast({
            "type": "alert",
            "data": alert_dict
        })
        
        await self._send_sms(alert)
    
    async def _send_sms(self, alert: Alert):
        alert_key = f"{alert.device_id}_{alert.type}"
        
        if alert_key in self.sms_sent:
            last_sent = self.sms_sent[alert_key]
            if datetime.utcnow() < last_sent + self.sms_cooldown:
                return
        
        level_names = {
            AlertLevel.LEVEL1: "一级气体告警",
            AlertLevel.LEVEL2: "二级窒息告警",
            AlertLevel.SECURITY: "安防告警"
        }
        
        sms_message = f"[{level_names.get(alert.level, '告警')}] {alert.message}"
        phone_numbers = ["13800138000", "13900139000"]
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    settings.SMS_API_URL,
                    json={
                        "message": sms_message,
                        "phones": phone_numbers,
                        "alert_id": str(alert.id)
                    }
                )
            self.sms_sent[alert_key] = datetime.utcnow()
            logger.info(f"SMS sent for alert: {alert.message}")
        except Exception as e:
            logger.warning(f"Failed to send SMS: {e} (simulated SMS sending)")
            self.sms_sent[alert_key] = datetime.utcnow()
    
    async def acknowledge_alert(self, alert_id: str, operator: str) -> Optional[Dict[str, Any]]:
        from bson import ObjectId
        result = await alerts_collection.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {"acknowledged": True, "acknowledged_by": operator,
                      "acknowledged_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            alert = await alerts_collection.find_one({"_id": ObjectId(alert_id)})
            if alert:
                alert = serialize_document(alert)
                await self.websocket_manager.broadcast({
                    "type": "alert_acknowledged",
                    "data": alert
                })
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


websocket_manager = WebSocketManager()
alert_service = AlertService(websocket_manager)
