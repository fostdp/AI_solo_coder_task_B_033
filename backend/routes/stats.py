from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta

from backend.services.control_service import control_service
from backend.models.database import (
    health_scores_collection,
    serialize_documents
)

router = APIRouter(prefix="/api/stats", tags=["statistics"])


@router.get("/health-score")
async def get_health_score(calculate_new: bool = True):
    if calculate_new:
        result = await control_service.calculate_health_score()
        return result
    else:
        latest = await health_scores_collection.find_one(
            sort=[("timestamp", -1)]
        )
        if latest:
            from backend.models.database import serialize_document
            return serialize_document(latest)
        else:
            result = await control_service.calculate_health_score()
            return result


@router.get("/health-score/history")
async def get_health_score_history(
    days: int = Query(7, ge=1, le=90)
):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    cursor = health_scores_collection.find({
        "timestamp": {"$gte": start_time, "$lte": end_time}
    }).sort("timestamp", 1)
    
    scores = await cursor.to_list(length=1008)
    
    return {
        "period_days": days,
        "scores": serialize_documents(scores),
        "count": len(scores),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    }


@router.get("/fault-statistics")
async def get_fault_statistics(
    months: int = Query(1, ge=1, le=12)
):
    stats = await control_service.get_fault_statistics(months=months)
    return stats


@router.get("/dashboard")
async def get_dashboard_data():
    health_score = await control_service.calculate_health_score()
    fault_stats = await control_service.get_fault_statistics(months=1)
    
    from backend.models.database import devices_collection
    from backend.services.alert_service import alert_service
    
    active_alerts = await alert_service.get_active_alerts()
    
    device_stats = await devices_collection.aggregate([
        {"$group": {
            "_id": "$type",
            "total": {"$sum": 1},
            "normal": {"$sum": {"$cond": [{"$eq": ["$status", "normal"]}, 1, 0]}},
            "warning": {"$sum": {"$cond": [{"$eq": ["$status", "warning"]}, 1, 0]}},
            "fault": {"$sum": {"$cond": [{"$eq": ["$status", "fault"]}, 1, 0]}}
        }}
    ]).to_list(length=100)
    
    running_fans = await devices_collection.count_documents({
        "type": "fan",
        "properties.running": True
    })
    
    running_pumps = await devices_collection.count_documents({
        "type": "pump",
        "properties.running": True
    })
    
    from backend.routes.sensor import get_average_sensor_data
    avg_data = await get_average_sensor_data(hours=1)
    
    return {
        "health_score": health_score,
        "fault_statistics": fault_stats,
        "active_alerts": {
            "count": len(active_alerts),
            "alerts": active_alerts[:10]
        },
        "device_status": {item["_id"]: item for item in device_stats},
        "equipment_status": {
            "fans_running": running_fans,
            "pumps_running": running_pumps
        },
        "environment_average": avg_data,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/sms/send")
async def send_sms(message: dict):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Simulated SMS sent: {message.get('message')} to {message.get('phones')}")
    
    return {
        "status": "success",
        "simulated": True,
        "message": message.get("message"),
        "phones": message.get("phones"),
        "timestamp": datetime.utcnow().isoformat()
    }
