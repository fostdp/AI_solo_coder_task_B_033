import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta

from backend.models.schemas import FiberSensorData
from backend.models.database import (
    fiber_sensor_data_collection,
    structure_alerts_collection,
    serialize_document,
    serialize_documents
)
from structural_monitor.core import structure_monitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/structure", tags=["structure"])


@router.post("/data")
async def receive_fiber_data(data: FiberSensorData):
    result = await structure_monitor.process_fiber_data(data)

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Unknown error"))

    return {
        "status": "success",
        **result
    }


@router.post("/data/batch")
async def receive_fiber_data_batch(datas: List[FiberSensorData]):
    results = []
    for data in datas:
        try:
            result = await structure_monitor.process_fiber_data(data)
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing fiber data {data.device_id}: {e}")
            results.append({"status": "error", "device_id": data.device_id, "error": str(e)})

    success_count = sum(1 for r in results if r.get("status") == "success")
    return {
        "status": "success",
        "total_received": len(datas),
        "success_count": success_count,
        "failed_count": len(datas) - success_count,
        "results": results
    }


@router.get("/heatmap")
async def get_structure_heatmap(
    chamber: Optional[str] = None
):
    heatmap_data = await structure_monitor.get_heatmap_data(chamber)

    return {
        "chamber": chamber,
        "count": len(heatmap_data),
        "data": [point.dict() for point in heatmap_data]
    }


@router.get("/alerts/active")
async def get_active_structure_alerts(
    limit: int = Query(50, ge=1, le=200)
):
    alerts = await structure_monitor.get_active_alerts(limit)
    return {
        "alerts": alerts,
        "count": len(alerts)
    }


@router.get("/alerts")
async def get_structure_alerts(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    risk_level: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    query = {}
    if start_time or end_time:
        query["timestamp"] = {}
        if start_time:
            query["timestamp"]["$gte"] = start_time
        if end_time:
            query["timestamp"]["$lte"] = end_time
    if risk_level:
        query["risk_level"] = risk_level

    alerts = await structure_alerts_collection.find(query).sort(
        "timestamp", -1
    ).limit(limit).to_list(length=limit)

    return {
        "alerts": serialize_documents(alerts),
        "count": len(alerts),
        "query": query
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_structure_alert(alert_id: str):
    success = await structure_monitor.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return {"status": "success", "alert_id": alert_id}


@router.get("/trend")
async def get_structure_trend(
    start_km: float = Query(0, ge=0),
    end_km: float = Query(15, ge=0),
    hours: int = Query(24, ge=1, le=720)
):
    data = await structure_monitor.get_structure_trend(start_km, end_km, hours)
    return {
        "start_km": start_km,
        "end_km": end_km,
        "hours": hours,
        "data": data,
        "count": len(data)
    }


@router.get("/data")
async def get_fiber_sensor_data(
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

    data = await fiber_sensor_data_collection.find(query).sort(
        "timestamp", -1
    ).limit(limit).to_list(length=limit)

    return {
        "data": serialize_documents(data),
        "count": len(data),
        "query": query
    }


@router.get("/data/latest")
async def get_latest_fiber_data(
    chamber: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500)
):
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$device_id",
            "latest_data": {"$first": "$$ROOT"}
        }}
    ]

    if chamber:
        from backend.models.database import devices_collection
        device_ids = await devices_collection.distinct(
            "device_id", {"type": "fiber_sensor", "chamber": chamber}
        )
        pipeline.insert(0, {"$match": {"device_id": {"$in": device_ids}}})

    results = await fiber_sensor_data_collection.aggregate(pipeline).to_list(length=limit)

    latest_data = []
    for result in results:
        doc = serialize_document(result["latest_data"])
        latest_data.append(doc)

    return {
        "data": latest_data,
        "count": len(latest_data)
    }


@router.get("/statistics")
async def get_structure_statistics(
    hours: int = Query(24, ge=1, le=720)
):
    start_time = datetime.utcnow() - timedelta(hours=hours)

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_time}}},
        {"$group": {
            "_id": None,
            "avg_strain": {"$avg": "$strain"},
            "max_strain": {"$max": "$strain"},
            "min_strain": {"$min": "$strain"},
            "avg_fiber_temp": {"$avg": "$fiber_temperature"},
            "max_fiber_temp": {"$max": "$fiber_temperature"},
            "avg_crack_width": {"$avg": "$crack_width"},
            "max_crack_width": {"$max": "$crack_width"},
            "count": {"$sum": 1}
        }}
    ]

    results = await fiber_sensor_data_collection.aggregate(pipeline).to_list(length=1)

    if not results:
        return {
            "period_hours": hours,
            "statistics": {},
            "count": 0
        }

    result = results[0]

    risk_count_pipeline = [
        {"$match": {"timestamp": {"$gte": start_time}}},
        {"$group": {
            "_id": "$risk_level",
            "count": {"$sum": 1}
        }}
    ]
    risk_counts = await fiber_sensor_data_collection.aggregate(risk_count_pipeline).to_list(length=10)

    risk_distribution = {r["_id"]: r["count"] for r in risk_counts}

    return {
        "period_hours": hours,
        "statistics": {
            "strain": {
                "average": round(result.get("avg_strain", 0), 2),
                "max": round(result.get("max_strain", 0), 2),
                "min": round(result.get("min_strain", 0), 2)
            },
            "fiber_temperature": {
                "average": round(result.get("avg_fiber_temp", 0), 2),
                "max": round(result.get("max_fiber_temp", 0), 2)
            },
            "crack_width": {
                "average": round(result.get("avg_crack_width", 0), 4),
                "max": round(result.get("max_crack_width", 0), 4)
            }
        },
        "risk_distribution": risk_distribution,
        "total_readings": result.get("count", 0)
    }
