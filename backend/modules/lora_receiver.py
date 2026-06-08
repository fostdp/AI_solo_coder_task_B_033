import asyncio
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from backend.config import settings
from backend.models.schemas import SensorData, DeviceType, DeviceStatus
from backend.models.database import (
    devices_collection,
    sensor_data_collection,
    serialize_document
)

logger = logging.getLogger(__name__)


class LoraReceiver:
    def __init__(self):
        self.redis_client = None
        self.channel = settings.REDIS_CHANNEL_SENSOR_DATA
        self.running = False
        self._validation_rules = {
            "temperature": {"min": -40, "max": 85, "max_change": 20},
            "humidity": {"min": 0, "max": 100, "max_change": 30},
            "oxygen": {"min": 0, "max": 25, "max_change": 5},
            "methane": {"min": 0, "max": 100, "max_change": 10},
            "h2s": {"min": 0, "max": 100, "max_change": 20},
            "level": {"min": 0, "max": 100, "max_change": 50}
        }
        self._history_cache: Dict[str, Dict[str, float]] = defaultdict(dict)
    
    async def connect_redis(self):
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using in-memory queue")
            self.redis_client = None
            return
        
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}, using in-memory queue")
            self.redis_client = None
    
    async def disconnect_redis(self):
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
    
    def validate_sensor_data(self, data: SensorData, device_info: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors = []
        
        if not device_info:
            errors.append(f"Device {data.device_id} not found")
            return False, errors
        
        data_fields = {
            "temperature": data.temperature,
            "humidity": data.humidity,
            "oxygen": data.oxygen,
            "methane": data.methane,
            "h2s": data.h2s,
            "level": data.level
        }
        
        for field, value in data_fields.items():
            if value is None:
                continue
            
            rules = self._validation_rules.get(field)
            if not rules:
                continue
            
            if value < rules["min"] or value > rules["max"]:
                errors.append(
                    f"{field}={value} out of range [{rules['min']}, {rules['max']}]"
                )
                continue
            
            prev_value = self._history_cache.get(data.device_id, {}).get(field)
            if prev_value is not None:
                change = abs(value - prev_value)
                if change > rules["max_change"]:
                    errors.append(
                        f"{field} changed too fast: {prev_value} -> {value} (Δ={change:.1f}, max={rules['max_change']})"
                    )
        
        return len(errors) == 0, errors
    
    def update_history(self, device_id: str, data: SensorData):
        if data.temperature is not None:
            self._history_cache[device_id]["temperature"] = data.temperature
        if data.humidity is not None:
            self._history_cache[device_id]["humidity"] = data.humidity
        if data.oxygen is not None:
            self._history_cache[device_id]["oxygen"] = data.oxygen
        if data.methane is not None:
            self._history_cache[device_id]["methane"] = data.methane
        if data.h2s is not None:
            self._history_cache[device_id]["h2s"] = data.h2s
        if data.level is not None:
            self._history_cache[device_id]["level"] = data.level
    
    def enrich_sensor_data(self, data: SensorData, device_info: Dict[str, Any]) -> SensorData:
        if device_info["type"] == "env_sensor":
            data.type = "env_sensor"
        elif device_info["type"] == "pump":
            data.type = "pump"
        elif device_info["type"] == "manhole":
            data.type = "manhole"
        elif device_info["type"] == "fan":
            data.type = "fan"
        else:
            data.type = device_info["type"]
        
        if data.location is None and device_info.get("location"):
            from backend.models.schemas import Location
            data.location = Location(**device_info["location"])
        
        return data
    
    async def process_single_data(self, data: SensorData) -> Dict[str, Any]:
        device = await devices_collection.find_one({"device_id": data.device_id})
        
        is_valid, errors = self.validate_sensor_data(data, device)
        if not is_valid:
            logger.warning(f"Invalid sensor data {data.device_id}: {errors}")
            return {
                "device_id": data.device_id,
                "status": "error",
                "errors": errors
            }
        
        enriched_data = self.enrich_sensor_data(data, device)
        
        await sensor_data_collection.insert_one(enriched_data.dict())
        
        await devices_collection.update_one(
            {"device_id": data.device_id},
            {"$set": {"last_data": enriched_data.dict()}}
        )
        
        self.update_history(data.device_id, enriched_data)
        
        await self._publish_to_redis(enriched_data, device)
        
        return {
            "device_id": data.device_id,
            "status": "success",
            "type": enriched_data.type
        }
    
    async def process_batch_data(self, datas: List[SensorData]) -> Dict[str, Any]:
        if not datas:
            return {"processed": 0, "failed": 0}
        
        device_ids = [d.device_id for d in datas]
        devices_cursor = devices_collection.find({"device_id": {"$in": device_ids}})
        devices_list = await devices_cursor.to_list(length=len(device_ids))
        device_map = {d["device_id"]: d for d in devices_list}
        
        valid_data = []
        valid_dicts = []
        device_updates = []
        failed = []
        redis_messages = []
        
        for data in datas:
            device = device_map.get(data.device_id)
            
            is_valid, errors = self.validate_sensor_data(data, device)
            if not is_valid:
                failed.append({
                    "device_id": data.device_id,
                    "errors": errors
                })
                continue
            
            enriched_data = self.enrich_sensor_data(data, device)
            valid_data.append((enriched_data, device))
            valid_dicts.append(enriched_data.dict())
            
            device_updates.append({
                "update_one": {
                    "filter": {"device_id": data.device_id},
                    "update": {"$set": {"last_data": enriched_data.dict()}}
                }
            })
            
            self.update_history(data.device_id, enriched_data)
            
            redis_messages.append((enriched_data, device))
        
        if valid_dicts:
            await sensor_data_collection.insert_many(valid_dicts, ordered=False)
        
        if device_updates:
            await devices_collection.bulk_write(device_updates, ordered=False)
        
        for enriched_data, device in redis_messages:
            await self._publish_to_redis(enriched_data, device)
        
        return {
            "total_received": len(datas),
            "processed": len(valid_data),
            "failed": len(failed),
            "failed_items": failed
        }
    
    async def _publish_to_redis(self, data: SensorData, device: Dict[str, Any]):
        message = {
            "device_id": data.device_id,
            "type": data.type,
            "chamber": device.get("chamber", "综合"),
            "timestamp": data.timestamp.isoformat(),
            "data": {
                "temperature": data.temperature,
                "humidity": data.humidity,
                "oxygen": data.oxygen,
                "methane": data.methane,
                "h2s": data.h2s,
                "level": data.level,
                "cover_open": data.cover_open,
                "running": data.running,
                "speed": data.speed
            },
            "device_info": {
                "type": device.get("type"),
                "chamber": device.get("chamber"),
                "distance_km": device.get("distance_km")
            }
        }
        
        message_json = json.dumps(message)
        
        if self.redis_client:
            try:
                await self.redis_client.publish(self.channel, message_json)
            except Exception as e:
                logger.error(f"Failed to publish to Redis: {e}")
        else:
            if hasattr(self, '_in_memory_queue'):
                await self._in_memory_queue.put(message)
    
    def get_validation_rules(self) -> Dict[str, Any]:
        return self._validation_rules.copy()
    
    async def process_data(self, data: SensorData) -> Dict[str, Any]:
        return await self.process_single_data(data)
    
    async def start_redis_listener(self):
        logger.info("LoraReceiver Redis listener started (publisher only)")
        self.running = True
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("LoraReceiver listener stopped")
            self.running = False


lora_receiver = LoraReceiver()
