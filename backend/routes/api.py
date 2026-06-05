import asyncio
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from bson import ObjectId

from config.database import get_collection
from models.models import (
    EnvironmentData, EnvironmentDataBatch,
    ManholeData, ManholeDataBatch,
    FanData, PumpData,
    Device, DeviceStatus, Alarm, CabinType, DeviceType,
    OperationHistory
)
from controllers.alarm_manager import alarm_manager
from controllers.health_score import health_calculator
from controllers.ventilation_control import ventilation_controller
from controllers.pump_control import pump_controller
from utils.mqtt_client import mqtt_client
from utils.websocket import manager

router = APIRouter()


@router.get("/")
async def root():
    return {
        "app": "地下管廊综合监控与智能运维系统",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }


def _get_env_device_status(data: EnvironmentData) -> DeviceStatus:
    if data.oxygen < 18 or data.methane >= 1 or data.hydrogen_sulfide >= 10 or data.temperature >= 35:
        return DeviceStatus.FAULT
    elif data.oxygen < 18.5 or data.methane > 0.8 or data.hydrogen_sulfide > 8 or data.temperature > 33:
        return DeviceStatus.WARNING
    else:
        return DeviceStatus.NORMAL


def _get_manhole_device_status(data: ManholeData) -> DeviceStatus:
    if data.is_open and not data.is_legal:
        return DeviceStatus.FAULT
    elif data.battery_level is not None and data.battery_level < 20:
        return DeviceStatus.WARNING
    else:
        return DeviceStatus.NORMAL


async def _process_single_env_data(data: EnvironmentData) -> Tuple[DeviceStatus, Dict]:
    await get_collection("environment_data").insert_one(data.dict())

    device_status = _get_env_device_status(data)

    await get_collection("devices").update_one(
        {"device_id": data.device_id},
        {"$set": {
            "last_update": data.timestamp,
            "status": device_status.value
        }},
        upsert=True
    )

    await alarm_manager.check_environment_data(data)

    asyncio.create_task(
        ventilation_controller.process_sensor_data(
            data.cabin, data.oxygen, data.temperature, data.humidity
        )
    )

    return device_status, {
        "temperature": data.temperature,
        "humidity": data.humidity,
        "oxygen": data.oxygen,
        "methane": data.methane,
        "hydrogen_sulfide": data.hydrogen_sulfide
    }


@router.post("/data/lora")
async def receive_lora_data(data: EnvironmentData):
    try:
        start_time = datetime.utcnow()
        device_status, sensor_data = await _process_single_env_data(data)
        process_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        await manager.broadcast_device_update({
            "device_id": data.device_id,
            "type": "env_sensor",
            "status": device_status.value,
            "data": sensor_data,
            "process_time_ms": process_time
        })

        return {
            "status": "success",
            "message": "数据接收成功",
            "process_time_ms": process_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/lora/batch")
async def receive_lora_data_batch(batch: EnvironmentDataBatch):
    try:
        start_time = datetime.utcnow()
        env_collection = get_collection("environment_data")
        devices_collection = get_collection("devices")

        if not batch.data:
            return {"status": "success", "count": 0, "message": "空批次"}

        data_dicts = [d.dict() for d in batch.data]
        await env_collection.insert_many(data_dicts, ordered=False)

        device_updates = []
        broadcast_tasks = []
        cabin_avg_data: Dict[str, Dict] = {}

        for data in batch.data:
            device_status = _get_env_device_status(data)

            device_updates.append({
                "update_one": {
                    "filter": {"device_id": data.device_id},
                    "update": {
                        "$set": {
                            "last_update": data.timestamp,
                            "status": device_status.value
                        }
                    },
                    "upsert": True
                }
            })

            cabin = data.cabin.value
            if cabin not in cabin_avg_data:
                cabin_avg_data[cabin] = {
                    "count": 0,
                    "oxygen_sum": 0,
                    "temperature_sum": 0,
                    "humidity_sum": 0
                }
            cabin_avg_data[cabin]["count"] += 1
            cabin_avg_data[cabin]["oxygen_sum"] += data.oxygen
            cabin_avg_data[cabin]["temperature_sum"] += data.temperature
            cabin_avg_data[cabin]["humidity_sum"] += data.humidity

            broadcast_tasks.append(
                manager.broadcast_device_update({
                    "device_id": data.device_id,
                    "type": "env_sensor",
                    "status": device_status.value,
                    "data": {
                        "temperature": data.temperature,
                        "humidity": data.humidity,
                        "oxygen": data.oxygen,
                        "methane": data.methane,
                        "hydrogen_sulfide": data.hydrogen_sulfide
                    }
                })
            )

        if device_updates:
            await devices_collection.bulk_write(device_updates, ordered=False)

        alarm_tasks = [alarm_manager.check_environment_data(d) for d in batch.data]
        await asyncio.gather(*alarm_tasks)

        for cabin, avg_data in cabin_avg_data.items():
            count = avg_data["count"]
            avg_oxygen = avg_data["oxygen_sum"] / count
            avg_temperature = avg_data["temperature_sum"] / count
            avg_humidity = avg_data["humidity_sum"] / count

            asyncio.create_task(
                ventilation_controller.process_sensor_data(
                    CabinType(cabin), avg_oxygen, avg_temperature, avg_humidity
                )
            )

        if broadcast_tasks:
            await asyncio.gather(*broadcast_tasks)

        process_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "status": "success",
            "count": len(batch.data),
            "process_time_ms": process_time,
            "throughput": round(len(batch.data) / (process_time / 1000), 2) if process_time > 0 else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _process_single_manhole_data(data: ManholeData) -> DeviceStatus:
    await get_collection("manhole_data").insert_one(data.dict())

    device_status = _get_manhole_device_status(data)

    await get_collection("devices").update_one(
        {"device_id": data.device_id},
        {"$set": {
            "last_update": data.timestamp,
            "status": device_status.value
        }},
        upsert=True
    )

    await alarm_manager.check_manhole_data(data)

    return device_status


@router.post("/data/manhole")
async def receive_manhole_data(data: ManholeData):
    try:
        device_status = await _process_single_manhole_data(data)

        await manager.broadcast_device_update({
            "device_id": data.device_id,
            "type": "manhole",
            "status": device_status.value,
            "data": {
                "is_open": data.is_open,
                "is_legal": data.is_legal
            }
        })

        return {"status": "success", "message": "井盖数据接收成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/manhole/batch")
async def receive_manhole_data_batch(batch: ManholeDataBatch):
    try:
        start_time = datetime.utcnow()
        manhole_collection = get_collection("manhole_data")
        devices_collection = get_collection("devices")

        if not batch.data:
            return {"status": "success", "count": 0, "message": "空批次"}

        data_dicts = [d.dict() for d in batch.data]
        await manhole_collection.insert_many(data_dicts, ordered=False)

        device_updates = []
        broadcast_tasks = []

        for data in batch.data:
            device_status = _get_manhole_device_status(data)

            device_updates.append({
                "update_one": {
                    "filter": {"device_id": data.device_id},
                    "update": {
                        "$set": {
                            "last_update": data.timestamp,
                            "status": device_status.value
                        }
                    },
                    "upsert": True
                }
            })

            broadcast_tasks.append(
                manager.broadcast_device_update({
                    "device_id": data.device_id,
                    "type": "manhole",
                    "status": device_status.value,
                    "data": {
                        "is_open": data.is_open,
                        "is_legal": data.is_legal
                    }
                })
            )

        if device_updates:
            await devices_collection.bulk_write(device_updates, ordered=False)

        alarm_tasks = [alarm_manager.check_manhole_data(d) for d in batch.data]
        await asyncio.gather(*alarm_tasks)

        if broadcast_tasks:
            await asyncio.gather(*broadcast_tasks)

        process_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "status": "success",
            "count": len(batch.data),
            "process_time_ms": process_time,
            "throughput": round(len(batch.data) / (process_time / 1000), 2) if process_time > 0 else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/pump")
async def receive_pump_data(data: PumpData):
    try:
        data_dict = data.dict()
        await get_collection("pump_data").insert_one(data_dict)

        await pump_controller.process_level_data(
            data.device_id, data.cabin.value, data.level, data.is_running
        )

        device_updates = {
            "last_update": data.timestamp
        }

        if data.current is not None and data.current > 15:
            device_updates["status"] = DeviceStatus.WARNING
        elif not data.is_running and data.level > 0.9:
            device_updates["status"] = DeviceStatus.FAULT
        else:
            device_updates["status"] = DeviceStatus.NORMAL

        await get_collection("devices").update_one(
            {"device_id": data.device_id},
            {"$set": device_updates},
            upsert=True
        )

        return {"status": "success", "message": "水泵数据接收成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices")
async def get_devices(
    type: Optional[DeviceType] = None,
    cabin: Optional[CabinType] = None,
    status: Optional[DeviceStatus] = None
):
    query = {}
    if type:
        query["type"] = type.value
    if cabin:
        query["cabin"] = cabin.value
    if status:
        query["status"] = status.value

    devices = await get_collection("devices").find(query).to_list(length=None)
    for d in devices:
        if "_id" in d:
            d["_id"] = str(d["_id"])

    return {"count": len(devices), "devices": devices}


@router.get("/devices/{device_id}")
async def get_device(device_id: str):
    device = await get_collection("devices").find_one({"device_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    if "_id" in device:
        device["_id"] = str(device["_id"])
    return device


@router.get("/devices/{device_id}/trend")
async def get_device_trend(
    device_id: str,
    hours: int = Query(24, ge=1, le=72)
):
    device = await get_collection("devices").find_one({"device_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    start_time = datetime.utcnow() - timedelta(hours=hours)
    device_type = device.get("type")

    collection_name = None
    if device_type == "env_sensor":
        collection_name = "environment_data"
    elif device_type == "manhole":
        collection_name = "manhole_data"
    elif device_type == "fan":
        collection_name = "fan_data"
    elif device_type == "pump":
        collection_name = "pump_data"

    if not collection_name:
        raise HTTPException(status_code=400, detail="不支持的设备类型")

    data = await get_collection(collection_name).find({
        "device_id": device_id,
        "timestamp": {"$gte": start_time}
    }).sort("timestamp", 1).to_list(length=None)

    for d in data:
        if "_id" in d:
            del d["_id"]
        if "timestamp" in d:
            d["timestamp"] = d["timestamp"].isoformat()

    return {"device_id": device_id, "hours": hours, "data": data}


@router.get("/devices/{device_id}/history")
async def get_device_operation_history(
    device_id: str,
    limit: int = Query(50, ge=1, le=200)
):
    history = await get_collection("operation_history").find({
        "device_id": device_id
    }).sort("timestamp", -1).limit(limit).to_list(length=None)

    for h in history:
        if "_id" in h:
            h["_id"] = str(h["_id"])
        if "timestamp" in h:
            h["timestamp"] = h["timestamp"].isoformat()

    return {"device_id": device_id, "count": len(history), "history": history}


@router.post("/devices/{device_id}/control")
async def control_device(
    device_id: str,
    command: dict
):
    device = await get_collection("devices").find_one({"device_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    device_type = device.get("type")
    cmd = command.get("command")
    operator = command.get("operator", "manual")

    if device_type == "fan":
        speed = command.get("speed", 50)
        mqtt_client.send_fan_command(device_id, cmd, speed)
        is_running = cmd == "start"
        ventilation_controller.update_fan_state(device_id, device.cabin, is_running, speed if is_running else 0)
    elif device_type == "pump":
        pump_controller.manual_control(device_id, cmd, operator)
    else:
        raise HTTPException(status_code=400, detail="该设备类型不支持手动控制")

    op_history = OperationHistory(
        device_id=device_id,
        operation=f"manual_{cmd}",
        operator=operator,
        parameters=command
    )
    await get_collection("operation_history").insert_one(op_history.dict())

    return {"status": "success", "message": f"命令已发送: {cmd}"}


@router.get("/alarms")
async def get_alarms(
    level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500)
):
    query = {}
    if level:
        query["level"] = level
    if acknowledged is not None:
        query["acknowledged"] = acknowledged

    alarms = await get_collection("alarms").find(query).sort("timestamp", -1).limit(limit).to_list(length=None)

    for a in alarms:
        if "_id" in a:
            a["_id"] = str(a["_id"])
        if "timestamp" in a:
            a["timestamp"] = a["timestamp"].isoformat()
        if "acknowledged_at" in a and a["acknowledged_at"]:
            a["acknowledged_at"] = a["acknowledged_at"].isoformat()

    return {"count": len(alarms), "alarms": alarms}


@router.post("/alarms/{alarm_id}/acknowledge")
async def acknowledge_alarm(alarm_id: str, user_data: dict):
    user = user_data.get("user", "unknown")
    success = await alarm_manager.acknowledge_alarm(ObjectId(alarm_id), user)
    if not success:
        raise HTTPException(status_code=404, detail="告警不存在")
    return {"status": "success", "message": "告警已确认"}


@router.get("/health/score")
async def get_health_score():
    overall_score, details = await health_calculator.calculate_overall_score()

    cabin_scores = {}
    for cabin in [CabinType.POWER, CabinType.WATER, CabinType.GAS]:
        score, cabin_details = await health_calculator.calculate_cabin_score(cabin)
        cabin_scores[cabin.value] = {
            "score": score,
            "details": cabin_details
        }

    return {
        "overall_score": overall_score,
        "component_scores": details,
        "cabin_scores": cabin_scores,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/fault-stats")
async def get_fault_statistics():
    stats = await health_calculator.get_monthly_fault_stats()
    return stats


@router.get("/geojson/devices")
async def get_devices_geojson():
    devices = await get_collection("devices").find().to_list(length=None)

    features = []
    for device in devices:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": device.get("location", [0, 0])
            },
            "properties": {
                "device_id": device.get("device_id"),
                "name": device.get("name"),
                "type": device.get("type"),
                "cabin": device.get("cabin"),
                "status": device.get("status", "normal"),
                "description": device.get("description", "")
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }


@router.get("/geojson/corridor")
async def get_corridor_geojson():
    corridor_data = await get_collection("corridor_geojson").find_one({})
    if corridor_data and "_id" in corridor_data:
        del corridor_data["_id"]
    return corridor_data or {"type": "FeatureCollection", "features": []}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_personal_message({"type": "pong", "timestamp": datetime.utcnow().isoformat()}, websocket)
            except:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket错误: {e}")
        manager.disconnect(websocket)
