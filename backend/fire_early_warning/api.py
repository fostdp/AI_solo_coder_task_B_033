import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta

from backend.config import settings
from backend.models.schemas import FireSensorData
from backend.models.database import (
    fire_alerts_collection,
    fire_zone_status_collection,
    sensor_data_collection,
    serialize_document,
    serialize_documents
)
from fire_early_warning.core import fire_early_warning
from fire_early_warning.inference_service import (
    is_service_running,
    get_service_status,
    start_inference_service,
    stop_inference_service,
    call_inference_service
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fire", tags=["fire"])


@router.post("/data")
async def receive_fire_sensor_data(data: FireSensorData):
    result = await fire_early_warning.process_fire_sensor_data(data)

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Unknown error"))

    return {
        "status": "success",
        **result
    }


@router.post("/data/batch")
async def receive_fire_sensor_batch(datas: List[FireSensorData]):
    results = []
    for data in datas:
        try:
            result = await fire_early_warning.process_fire_sensor_data(data)
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing fire data {data.device_id}: {e}")
            results.append({"status": "error", "device_id": data.device_id, "error": str(e)})

    success_count = sum(1 for r in results if r.get("status") == "success")
    return {
        "status": "success",
        "total_received": len(datas),
        "success_count": success_count,
        "failed_count": len(datas) - success_count,
        "results": results
    }


@router.get("/alerts/active")
async def get_active_fire_alerts(
    limit: int = Query(20, ge=1, le=100)
):
    alerts = await fire_early_warning.get_active_fire_alerts(limit)
    return {
        "alerts": alerts,
        "count": len(alerts)
    }


@router.get("/alerts")
async def get_fire_alerts(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    risk_level: Optional[str] = None,
    chamber: Optional[str] = None,
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
    if chamber:
        query["chamber"] = chamber

    alerts = await fire_alerts_collection.find(query).sort(
        "timestamp", -1
    ).limit(limit).to_list(length=limit)

    return {
        "alerts": serialize_documents(alerts),
        "count": len(alerts),
        "query": query
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_fire_alert(alert_id: str):
    success = await fire_early_warning.acknowledge_fire_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return {"status": "success", "alert_id": alert_id}


@router.get("/zones")
async def get_fire_zones(
    chamber: Optional[str] = None
):
    zones = await fire_early_warning.get_fire_zone_status(chamber)
    return {
        "zones": zones,
        "count": len(zones)
    }


@router.post("/zones/{zone_id}/deactivate")
async def deactivate_fire_zone(zone_id: str):
    success = await fire_early_warning.deactivate_fire_zone(zone_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    return {"status": "success", "zone_id": zone_id}


@router.get("/sensors/data")
async def get_fire_sensor_history(
    device_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(1000, ge=1, le=10000)
):
    query = {"type": "smoke_sensor"}
    if device_id:
        query["device_id"] = device_id
    if start_time or end_time:
        query["timestamp"] = {}
        if start_time:
            query["timestamp"]["$gte"] = start_time
        if end_time:
            query["timestamp"]["$lte"] = end_time

    data = await sensor_data_collection.find(query).sort(
        "timestamp", -1
    ).limit(limit).to_list(length=limit)

    return {
        "data": serialize_documents(data),
        "count": len(data),
        "query": query
    }


@router.get("/sensors/latest")
async def get_latest_fire_sensor_data(
    chamber: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500)
):
    pipeline = [
        {"$match": {"type": "smoke_sensor"}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$device_id",
            "latest_data": {"$first": "$$ROOT"}
        }}
    ]

    if chamber:
        from backend.models.database import devices_collection
        device_ids = await devices_collection.distinct(
            "device_id", {"type": "smoke_sensor", "chamber": chamber}
        )
        pipeline.insert(1, {"$match": {"device_id": {"$in": device_ids}}})

    results = await sensor_data_collection.aggregate(pipeline).to_list(length=limit)

    latest_data = []
    for result in results:
        doc = serialize_document(result["latest_data"])
        latest_data.append(doc)

    return {
        "data": latest_data,
        "count": len(latest_data)
    }


@router.get("/statistics")
async def get_fire_statistics(
    hours: int = Query(24, ge=1, le=720)
):
    start_time = datetime.utcnow() - timedelta(hours=hours)

    sensor_pipeline = [
        {"$match": {
            "type": "smoke_sensor",
            "timestamp": {"$gte": start_time}
        }},
        {"$group": {
            "_id": None,
            "avg_temperature": {"$avg": "$temperature"},
            "max_temperature": {"$max": "$temperature"},
            "avg_smoke": {"$avg": "$smoke_density"},
            "max_smoke": {"$max": "$smoke_density"},
            "count": {"$sum": 1}
        }}
    ]

    sensor_results = await sensor_data_collection.aggregate(sensor_pipeline).to_list(length=1)

    alert_pipeline = [
        {"$match": {"timestamp": {"$gte": start_time}}},
        {"$group": {
            "_id": "$risk_level",
            "count": {"$sum": 1}
        }}
    ]
    alert_results = await fire_alerts_collection.aggregate(alert_pipeline).to_list(length=10)

    alert_distribution = {r["_id"]: r["count"] for r in alert_results}

    active_alerts = await fire_alerts_collection.count_documents({"acknowledged": False})

    if not sensor_results:
        return {
            "period_hours": hours,
            "sensor_statistics": {},
            "alert_distribution": alert_distribution,
            "active_alerts": active_alerts,
            "total_readings": 0
        }

    sensor_data = sensor_results[0]

    return {
        "period_hours": hours,
        "sensor_statistics": {
            "temperature": {
                "average": round(sensor_data.get("avg_temperature", 0), 2),
                "max": round(sensor_data.get("max_temperature", 0), 2)
            },
            "smoke_density": {
                "average": round(sensor_data.get("avg_smoke", 0), 4),
                "max": round(sensor_data.get("max_smoke", 0), 4)
            }
        },
        "alert_distribution": alert_distribution,
        "active_alerts": active_alerts,
        "total_readings": sensor_data.get("count", 0)
    }


@router.get("/probability/calculate")
async def calculate_fire_probability(
    temperature: float = Query(..., ge=-40, le=200),
    temp_rate: float = Query(..., ge=0),
    smoke_density: float = Query(..., ge=0),
    correlation: float = Query(0, ge=-1, le=1)
):
    probability = None

    if is_service_running():
        try:
            result = await call_inference_service(
                temperature=temperature,
                temp_rate=temp_rate,
                smoke_density=smoke_density,
                temp_smoke_correlation=correlation
            )
            if result and result.get("success"):
                probability = result["fire_probability"]
        except Exception as e:
            logger.warning(f"Inference service call failed, using local: {e}")

    if probability is None:
        probability = fire_early_warning.bayesian_detector.calculate_fire_probability(
            temperature=temperature,
            temp_rate=temp_rate,
            smoke_density=smoke_density,
            temp_smoke_correlation=correlation
        )

    risk_level = "normal"
    if probability >= 0.9:
        risk_level = "critical"
    elif probability >= settings.FIRE_PROBABILITY_THRESHOLD:
        risk_level = "warning"
    elif probability >= 0.5:
        risk_level = "attention"

    return {
        "temperature": temperature,
        "temp_rate": temp_rate,
        "smoke_density": smoke_density,
        "correlation": correlation,
        "fire_probability": probability,
        "risk_level": risk_level,
        "threshold": settings.FIRE_PROBABILITY_THRESHOLD
    }


@router.get("/inference-service/status")
async def get_inference_service_status():
    return {
        "service_running": is_service_running(),
        "status": get_service_status()
    }


@router.post("/inference-service/start")
async def start_inference():
    success = start_inference_service()
    if success:
        return {"status": "success", "message": "Fire inference service started"}
    else:
        raise HTTPException(status_code=500, detail="Failed to start fire inference service")


@router.post("/inference-service/stop")
async def stop_inference():
    success = stop_inference_service()
    if success:
        return {"status": "success", "message": "Fire inference service stopped"}
    else:
        raise HTTPException(status_code=500, detail="Failed to stop fire inference service")


@router.get("/confirmations/pending")
async def get_pending_confirmations():
    confirmations = await fire_early_warning.get_pending_confirmations()
    return {
        "confirmations": confirmations,
        "count": len(confirmations)
    }


@router.post("/confirmations/{confirmation_id}/confirm")
async def confirm_alert(
    confirmation_id: str,
    confirmed: bool = True,
    confirmed_by: str = "system",
    confirmation_result: str = "fire_confirmed"
):
    success = await fire_early_warning.confirm_fire_alert(
        confirmation_id=confirmation_id,
        confirmed=confirmed,
        confirmed_by=confirmed_by,
        confirmation_result=confirmation_result
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Confirmation {confirmation_id} not found")
    return {
        "status": "success",
        "confirmation_id": confirmation_id,
        "confirmed": confirmed,
        "confirmation_result": confirmation_result
    }
