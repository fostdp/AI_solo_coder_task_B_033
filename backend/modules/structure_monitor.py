import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import redis.asyncio as redis
import json

from backend.config import settings
from backend.models.database import (
    fiber_sensor_data_collection,
    structure_alerts_collection,
    devices_collection
)
from backend.models.schemas import (
    FiberSensorData,
    StructureHeatmapPoint,
    StructureAlert,
    Location
)

logger = logging.getLogger(__name__)


class StructureMonitor:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.alert_cooldowns: Dict[str, datetime] = {}
        self.running = False

    async def connect_redis(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB
        )
        logger.info("Structure Monitor connected to Redis")

    async def disconnect_redis(self):
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Structure Monitor disconnected from Redis")

    def _calculate_risk_level(self, strain: float, crack_width: Optional[float]) -> str:
        if strain >= settings.STRUCTURE_STRAIN_ALARM or \
           (crack_width is not None and crack_width >= settings.STRUCTURE_CRACK_ALARM):
            return "critical"
        elif strain >= settings.STRUCTURE_STRAIN_WARNING or \
             (crack_width is not None and crack_width >= settings.STRUCTURE_CRACK_WARNING):
            return "warning"
        elif strain >= settings.STRUCTURE_STRAIN_WARNING * 0.7:
            return "attention"
        else:
            return "normal"

    async def process_fiber_data(self, data: FiberSensorData) -> Dict[str, Any]:
        device_info = await devices_collection.find_one({"device_id": data.device_id})
        if not device_info:
            return {"status": "error", "message": f"Device {data.device_id} not found"}

        strain = data.strain
        crack_width = data.crack_width
        risk_level = self._calculate_risk_level(strain, crack_width)

        doc = data.model_dump()
        doc["risk_level"] = risk_level
        await fiber_sensor_data_collection.insert_one(doc)

        await devices_collection.update_one(
            {"device_id": data.device_id},
            {"$set": {
                "properties.last_strain": strain,
                "properties.last_fiber_temp": data.fiber_temperature,
                "properties.last_crack_width": crack_width,
                "properties.risk_level": risk_level,
                "properties.last_reading": datetime.utcnow()
            }}
        )

        alert_result = None
        if risk_level in ["warning", "critical"]:
            alert_result = await self._check_and_create_alert(
                data.device_id, data.distance_km, strain, crack_width, risk_level
            )

        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:structure:update",
                json.dumps({
                    "device_id": data.device_id,
                    "distance_km": data.distance_km,
                    "strain": strain,
                    "fiber_temperature": data.fiber_temperature,
                    "crack_width": crack_width,
                    "risk_level": risk_level,
                    "location": data.location.model_dump(),
                    "timestamp": datetime.utcnow().isoformat()
                })
            )

        return {
            "status": "success",
            "risk_level": risk_level,
            "alert": alert_result,
            "data": doc
        }

    async def _check_and_create_alert(
        self,
        device_id: str,
        distance_km: float,
        strain: float,
        crack_width: Optional[float],
        risk_level: str
    ) -> Optional[Dict[str, Any]]:
        cooldown_key = f"structure:{device_id}"
        now = datetime.utcnow()

        if cooldown_key in self.alert_cooldowns:
            if now - self.alert_cooldowns[cooldown_key] < timedelta(minutes=10):
                return None

        threshold = settings.STRUCTURE_STRAIN_ALARM if risk_level == "critical" else settings.STRUCTURE_STRAIN_WARNING

        if risk_level == "critical":
            message = f"结构风险危急！管廊{distance_km:.1f}公里处应变{strain:.1f}με，超过阈值{threshold}με"
            if crack_width is not None:
                message += f"，裂缝宽度{crack_width:.2f}mm"
        else:
            message = f"结构风险预警：管廊{distance_km:.1f}公里处应变{strain:.1f}με，接近阈值{threshold}με"

        alert = StructureAlert(
            device_id=device_id,
            distance_km=distance_km,
            strain=strain,
            threshold=threshold,
            crack_width=crack_width,
            risk_level=risk_level,
            message=message
        )

        result = await structure_alerts_collection.insert_one(alert.model_dump(exclude={"id"}))

        self.alert_cooldowns[cooldown_key] = now

        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:alarm:structural",
                json.dumps({
                    "alert_id": str(result.inserted_id),
                    "device_id": device_id,
                    "distance_km": distance_km,
                    "strain": strain,
                    "risk_level": risk_level,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                })
            )

        return {"alert_id": str(result.inserted_id), "message": message}

    async def get_heatmap_data(self, chamber: Optional[str] = None) -> List[StructureHeatmapPoint]:
        query = {}
        if chamber:
            device_ids = await devices_collection.distinct(
                "device_id", {"type": "fiber_sensor", "chamber": chamber}
            )
            query["device_id"] = {"$in": device_ids}

        latest_data = await fiber_sensor_data_collection.aggregate([
            {"$match": query},
            {"$sort": {"timestamp": -1}},
            {"$group": {
                "_id": "$device_id",
                "latest_data": {"$first": "$$ROOT"}
            }}
        ]).to_list(length=settings.NUM_FIBER_SENSORS)

        heatmap_points = []
        for item in latest_data:
            data = item["latest_data"]
            risk_level = self._calculate_risk_level(
                data.get("strain", 0),
                data.get("crack_width")
            )

            device = await devices_collection.find_one({"device_id": data["device_id"]})
            location = device.get("location") if device else data.get("location")

            if location:
                heatmap_points.append(StructureHeatmapPoint(
                    distance_km=data.get("distance_km", 0),
                    strain=data.get("strain", 0),
                    fiber_temperature=data.get("fiber_temperature", 0),
                    risk_level=risk_level,
                    location=Location(**location) if isinstance(location, dict) else location
                ))

        heatmap_points.sort(key=lambda x: x.distance_km)
        return heatmap_points

    async def get_active_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        alerts = await structure_alerts_collection.find(
            {"acknowledged": False}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

        from backend.models.database import serialize_documents
        return serialize_documents(alerts)

    async def acknowledge_alert(self, alert_id: str) -> bool:
        from bson import ObjectId
        result = await structure_alerts_collection.update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {"acknowledged": True}}
        )
        return result.modified_count > 0

    async def get_structure_trend(self, distance_km_start: float, distance_km_end: float,
                                  hours: int = 24) -> List[Dict[str, Any]]:
        start_time = datetime.utcnow() - timedelta(hours=hours)

        device_ids = await devices_collection.distinct(
            "device_id",
            {
                "type": "fiber_sensor",
                "distance_km": {"$gte": distance_km_start, "$lte": distance_km_end}
            }
        )

        data = await fiber_sensor_data_collection.find({
            "device_id": {"$in": device_ids},
            "timestamp": {"$gte": start_time}
        }).sort("timestamp", 1).to_list(length=10000)

        from backend.models.database import serialize_documents
        return serialize_documents(data)

    async def start_listener(self):
        self.running = True
        logger.info("Structure Monitor listener started")

        while self.running:
            try:
                if not self.redis_client:
                    await self.connect_redis()

                pubsub = self.redis_client.pubsub()
                await pubsub.subscribe("tunnel:sensor:fiber")

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            fiber_data = FiberSensorData(**data)
                            await self.process_fiber_data(fiber_data)
                        except Exception as e:
                            logger.error(f"Error processing fiber data: {e}")

            except Exception as e:
                logger.error(f"Structure Monitor listener error: {e}")
                await asyncio.sleep(5)

        logger.info("Structure Monitor listener stopped")


structure_monitor = StructureMonitor()
