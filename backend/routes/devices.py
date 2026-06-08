from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta

from backend.models.database import (
    devices_collection,
    tunnel_route_collection,
    serialize_document,
    serialize_documents
)
from backend.models.schemas import DeviceType, DeviceStatus

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("/")
async def get_devices(
    type: Optional[DeviceType] = None,
    chamber: Optional[str] = None,
    status: Optional[DeviceStatus] = None,
    limit: int = Query(1000, ge=1, le=5000)
):
    query = {}
    if type:
        query["type"] = type.value
    if chamber:
        query["chamber"] = chamber
    if status:
        query["status"] = status.value
    
    cursor = devices_collection.find(query).limit(limit)
    devices = await cursor.to_list(length=limit)
    return {"devices": serialize_documents(devices), "count": len(devices)}


@router.get("/geojson")
async def get_devices_geojson(
    type: Optional[DeviceType] = None,
    chamber: Optional[str] = None,
    status: Optional[DeviceStatus] = None
):
    query = {}
    if type:
        query["type"] = type.value
    if chamber:
        query["chamber"] = chamber
    if status:
        query["status"] = status.value
    
    cursor = devices_collection.find(query)
    devices = await cursor.to_list(length=5000)
    
    features = []
    for device in devices:
        device = serialize_document(device)
        feature = {
            "type": "Feature",
            "id": device["device_id"],
            "properties": {
                "device_id": device["device_id"],
                "type": device["type"],
                "name": device["name"],
                "chamber": device["chamber"],
                "status": device["status"],
                "distance_km": device.get("distance_km"),
                **device.get("properties", {})
            },
            "geometry": device.get("location")
        }
        features.append(feature)
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


@router.get("/tunnel-route")
async def get_tunnel_route():
    route = await tunnel_route_collection.find_one()
    if not route:
        raise HTTPException(status_code=404, detail="Tunnel route not found")
    return serialize_document(route)


@router.get("/{device_id}")
async def get_device(device_id: str):
    device = await devices_collection.find_one({"device_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return serialize_document(device)


@router.get("/{device_id}/history")
async def get_device_history(
    device_id: str,
    hours: int = Query(24, ge=1, le=720)
):
    from backend.services.control_service import control_service
    
    device = await devices_collection.find_one({"device_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    history = await control_service.get_device_history(device_id, hours)
    return {
        "device_id": device_id,
        "period_hours": hours,
        "data": history,
        "count": len(history)
    }


@router.get("/{device_id}/operations")
async def get_device_operations(
    device_id: str,
    limit: int = Query(50, ge=1, le=200)
):
    from backend.services.control_service import control_service
    
    device = await devices_collection.find_one({"device_id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    operations = await control_service.get_operation_history(device_id, limit)
    return {
        "device_id": device_id,
        "operations": operations,
        "count": len(operations)
    }


@router.get("/statistics/summary")
async def get_device_statistics():
    pipeline = [
        {"$group": {
            "_id": {"type": "$type", "status": "$status"},
            "count": {"$sum": 1}
        }}
    ]
    
    results = await devices_collection.aggregate(pipeline).to_list(length=100)
    
    summary = {}
    for result in results:
        device_type = result["_id"]["type"]
        status = result["_id"]["status"]
        count = result["count"]
        
        if device_type not in summary:
            summary[device_type] = {"total": 0, "normal": 0, "warning": 0, "fault": 0}
        
        summary[device_type]["total"] += count
        if status in summary[device_type]:
            summary[device_type][status] += count
    
    pipeline2 = [
        {"$group": {
            "_id": "$chamber",
            "count": {"$sum": 1}
        }}
    ]
    
    chamber_results = await devices_collection.aggregate(pipeline2).to_list(length=100)
    chamber_summary = {item["_id"]: item["count"] for item in chamber_results}
    
    return {
        "by_type": summary,
        "by_chamber": chamber_summary,
        "total_devices": sum(s["total"] for s in summary.values())
    }
