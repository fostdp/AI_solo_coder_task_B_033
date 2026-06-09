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
        self.fiber_data_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self.fiber_break_status: Dict[str, Dict[str, Any]] = {}
        self.last_data_timestamp: Dict[str, datetime] = {}

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

    def _detect_fiber_break(self, device_id: str, strain: float, distance_km: float) -> Dict[str, Any]:
        if device_id not in self.fiber_data_buffer:
            self.fiber_data_buffer[device_id] = []
        
        self.fiber_data_buffer[device_id].append({
            "strain": strain,
            "distance_km": distance_km,
            "timestamp": datetime.utcnow()
        })
        
        if len(self.fiber_data_buffer[device_id]) > settings.FIBER_BREAK_DETECTION_WINDOW * 2:
            self.fiber_data_buffer[device_id] = self.fiber_data_buffer[device_id][-settings.FIBER_BREAK_DETECTION_WINDOW * 2:]
        
        buffer = self.fiber_data_buffer[device_id]
        if len(buffer) < settings.FIBER_BREAK_DETECTION_WINDOW:
            return {"is_break": False}
        
        recent_data = buffer[-settings.FIBER_BREAK_DETECTION_WINDOW:]
        
        break_count = sum(1 for d in recent_data if d["strain"] <= settings.FIBER_BREAK_STRAIN_THRESHOLD)
        if break_count >= settings.FIBER_BREAK_DETECTION_WINDOW:
            previous_data = buffer[:-settings.FIBER_BREAK_DETECTION_WINDOW]
            if previous_data:
                avg_prev_strain = sum(d["strain"] for d in previous_data) / len(previous_data)
                strain_drop = avg_prev_strain - strain
                if strain_drop > abs(settings.FIBER_BREAK_STRAIN_THRESHOLD):
                    return {
                        "is_break": True,
                        "break_position": distance_km,
                        "strain_drop": strain_drop,
                        "severity": "critical"
                    }
        
        return {"is_break": False}

    def _check_data_interruption(self, device_id: str) -> Dict[str, Any]:
        now = datetime.utcnow()
        last_ts = self.last_data_timestamp.get(device_id)
        
        if last_ts:
            time_since_last = (now - last_ts).total_seconds()
            if time_since_last > settings.FIBER_DATA_TIMEOUT_SECONDS:
                return {
                    "is_interrupted": True,
                    "interruption_duration": time_since_last,
                    "last_timestamp": last_ts.isoformat()
                }
        
        self.last_data_timestamp[device_id] = now
        return {"is_interrupted": False}

    def _interpolate_missing_data(
        self,
        known_points: List[Dict[str, Any]],
        target_distance: float
    ) -> Optional[Dict[str, Any]]:
        if len(known_points) < 2:
            return None
        
        sorted_points = sorted(known_points, key=lambda p: p["distance_km"])
        
        for i in range(len(sorted_points) - 1):
            p1 = sorted_points[i]
            p2 = sorted_points[i + 1]
            
            if p1["distance_km"] <= target_distance <= p2["distance_km"]:
                gap = p2["distance_km"] - p1["distance_km"]
                if gap > settings.FIBER_INTERPOLATION_MAX_GAP:
                    return None
                
                ratio = (target_distance - p1["distance_km"]) / gap if gap > 0 else 0
                
                interpolated_strain = p1["strain"] + ratio * (p2["strain"] - p1["strain"])
                interpolated_temp = p1["fiber_temperature"] + ratio * (p2["fiber_temperature"] - p1["fiber_temperature"])
                interpolated_crack = None
                if p1.get("crack_width") is not None and p2.get("crack_width") is not None:
                    interpolated_crack = p1["crack_width"] + ratio * (p2["crack_width"] - p1["crack_width"])
                
                return {
                    "distance_km": target_distance,
                    "strain": interpolated_strain,
                    "fiber_temperature": interpolated_temp,
                    "crack_width": interpolated_crack,
                    "is_interpolated": True,
                    "interpolation_gap": gap,
                    "confidence": 1.0 - ratio * 0.1
                }
        
        return None

    async def _interpolate_heatmap_gaps(
        self,
        heatmap_points: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if len(heatmap_points) < 2:
            return heatmap_points
        
        sorted_points = sorted(heatmap_points, key=lambda p: p["distance_km"])
        interpolated_result = []
        
        for i in range(len(sorted_points) - 1):
            p1 = sorted_points[i]
            p2 = sorted_points[i + 1]
            
            interpolated_result.append(p1)
            
            gap = p2["distance_km"] - p1["distance_km"]
            if gap > 0.1 and gap <= settings.FIBER_INTERPOLATION_MAX_GAP:
                num_interpolations = int(gap / 0.1)
                for j in range(1, num_interpolations):
                    target_distance = p1["distance_km"] + j * 0.1
                    interpolated = self._interpolate_missing_data(
                        [p1, p2],
                        target_distance
                    )
                    if interpolated:
                        interpolated["risk_level"] = self._calculate_risk_level(
                            interpolated["strain"],
                            interpolated.get("crack_width")
                        )
                        interpolated_result.append(interpolated)
        
        if sorted_points:
            interpolated_result.append(sorted_points[-1])
        
        return interpolated_result

    async def process_fiber_data(self, data: FiberSensorData) -> Dict[str, Any]:
        device_info = await devices_collection.find_one({"device_id": data.device_id})
        if not device_info:
            return {"status": "error", "message": f"Device {data.device_id} not found"}

        strain = data.strain
        crack_width = data.crack_width
        distance_km = data.distance_km
        device_id = data.device_id

        interruption_info = self._check_data_interruption(device_id)
        break_info = self._detect_fiber_break(device_id, strain, distance_km)

        if break_info.get("is_break"):
            self.fiber_break_status[device_id] = {
                **break_info,
                "detected_at": datetime.utcnow(),
                "acknowledged": False
            }
            logger.warning(f"Fiber break detected at {distance_km:.2f}km on {device_id}")

        risk_level = self._calculate_risk_level(strain, crack_width)

        doc = data.dict()
        doc["risk_level"] = risk_level
        doc["is_interrupted"] = interruption_info.get("is_interrupted", False)
        doc["interruption_info"] = interruption_info
        doc["is_fiber_break"] = break_info.get("is_break", False)
        doc["fiber_break_info"] = break_info
        await fiber_sensor_data_collection.insert_one(doc)

        update_data = {
            "properties.last_strain": strain,
            "properties.last_fiber_temp": data.fiber_temperature,
            "properties.last_crack_width": crack_width,
            "properties.risk_level": risk_level,
            "properties.last_reading": datetime.utcnow(),
            "properties.is_fiber_broken": break_info.get("is_break", False),
            "properties.data_interrupted": interruption_info.get("is_interrupted", False)
        }
        if break_info.get("is_break"):
            update_data["properties.fiber_break_position"] = break_info.get("break_position")

        await devices_collection.update_one(
            {"device_id": device_id},
            {"$set": update_data}
        )

        alert_result = None
        if break_info.get("is_break"):
            alert_result = await self._check_and_create_alert(
                device_id, distance_km, strain, crack_width, "critical"
            )
            alert_result["alert_type"] = "fiber_break"
        elif risk_level in ["warning", "critical"]:
            alert_result = await self._check_and_create_alert(
                device_id, distance_km, strain, crack_width, risk_level
            )

        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:structure:update",
                json.dumps({
                    "device_id": device_id,
                    "distance_km": distance_km,
                    "strain": strain,
                    "fiber_temperature": data.fiber_temperature,
                    "crack_width": crack_width,
                    "risk_level": risk_level,
                    "location": data.location.dict(),
                    "is_fiber_break": break_info.get("is_break", False),
                    "fiber_break_info": break_info,
                    "is_interrupted": interruption_info.get("is_interrupted", False),
                    "timestamp": datetime.utcnow().isoformat()
                })
            )

        return {
            "status": "success",
            "risk_level": risk_level,
            "alert": alert_result,
            "data": doc,
            "fiber_break_info": break_info,
            "interruption_info": interruption_info
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

    async def get_heatmap_data(self, chamber: Optional[str] = None, enable_interpolation: bool = True) -> List[Dict[str, Any]]:
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
        raw_points = []
        for item in latest_data:
            data = item["latest_data"]
            risk_level = self._calculate_risk_level(
                data.get("strain", 0),
                data.get("crack_width")
            )

            device = await devices_collection.find_one({"device_id": data["device_id"]})
            location = device.get("location") if device else data.get("location")

            point_data = {
                "distance_km": data.get("distance_km", 0),
                "strain": data.get("strain", 0),
                "fiber_temperature": data.get("fiber_temperature", 0),
                "crack_width": data.get("crack_width"),
                "risk_level": risk_level,
                "location": location,
                "device_id": data["device_id"],
                "is_interpolated": False,
                "is_fiber_broken": data.get("is_fiber_break", False)
            }
            raw_points.append(point_data)

            if location:
                heatmap_points.append(StructureHeatmapPoint(
                    distance_km=data.get("distance_km", 0),
                    strain=data.get("strain", 0),
                    fiber_temperature=data.get("fiber_temperature", 0),
                    risk_level=risk_level,
                    location=Location(**location) if isinstance(location, dict) else location
                ))

        if enable_interpolation and len(raw_points) >= 2:
            interpolated_points = await self._interpolate_heatmap_gaps(raw_points)
            
            result_points = []
            for p in interpolated_points:
                if p.get("is_interpolated"):
                    result_points.append(p)
                else:
                    loc = p.get("location")
                    if loc:
                        result_points.append(StructureHeatmapPoint(
                            distance_km=p["distance_km"],
                            strain=p["strain"],
                            fiber_temperature=p["fiber_temperature"],
                            risk_level=p["risk_level"],
                            location=Location(**loc) if isinstance(loc, dict) else loc
                        ))
            return result_points

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
