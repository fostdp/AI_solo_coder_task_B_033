from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from backend.services.alert_service import alert_service, websocket_manager
from backend.models.database import serialize_documents
from backend.models.schemas import AlertLevel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/active")
async def get_active_alerts():
    alerts = await alert_service.get_active_alerts()
    return {
        "alerts": alerts,
        "count": len(alerts)
    }


@router.get("/history")
async def get_alert_history(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    level: Optional[AlertLevel] = None,
    device_id: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=5000)
):
    if end_time is None:
        end_time = datetime.utcnow()
    if start_time is None:
        start_time = end_time - timedelta(days=7)
    
    alerts = await alert_service.get_alert_history(start_time, end_time, level)
    
    if device_id:
        alerts = [a for a in alerts if a.get("device_id") == device_id]
    
    alerts = alerts[:limit]
    
    return {
        "alerts": alerts,
        "count": len(alerts),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    }


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, operator: str = "system"):
    result = await alert_service.acknowledge_alert(alert_id, operator)
    if not result:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "alert": result}


@router.get("/statistics")
async def get_alert_statistics(
    days: int = Query(30, ge=1, le=365)
):
    from backend.models.database import alerts_collection
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    pipeline = [
        {"$match": {
            "timestamp": {"$gte": start_time, "$lte": end_time}
        }},
        {"$group": {
            "_id": {"level": "$level", "type": "$type"},
            "count": {"$sum": 1}
        }}
    ]
    
    results = await alerts_collection.aggregate(pipeline).to_list(length=100)
    
    by_level = {"level1": 0, "level2": 0, "security": 0}
    by_type = {}
    
    for result in results:
        level = result["_id"]["level"]
        alert_type = result["_id"]["type"]
        count = result["count"]
        
        if level in by_level:
            by_level[level] += count
        
        if alert_type not in by_type:
            by_type[alert_type] = 0
        by_type[alert_type] += count
    
    daily_pipeline = [
        {"$match": {
            "timestamp": {"$gte": start_time, "$lte": end_time}
        }},
        {"$group": {
            "_id": {
                "year": {"$year": "$timestamp"},
                "month": {"$month": "$timestamp"},
                "day": {"$dayOfMonth": "$timestamp"},
                "level": "$level"
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}}
    ]
    
    daily_results = await alerts_collection.aggregate(daily_pipeline).to_list(length=1000)
    
    daily_data = {}
    for result in daily_results:
        date_key = f"{result['_id']['year']}-{result['_id']['month']:02d}-{result['_id']['day']:02d}"
        level = result["_id"]["level"]
        if date_key not in daily_data:
            daily_data[date_key] = {"date": date_key, "total": 0, "level1": 0, "level2": 0, "security": 0}
        daily_data[date_key][level] = result["count"]
        daily_data[date_key]["total"] += result["count"]
    
    daily_list = sorted(daily_data.values(), key=lambda x: x["date"])
    
    return {
        "period_days": days,
        "total_alerts": sum(by_level.values()),
        "by_level": by_level,
        "by_type": by_type,
        "daily": daily_list,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket message: {data}")
            
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
            elif data.get("type") == "get_active_alerts":
                alerts = await alert_service.get_active_alerts()
                await websocket.send_json({"type": "active_alerts", "data": alerts})
                
    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket_manager.disconnect(websocket)
