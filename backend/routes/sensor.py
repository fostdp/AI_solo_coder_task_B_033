from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import List, Optional
from datetime import datetime, timedelta

from backend.models.schemas import SensorData
from backend.models.database import (
    sensor_data_collection,
    devices_collection,
    serialize_document,
    serialize_documents
)
from backend.services.control_service import control_service

router = APIRouter(prefix="/api/sensor", tags=["sensor"])


@router.post("/data")
async def receive_sensor_data(data: SensorData):
    device = await devices_collection.find_one({"device_id": data.device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device["type"] == "env_sensor":
        data.type = "env_sensor"
    elif device["type"] == "pump":
        data.type = "pump"
    elif device["type"] == "manhole":
        data.type = "manhole"
    elif device["type"] == "fan":
        data.type = "fan"
    else:
        data.type = device["type"]
    
    if data.location is None and device.get("location"):
        from backend.models.schemas import Location
        data.location = Location(**device["location"])
    
    result = await control_service.process_sensor_data(data)
    
    return {
        "status": "success",
        **result
    }


@router.post("/data/batch")
async def receive_sensor_data_batch(datas: List[SensorData]):
    results = []
    for data in datas:
        try:
            device = await devices_collection.find_one({"device_id": data.device_id})
            if device:
                if device["type"] == "env_sensor":
                    data.type = "env_sensor"
                elif device["type"] == "pump":
                    data.type = "pump"
                elif device["type"] == "manhole":
                    data.type = "manhole"
                elif device["type"] == "fan":
                    data.type = "fan"
                else:
                    data.type = device["type"]
                
                if data.location is None and device.get("location"):
                    from backend.models.schemas import Location
                    data.location = Location(**device["location"])
                
                result = await control_service.process_sensor_data(data)
                results.append({"device_id": data.device_id, "status": "success", **result})
            else:
                results.append({"device_id": data.device_id, "status": "error", "reason": "Device not found"})
        except Exception as e:
            results.append({"device_id": data.device_id, "status": "error", "reason": str(e)})
    
    return {
        "status": "success",
        "processed": len([r for r in results if r["status"] == "success"]),
        "failed": len([r for r in results if r["status"] == "error"]),
        "results": results
    }


@router.get("/data")
async def get_sensor_data(
    device_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(1000, ge=1, le=10000)
):
    query = {}
    if device_id:
        query["device_id"] = device_id
    
    if start_time or end_time:
        query["timestamp"] = {}
        if start_time:
            query["timestamp"]["$gte"] = start_time
        if end_time:
            query["timestamp"]["$lte"] = end_time
    
    cursor = sensor_data_collection.find(query).sort("timestamp", -1).limit(limit)
    data = await cursor.to_list(length=limit)
    
    return {
        "data": serialize_documents(data),
        "count": len(data),
        "query": query
    }


@router.get("/data/latest")
async def get_latest_sensor_data(
    device_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$device_id",
            "latest_data": {"$first": "$$ROOT"}
        }}
    ]
    
    if device_type:
        pipeline.insert(0, {"$match": {"type": device_type}})
    
    results = await sensor_data_collection.aggregate(pipeline).to_list(length=limit)
    
    latest_data = []
    for result in results:
        doc = serialize_document(result["latest_data"])
        latest_data.append(doc)
    
    return {
        "data": latest_data,
        "count": len(latest_data)
    }


@router.get("/data/average")
async def get_average_sensor_data(
    hours: int = Query(1, ge=1, le=168),
    chamber: Optional[str] = None
):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    
    pipeline = [
        {"$match": {
            "timestamp": {"$gte": start_time, "$lte": end_time},
            "type": "env_sensor"
        }},
        {"$group": {
            "_id": None,
            "avg_temperature": {"$avg": "$temperature"},
            "avg_humidity": {"$avg": "$humidity"},
            "avg_oxygen": {"$avg": "$oxygen"},
            "avg_methane": {"$avg": "$methane"},
            "avg_h2s": {"$avg": "$h2s"},
            "max_temperature": {"$max": "$temperature"},
            "min_oxygen": {"$min": "$oxygen"},
            "max_methane": {"$max": "$methane"},
            "max_h2s": {"$max": "$h2s"},
            "count": {"$sum": 1}
        }}
    ]
    
    if chamber:
        device_pipeline = [
            {"$match": {"chamber": chamber, "type": "env_sensor"}},
            {"$project": {"device_id": 1, "_id": 0}}
        ]
        devices = await devices_collection.aggregate(device_pipeline).to_list(length=1000)
        device_ids = [d["device_id"] for d in devices]
        pipeline[0]["$match"]["device_id"] = {"$in": device_ids}
    
    results = await sensor_data_collection.aggregate(pipeline).to_list(length=1)
    
    if not results:
        return {
            "period_hours": hours,
            "chamber": chamber,
            "averages": {},
            "count": 0
        }
    
    result = results[0]
    
    return {
        "period_hours": hours,
        "chamber": chamber,
        "averages": {
            "temperature": round(result.get("avg_temperature", 0), 2),
            "humidity": round(result.get("avg_humidity", 0), 2),
            "oxygen": round(result.get("avg_oxygen", 0), 2),
            "methane": round(result.get("avg_methane", 0), 4),
            "h2s": round(result.get("avg_h2s", 0), 2)
        },
        "extremes": {
            "max_temperature": round(result.get("max_temperature", 0), 2),
            "min_oxygen": round(result.get("min_oxygen", 0), 2),
            "max_methane": round(result.get("max_methane", 0), 4),
            "max_h2s": round(result.get("max_h2s", 0), 2)
        },
        "count": result.get("count", 0),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    }
