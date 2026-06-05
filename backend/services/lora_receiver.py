import asyncio
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from config.settings import settings
from config.database import get_collection
from models.models import (
    EnvironmentData, EnvironmentDataBatch,
    ManholeData, ManholeDataBatch,
    DeviceStatus, CabinType
)
from utils.redis_client import redis_client, RedisChannels


class LoRaReceiver:
    def __init__(self):
        self._valid_device_ids: Optional[set] = None
        self._last_device_refresh: Optional[datetime] = None
        self._device_refresh_interval = 300

    async def _refresh_device_list(self):
        now = datetime.utcnow()
        if self._valid_device_ids is None or \
           (self._last_device_refresh and (now - self._last_device_refresh).total_seconds() > self._device_refresh_interval):
            try:
                devices = await get_collection("devices").find(
                    {"type": {"$in": ["env_sensor", "manhole"]}},
                    {"device_id": 1}
                ).to_list(length=None)
                self._valid_device_ids = {d["device_id"] for d in devices}
                self._last_device_refresh = now
                print(f"[LoRa接收] 设备列表已刷新，共 {len(self._valid_device_ids)} 个设备")
            except Exception as e:
                print(f"[LoRa接收] 刷新设备列表失败: {e}")

    def _validate_env_data(self, data: EnvironmentData) -> Tuple[bool, Optional[str]]:
        if data.temperature < -40 or data.temperature > 85:
            return False, f"温度超出范围: {data.temperature}"
        if data.humidity < 0 or data.humidity > 100:
            return False, f"湿度超出范围: {data.humidity}"
        if data.oxygen < 0 or data.oxygen > 100:
            return False, f"氧气浓度超出范围: {data.oxygen}"
        if data.methane < 0 or data.methane > 100:
            return False, f"甲烷浓度超出范围: {data.methane}"
        if data.hydrogen_sulfide < 0 or data.hydrogen_sulfide > 1000:
            return False, f"硫化氢浓度超出范围: {data.hydrogen_sulfide}"
        if data.rssi is not None and (data.rssi < -120 or data.rssi > 0):
            return False, f"RSSI超出范围: {data.rssi}"
        time_diff = abs((data.timestamp - datetime.utcnow()).total_seconds())
        if time_diff > 3600:
            return False, f"时间戳异常: {data.timestamp}"
        return True, None

    def _validate_manhole_data(self, data: ManholeData) -> Tuple[bool, Optional[str]]:
        if data.battery_level is not None and (data.battery_level < 0 or data.battery_level > 100):
            return False, f"电量超出范围: {data.battery_level}"
        if data.rssi is not None and (data.rssi < -120 or data.rssi > 0):
            return False, f"RSSI超出范围: {data.rssi}"
        time_diff = abs((data.timestamp - datetime.utcnow()).total_seconds())
        if time_diff > 3600:
            return False, f"时间戳异常: {data.timestamp}"
        return True, None

    def _get_env_device_status(self, data: EnvironmentData) -> DeviceStatus:
        if data.oxygen < 18 or data.methane >= 1 or data.hydrogen_sulfide >= 10 or data.temperature >= 35:
            return DeviceStatus.FAULT
        elif data.oxygen < 18.5 or data.methane > 0.8 or data.hydrogen_sulfide > 8 or data.temperature > 33:
            return DeviceStatus.WARNING
        else:
            return DeviceStatus.NORMAL

    def _get_manhole_device_status(self, data: ManholeData) -> DeviceStatus:
        if data.is_open and not data.is_legal:
            return DeviceStatus.FAULT
        elif data.battery_level is not None and data.battery_level < 20:
            return DeviceStatus.WARNING
        else:
            return DeviceStatus.NORMAL

    async def _verify_device_id(self, device_id: str) -> bool:
        if self._valid_device_ids is None:
            await self._refresh_device_list()
        if self._valid_device_ids is not None:
            return device_id in self._valid_device_ids
        return True

    async def process_single_env_data(self, data: EnvironmentData) -> Tuple[DeviceStatus, Dict]:
        is_valid, error = self._validate_env_data(data)
        if not is_valid:
            raise ValueError(f"数据校验失败: {error}")

        if not await self._verify_device_id(data.device_id):
            raise ValueError(f"无效的设备ID: {data.device_id}")

        await get_collection("environment_data").insert_one(data.dict())
        device_status = self._get_env_device_status(data)

        await get_collection("devices").update_one(
            {"device_id": data.device_id},
            {"$set": {
                "last_update": data.timestamp,
                "status": device_status.value
            }},
            upsert=True
        )

        sensor_data = {
            "temperature": data.temperature,
            "humidity": data.humidity,
            "oxygen": data.oxygen,
            "methane": data.methane,
            "hydrogen_sulfide": data.hydrogen_sulfide
        }

        await redis_client.publish(RedisChannels.ENV_DATA, {
            "device_id": data.device_id,
            "cabin": data.cabin.value if isinstance(data.cabin, CabinType) else data.cabin,
            "timestamp": data.timestamp.isoformat(),
            **sensor_data
        })

        await redis_client.publish(RedisChannels.DEVICE_UPDATE, {
            "device_id": data.device_id,
            "type": "env_sensor",
            "status": device_status.value,
            "data": sensor_data,
            "cabin": data.cabin.value if isinstance(data.cabin, CabinType) else data.cabin
        })

        return device_status, sensor_data

    async def process_batch_env_data(self, batch: EnvironmentDataBatch) -> Dict:
        await self._refresh_device_list()

        valid_data = []
        invalid_data = []
        device_updates = []
        env_publish_tasks = []

        for data in batch.data:
            is_valid, error = self._validate_env_data(data)
            if not is_valid:
                invalid_data.append({"device_id": data.device_id, "error": error})
                continue

            if not await self._verify_device_id(data.device_id):
                invalid_data.append({"device_id": data.device_id, "error": "无效设备ID"})
                continue

            valid_data.append(data)

        if not valid_data:
            return {
                "success": False,
                "processed": 0,
                "invalid": len(invalid_data),
                "errors": invalid_data
            }

        data_dicts = [d.dict() for d in valid_data]
        await get_collection("environment_data").insert_many(data_dicts, ordered=False)

        for data in valid_data:
            device_status = self._get_env_device_status(data)
            device_updates.append({
                "update_one": {
                    "filter": {"device_id": data.device_id},
                    "update": {"$set": {
                        "last_update": data.timestamp,
                        "status": device_status.value
                    }},
                    "upsert": True
                }
            })

            sensor_data = {
                "temperature": data.temperature,
                "humidity": data.humidity,
                "oxygen": data.oxygen,
                "methane": data.methane,
                "hydrogen_sulfide": data.hydrogen_sulfide
            }

            cabin_value = data.cabin.value if isinstance(data.cabin, CabinType) else data.cabin
            env_publish_tasks.append(
                redis_client.publish(RedisChannels.ENV_DATA, {
                    "device_id": data.device_id,
                    "cabin": cabin_value,
                    "timestamp": data.timestamp.isoformat(),
                    **sensor_data
                })
            )
            env_publish_tasks.append(
                redis_client.publish(RedisChannels.DEVICE_UPDATE, {
                    "device_id": data.device_id,
                    "type": "env_sensor",
                    "status": device_status.value,
                    "data": sensor_data,
                    "cabin": cabin_value
                })
            )

        if device_updates:
            await get_collection("devices").bulk_write(device_updates, ordered=False)

        if env_publish_tasks:
            await asyncio.gather(*env_publish_tasks)

        return {
            "success": True,
            "processed": len(valid_data),
            "invalid": len(invalid_data),
            "errors": invalid_data[:10]
        }

    async def process_single_manhole_data(self, data: ManholeData) -> Tuple[DeviceStatus, Dict]:
        is_valid, error = self._validate_manhole_data(data)
        if not is_valid:
            raise ValueError(f"数据校验失败: {error}")

        if not await self._verify_device_id(data.device_id):
            raise ValueError(f"无效的设备ID: {data.device_id}")

        await get_collection("manhole_data").insert_one(data.dict())
        device_status = self._get_manhole_device_status(data)

        await get_collection("devices").update_one(
            {"device_id": data.device_id},
            {"$set": {
                "last_update": data.timestamp,
                "status": device_status.value
            }},
            upsert=True
        )

        manhole_data = {
            "is_open": data.is_open,
            "is_legal": data.is_legal,
            "battery_level": data.battery_level
        }

        await redis_client.publish(RedisChannels.MANHOLE_DATA, {
            "device_id": data.device_id,
            "timestamp": data.timestamp.isoformat(),
            **manhole_data
        })

        await redis_client.publish(RedisChannels.DEVICE_UPDATE, {
            "device_id": data.device_id,
            "type": "manhole",
            "status": device_status.value,
            "data": manhole_data
        })

        return device_status, manhole_data

    async def process_batch_manhole_data(self, batch: ManholeDataBatch) -> Dict:
        await self._refresh_device_list()

        valid_data = []
        invalid_data = []
        device_updates = []
        publish_tasks = []

        for data in batch.data:
            is_valid, error = self._validate_manhole_data(data)
            if not is_valid:
                invalid_data.append({"device_id": data.device_id, "error": error})
                continue

            if not await self._verify_device_id(data.device_id):
                invalid_data.append({"device_id": data.device_id, "error": "无效设备ID"})
                continue

            valid_data.append(data)

        if not valid_data:
            return {
                "success": False,
                "processed": 0,
                "invalid": len(invalid_data),
                "errors": invalid_data
            }

        data_dicts = [d.dict() for d in valid_data]
        await get_collection("manhole_data").insert_many(data_dicts, ordered=False)

        for data in valid_data:
            device_status = self._get_manhole_device_status(data)
            device_updates.append({
                "update_one": {
                    "filter": {"device_id": data.device_id},
                    "update": {"$set": {
                        "last_update": data.timestamp,
                        "status": device_status.value
                    }},
                    "upsert": True
                }
            })

            manhole_data = {
                "is_open": data.is_open,
                "is_legal": data.is_legal,
                "battery_level": data.battery_level
            }

            publish_tasks.append(
                redis_client.publish(RedisChannels.MANHOLE_DATA, {
                    "device_id": data.device_id,
                    "timestamp": data.timestamp.isoformat(),
                    **manhole_data
                })
            )
            publish_tasks.append(
                redis_client.publish(RedisChannels.DEVICE_UPDATE, {
                    "device_id": data.device_id,
                    "type": "manhole",
                    "status": device_status.value,
                    "data": manhole_data
                })
            )

        if device_updates:
            await get_collection("devices").bulk_write(device_updates, ordered=False)

        if publish_tasks:
            await asyncio.gather(*publish_tasks)

        return {
            "success": True,
            "processed": len(valid_data),
            "invalid": len(invalid_data),
            "errors": invalid_data[:10]
        }


lora_receiver = LoRaReceiver()
