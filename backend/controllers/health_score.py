from datetime import datetime, timedelta
from typing import Dict, Tuple
from config.database import get_collection
from models.models import DeviceStatus, AlarmLevel, CabinType


class HealthScoreCalculator:
    def __init__(self):
        self.weights = {
            "env_sensors": 0.25,
            "manholes": 0.15,
            "fans": 0.25,
            "pumps": 0.20,
            "alarms": 0.15
        }

    async def calculate_overall_score(self) -> Tuple[float, Dict]:
        scores = {}

        scores["env_sensors"] = await self._calculate_env_sensor_score()
        scores["manholes"] = await self._calculate_manhole_score()
        scores["fans"] = await self._calculate_fan_score()
        scores["pumps"] = await self._calculate_pump_score()
        scores["alarms"] = await self._calculate_alarm_score()

        overall_score = sum(
            scores[key] * self.weights[key]
            for key in self.weights
        )

        return round(overall_score, 1), scores

    async def _calculate_env_sensor_score(self) -> float:
        collection = get_collection("devices")
        total = await collection.count_documents({"type": "env_sensor"})
        if total == 0:
            return 100.0

        normal = await collection.count_documents({
            "type": "env_sensor",
            "status": DeviceStatus.NORMAL
        })

        online = await collection.count_documents({
            "type": "env_sensor",
            "status": {"$ne": DeviceStatus.OFFLINE}
        })

        availability_score = (online / total) * 40
        health_score = (normal / max(1, online)) * 60

        return round(availability_score + health_score, 1)

    async def _calculate_manhole_score(self) -> float:
        collection = get_collection("devices")
        total = await collection.count_documents({"type": "manhole"})
        if total == 0:
            return 100.0

        normal = await collection.count_documents({
            "type": "manhole",
            "status": DeviceStatus.NORMAL
        })

        return round((normal / total) * 100, 1)

    async def _calculate_fan_score(self) -> float:
        collection = get_collection("devices")
        total = await collection.count_documents({"type": "fan"})
        if total == 0:
            return 100.0

        normal = await collection.count_documents({
            "type": "fan",
            "status": DeviceStatus.NORMAL
        })

        warning = await collection.count_documents({
            "type": "fan",
            "status": DeviceStatus.WARNING
        })

        fault = await collection.count_documents({
            "type": "fan",
            "status": DeviceStatus.FAULT
        })

        score = (normal / total) * 100
        score -= (warning / total) * 30
        score -= (fault / total) * 60

        return round(max(0, score), 1)

    async def _calculate_pump_score(self) -> float:
        collection = get_collection("devices")
        total = await collection.count_documents({"type": "pump"})
        if total == 0:
            return 100.0

        normal = await collection.count_documents({
            "type": "pump",
            "status": DeviceStatus.NORMAL
        })

        fault = await collection.count_documents({
            "type": "pump",
            "status": DeviceStatus.FAULT
        })

        score = (normal / total) * 100
        score -= (fault / total) * 70

        return round(max(0, score), 1)

    async def _calculate_alarm_score(self) -> float:
        collection = get_collection("alarms")
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)

        critical = await collection.count_documents({
            "level": AlarmLevel.CRITICAL,
            "timestamp": {"$gte": yesterday},
            "acknowledged": False
        })

        warning = await collection.count_documents({
            "level": AlarmLevel.WARNING,
            "timestamp": {"$gte": yesterday},
            "acknowledged": False
        })

        score = 100.0
        score -= critical * 15
        score -= warning * 8

        return round(max(0, score), 1)

    async def calculate_cabin_score(self, cabin: CabinType) -> Tuple[float, Dict]:
        collection = get_collection("devices")
        total = await collection.count_documents({"cabin": cabin.value})
        if total == 0:
            return 100.0, {}

        normal = await collection.count_documents({
            "cabin": cabin.value,
            "status": DeviceStatus.NORMAL
        })

        warning = await collection.count_documents({
            "cabin": cabin.value,
            "status": DeviceStatus.WARNING
        })

        fault = await collection.count_documents({
            "cabin": cabin.value,
            "status": DeviceStatus.FAULT
        })

        alarm_collection = get_collection("alarms")
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        active_alarms = await alarm_collection.count_documents({
            "cabin": cabin.value,
            "timestamp": {"$gte": yesterday},
            "acknowledged": False
        })

        score = (normal / total) * 100
        score -= (warning / total) * 25
        score -= (fault / total) * 50
        score -= active_alarms * 5

        details = {
            "total_devices": total,
            "normal": normal,
            "warning": warning,
            "fault": fault,
            "active_alarms": active_alarms
        }

        return round(max(0, score), 1), details

    async def get_monthly_fault_stats(self) -> Dict:
        now = datetime.utcnow()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        alarm_collection = get_collection("alarms")
        device_collection = get_collection("devices")

        monthly_alarms = await alarm_collection.aggregate([
            {
                "$match": {
                    "timestamp": {"$gte": start_of_month}
                }
            },
            {
                "$group": {
                    "_id": "$level",
                    "count": {"$sum": 1}
                }
            }
        ]).to_list(length=None)

        alarm_by_type = await alarm_collection.aggregate([
            {
                "$match": {
                    "timestamp": {"$gte": start_of_month}
                }
            },
            {
                "$group": {
                    "_id": "$alarm_type",
                    "count": {"$sum": 1}
                }
            }
        ]).to_list(length=None)

        fault_count = await device_collection.count_documents({
            "status": DeviceStatus.FAULT
        })

        warning_count = await device_collection.count_documents({
            "status": DeviceStatus.WARNING
        })

        stats = {
            "month": now.strftime("%Y-%m"),
            "total_alarms": sum(a["count"] for a in monthly_alarms),
            "alarms_by_level": {a["_id"]: a["count"] for a in monthly_alarms},
            "alarms_by_type": {a["_id"]: a["count"] for a in alarm_by_type},
            "current_fault_devices": fault_count,
            "current_warning_devices": warning_count
        }

        return stats


health_calculator = HealthScoreCalculator()
