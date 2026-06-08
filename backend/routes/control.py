from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Dict, Any, Optional
from datetime import datetime

from backend.models.schemas import FanControlParams, PumpControlParams
from backend.services.control_service import control_service
from backend.models.database import (
    control_commands_collection,
    serialize_documents
)

router = APIRouter(prefix="/api/control", tags=["control"])


@router.post("/fan/{fan_id}")
async def control_fan(
    fan_id: str,
    params: FanControlParams,
    operator: str = "admin"
):
    try:
        result = await control_service.manual_control_device(
            device_id=fan_id,
            command="set_fan_speed" if params.running else "stop_fan",
            parameters={"running": params.running, "speed": params.speed},
            operator=operator
        )
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pump/{pump_id}")
async def control_pump(
    pump_id: str,
    params: PumpControlParams,
    operator: str = "admin"
):
    try:
        result = await control_service.manual_control_device(
            device_id=pump_id,
            command="start_pump" if params.running else "stop_pump",
            parameters={"running": params.running},
            operator=operator
        )
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pump/{pump_id}/auto-mode")
async def set_pump_auto_mode(pump_id: str, operator: str = "admin"):
    from backend.control.pump_control import pump_controller
    
    pump_controller.set_auto_mode(pump_id)
    
    result = await control_service.manual_control_device(
        device_id=pump_id,
        command="auto_mode",
        parameters={"auto_mode": True},
        operator=operator
    )
    return {"status": "success", **result}


@router.get("/commands")
async def get_control_commands(
    device_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    query = {}
    if device_id:
        query["device_id"] = device_id
    
    cursor = control_commands_collection.find(query).sort("timestamp", -1).limit(limit)
    commands = await cursor.to_list(length=limit)
    
    return {
        "commands": serialize_documents(commands),
        "count": len(commands)
    }


@router.get("/status/fans")
async def get_fans_status():
    from backend.control.ventilation_pid import ventilation_controller
    from backend.models.database import devices_collection, serialize_documents
    
    fans = await devices_collection.find({"type": "fan"}).to_list(length=100)
    result = []
    for fan in fans:
        state = ventilation_controller.get_fan_state(fan["device_id"])
        result.append({
            "device_id": fan["device_id"],
            "name": fan["name"],
            "chamber": fan["chamber"],
            "status": fan.get("status", "normal"),
            "running": fan.get("properties", {}).get("running", False),
            "speed": fan.get("properties", {}).get("speed", 0),
            "controller_state": state,
            "distance_km": fan.get("distance_km")
        })
    return {"fans": result, "count": len(result)}


@router.get("/status/pumps")
async def get_pumps_status():
    from backend.control.pump_control import pump_controller
    from backend.models.database import devices_collection
    
    pumps = await devices_collection.find({"type": "pump"}).to_list(length=100)
    result = []
    for pump in pumps:
        state = pump_controller.get_pump_state(pump["device_id"])
        auto_mode = pump_controller.auto_mode.get(pump["device_id"], True)
        result.append({
            "device_id": pump["device_id"],
            "name": pump["name"],
            "chamber": pump["chamber"],
            "status": pump.get("status", "normal"),
            "running": pump.get("properties", {}).get("running", False),
            "level": pump.get("properties", {}).get("level", 0),
            "auto_mode": auto_mode,
            "controller_state": state,
            "distance_km": pump.get("distance_km")
        })
    return {"pumps": result, "count": len(result)}


@router.post("/ventilation/reset")
async def reset_ventilation_controller():
    from backend.control.ventilation_pid import ventilation_controller
    ventilation_controller.reset()
    return {"status": "success", "message": "Ventilation controller reset"}


@router.get("/ventilation/debug")
async def get_ventilation_debug():
    from backend.control.ventilation_pid import ventilation_controller
    
    return {
        "oxygen_pid": {
            "kp": ventilation_controller.oxygen_pid.kp,
            "ki": ventilation_controller.oxygen_pid.ki,
            "kd": ventilation_controller.oxygen_pid.kd,
            "setpoint": ventilation_controller.oxygen_pid.setpoint,
            "integral": ventilation_controller.oxygen_pid.integral,
            "prev_error": ventilation_controller.oxygen_pid.prev_error,
            "last_output": ventilation_controller.oxygen_pid.last_output
        },
        "temperature_pid": {
            "kp": ventilation_controller.temperature_pid.kp,
            "ki": ventilation_controller.temperature_pid.ki,
            "kd": ventilation_controller.temperature_pid.kd,
            "setpoint": ventilation_controller.temperature_pid.setpoint,
            "integral": ventilation_controller.temperature_pid.integral,
            "prev_error": ventilation_controller.temperature_pid.prev_error,
            "last_output": ventilation_controller.temperature_pid.last_output
        },
        "fan_states": ventilation_controller.fan_states
    }
