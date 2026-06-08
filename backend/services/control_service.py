import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from backend.config import settings
from backend.models.database import (
    devices_collection,
    sensor_data_collection,
    control_commands_collection,
    operation_logs_collection,
    health_scores_collection,
    serialize_document,
    serialize_documents
)
from backend.models.schemas import (
    SensorData,
    ControlCommand,
    OperationLog,
    HealthScore,
    DeviceStatus
)
from backend.control.ventilation_pid import ventilation_controller
from backend.control.pump_control import pump_controller
from backend.services.mqtt_service import mqtt_service
from backend.services.alert_service import alert_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ControlService:
    def __init__(self):
        self.fan_last_control: Dict[str, datetime] = {}
        self.pump_last_control: Dict[str, datetime] = {}
        self.control_interval = 30
    
    async def process_sensor_data(self, sensor_data: SensorData) -> Dict[str, Any]:
        result = await sensor_data_collection.insert_one(sensor_data.dict())
        
        await devices_collection.update_one(
            {"device_id": sensor_data.device_id},
            {"$set": {"last_data": sensor_data.dict()}}
        )
        
        alerts = await alert_service.check_sensor_data(sensor_data)
        
        control_actions = []
        
        if sensor_data.type == "env_sensor" and sensor_data.oxygen is not None:
            control_actions = await self._process_ventilation_control(sensor_data)
        
        if sensor_data.type == "pump" and sensor_data.level is not None:
            control_actions = await self._process_pump_control(sensor_data)
        
        await self._update_device_status(sensor_data.device_id)
        
        return {
            "sensor_data_id": str(result.inserted_id),
            "alerts_count": len(alerts),
            "control_actions": control_actions
        }
    
    async def _process_ventilation_control(self, sensor_data: SensorData) -> List[Dict[str, Any]]:
        if sensor_data.oxygen is None or sensor_data.temperature is None:
            return []
        
        running, speed, control_details = ventilation_controller.calculate_control(
            oxygen=sensor_data.oxygen,
            temperature=sensor_data.temperature,
            humidity=sensor_data.humidity or 60
        )
        
        control_actions = []
        
        fans = await devices_collection.find({
            "type": "fan",
            "status": {"$ne": "fault"}
        }).to_list(length=settings.NUM_FANS)
        
        for fan in fans:
            fan_id = fan["device_id"]
            now = datetime.utcnow()
            
            last_control = self.fan_last_control.get(fan_id)
            if last_control and (now - last_control).total_seconds() < self.control_interval:
                continue
            
            current_state = fan.get("properties", {})
            current_running = current_state.get("running", False)
            current_speed = current_state.get("speed", 0)
            
            if current_running != running or current_speed != speed:
                action = await self._control_fan(fan_id, running, speed, control_details)
                if action:
                    control_actions.append(action)
                self.fan_last_control[fan_id] = now
        
        return control_actions
    
    async def _control_fan(self, fan_id: str, running: bool, speed: int,
                           control_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        command = ControlCommand(
            device_id=fan_id,
            command="set_fan_speed" if running else "stop_fan",
            parameters={"running": running, "speed": speed, "control_details": control_details},
            source="automatic"
        )
        
        await control_commands_collection.insert_one(command.dict())
        
        await mqtt_service.publish_control_command(
            device_id=fan_id,
            command=command.command,
            parameters=command.parameters
        )
        
        await devices_collection.update_one(
            {"device_id": fan_id},
            {"$set": {
                "properties.running": running,
                "properties.speed": speed,
                "properties.last_control_time": datetime.utcnow()
            }}
        )
        
        ventilation_controller.update_fan_state(fan_id, running, speed)
        
        log = OperationLog(
            device_id=fan_id,
            action="fan_control",
            details={"running": running, "speed": speed},
            operator="system"
        )
        await operation_logs_collection.insert_one(log.dict())
        
        return {
            "device_id": fan_id,
            "running": running,
            "speed": speed,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _process_pump_control(self, sensor_data: SensorData) -> List[Dict[str, Any]]:
        if sensor_data.level is None:
            return []
        
        pump_id = sensor_data.device_id
        running, control_details = pump_controller.calculate_control(pump_id, sensor_data.level)
        
        control_actions = []
        
        now = datetime.utcnow()
        last_control = self.pump_last_control.get(pump_id)
        if last_control and (now - last_control).total_seconds() < self.control_interval:
            return control_actions
        
        pump = await devices_collection.find_one({"device_id": pump_id})
        if not pump:
            return control_actions
        
        current_running = pump.get("properties", {}).get("running", False)
        
        if current_running != running or control_details.get("control_changed"):
            action = await self._control_pump(pump_id, running, control_details)
            if action:
                control_actions.append(action)
            self.pump_last_control[pump_id] = now
        
        return control_actions
    
    async def _control_pump(self, pump_id: str, running: bool,
                            control_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        command = ControlCommand(
            device_id=pump_id,
            command="start_pump" if running else "stop_pump",
            parameters={"running": running, "control_details": control_details},
            source="automatic"
        )
        
        await control_commands_collection.insert_one(command.dict())
        
        await mqtt_service.publish_control_command(
            device_id=pump_id,
            command=command.command,
            parameters=command.parameters
        )
        
        update_data = {
            "properties.running": running,
            "properties.level": control_details.get("level", 0)
        }
        if running:
            update_data["properties.last_start"] = datetime.utcnow()
        else:
            update_data["properties.last_stop"] = datetime.utcnow()
        
        await devices_collection.update_one({"device_id": pump_id}, {"$set": update_data})
        
        log = OperationLog(
            device_id=pump_id,
            action="pump_control",
            details={"running": running},
            operator="system"
        )
        await operation_logs_collection.insert_one(log.dict())
        
        return {
            "device_id": pump_id,
            "running": running,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def manual_control_device(self, device_id: str, command: str,
                                     parameters: Dict[str, Any],
                                     operator: str) -> Dict[str, Any]:
        device = await devices_collection.find_one({"device_id": device_id})
        if not device:
            raise ValueError(f"Device {device_id} not found")
        
        if device["type"] == "pump":
            if "running" in parameters:
                pump_controller.set_manual_mode(device_id, parameters["running"])
            elif command == "auto_mode":
                pump_controller.set_auto_mode(device_id)
        
        control_command = ControlCommand(
            device_id=device_id,
            command=command,
            parameters=parameters,
            source="manual"
        )
        
        await control_commands_collection.insert_one(control_command.dict())
        
        await mqtt_service.publish_control_command(device_id, command, parameters)
        
        log = OperationLog(
            device_id=device_id,
            action=command,
            details=parameters,
            operator=operator
        )
        await operation_logs_collection.insert_one(log.dict())
        
        if parameters.get("running") is not None:
            await devices_collection.update_one(
                {"device_id": device_id},
                {"$set": {"properties.running": parameters["running"]}}
            )
        if parameters.get("speed") is not None:
            await devices_collection.update_one(
                {"device_id": device_id},
                {"$set": {"properties.speed": parameters["speed"]}}
            )
        
        return {
            "status": "success",
            "device_id": device_id,
            "command": command,
            "parameters": parameters,
            "operator": operator
        }
    
    async def _update_device_status(self, device_id: str):
        device = await devices_collection.find_one({"device_id": device_id})
        if not device:
            return
        
        status = DeviceStatus.NORMAL
        device_type = device.get("type")
        
        if device_type == "env_sensor":
            last_data = device.get("last_data", {})
            if last_data.get("methane", 0) >= settings.METHANE_ALARM * 0.8 or \
               last_data.get("h2s", 0) >= settings.H2S_ALARM * 0.8 or \
               last_data.get("oxygen", 20) < settings.OXYGEN_ALARM_LOW + 1 or \
               last_data.get("temperature", 25) > settings.TEMPERATURE_MAX - 3:
                status = DeviceStatus.WARNING
            
            if last_data.get("methane", 0) >= settings.METHANE_ALARM or \
               last_data.get("h2s", 0) >= settings.H2S_ALARM or \
               last_data.get("oxygen", 20) < settings.OXYGEN_ALARM_LOW or \
               last_data.get("temperature", 25) > settings.TEMPERATURE_MAX:
                status = DeviceStatus.FAULT
        
        elif device_type == "manhole":
            last_data = device.get("last_data", {})
            if last_data.get("cover_open", False):
                status = DeviceStatus.FAULT
        
        elif device_type in ["pump", "fan"]:
            props = device.get("properties", {})
            fault_count = props.get("fault_count", 0)
            if fault_count > 3:
                status = DeviceStatus.FAULT
            elif fault_count > 0:
                status = DeviceStatus.WARNING
        
        await devices_collection.update_one(
            {"device_id": device_id},
            {"$set": {"status": status}}
        )
    
    async def calculate_health_score(self) -> Dict[str, Any]:
        total_devices = await devices_collection.count_documents({})
        normal_devices = await devices_collection.count_documents({"status": "normal"})
        warning_devices = await devices_collection.count_documents({"status": "warning"})
        fault_devices = await devices_collection.count_documents({"status": "fault"})
        
        now = datetime.utcnow()
        start_of_day = datetime(now.year, now.month, now.day)
        
        alerts_today = await alert_service.get_alert_history(
            start_time=start_of_day,
            end_time=now
        )
        
        alert_count = len(alerts_today)
        
        device_score = (normal_devices / max(1, total_devices)) * 60
        warning_penalty = warning_devices / max(1, total_devices) * 15
        fault_penalty = fault_devices / max(1, total_devices) * 30
        alert_penalty = min(alert_count * 2, 25)
        
        total_score = max(0, min(100, device_score - warning_penalty - fault_penalty - alert_penalty))
        
        details = {
            "device_score": round(device_score, 2),
            "warning_penalty": round(warning_penalty, 2),
            "fault_penalty": round(fault_penalty, 2),
            "alert_penalty": round(alert_penalty, 2),
            "total_devices": total_devices,
            "normal_devices": normal_devices,
            "warning_devices": warning_devices,
            "fault_devices": fault_devices,
            "alerts_today": alert_count
        }
        
        health_score = HealthScore(
            score=round(total_score, 2),
            details={k: round(v, 2) if isinstance(v, float) else v for k, v in details.items()}
        )
        
        await health_scores_collection.insert_one(health_score.dict())
        
        return {
            "score": round(total_score, 2),
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def get_fault_statistics(self, months: int = 1) -> Dict[str, Any]:
        now = datetime.utcnow()
        start_time = now - timedelta(days=30 * months)
        
        pipeline = [
            {"$match": {
                "timestamp": {"$gte": start_time, "$lte": now},
                "level": {"$in": ["level1", "level2", "security"]}
            }},
            {"$group": {
                "_id": "$type",
                "count": {"$sum": 1}
            }}
        ]
        
        results = await alerts_collection.aggregate(pipeline).to_list(length=100)
        
        type_counts = {item["_id"]: item["count"] for item in results}
        
        pipeline2 = [
            {"$match": {
                "timestamp": {"$gte": start_time, "$lte": now}
            }},
            {"$group": {
                "_id": "$level",
                "count": {"$sum": 1}
            }}
        ]
        
        level_results = await alerts_collection.aggregate(pipeline2).to_list(length=100)
        level_counts = {item["_id"]: item["count"] for item in level_results}
        
        devices_by_type = await devices_collection.aggregate([
            {"$group": {"_id": "$type", "count": {"$sum": 1}}}
        ]).to_list(length=100)
        
        devices_fault = await devices_collection.aggregate([
            {"$match": {"status": "fault"}},
            {"$group": {"_id": "$type", "count": {"$sum": 1}}}
        ]).to_list(length=100)
        
        return {
            "period": f"last_{months}_months",
            "total_alerts": sum(type_counts.values()),
            "alerts_by_type": type_counts,
            "alerts_by_level": level_counts,
            "total_devices": {item["_id"]: item["count"] for item in devices_by_type},
            "fault_devices": {item["_id"]: item["count"] for item in devices_fault},
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat()
        }
    
    async def get_device_history(self, device_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        cursor = sensor_data_collection.find({
            "device_id": device_id,
            "timestamp": {"$gte": start_time, "$lte": end_time}
        }).sort("timestamp", 1)
        
        data = await cursor.to_list(length=1440)
        return serialize_documents(data)
    
    async def get_operation_history(self, device_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = operation_logs_collection.find({
            "device_id": device_id
        }).sort("timestamp", -1).limit(limit)
        
        logs = await cursor.to_list(length=limit)
        return serialize_documents(logs)


control_service = ControlService()
