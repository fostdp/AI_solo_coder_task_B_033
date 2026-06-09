import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from asset_manager.core import asset_manager
from backend.models.schemas import (
    Asset,
    MaintenanceRecord,
    MaintenanceTask
)
from backend.models.database import (
    assets_collection,
    maintenance_records_collection,
    maintenance_plans_collection,
    life_predictions_collection,
    serialize_document,
    serialize_documents
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/")
async def get_all_assets(
    chamber: Optional[str] = None,
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=5000)
):
    assets = await asset_manager.get_all_assets(chamber, asset_type)

    if status:
        assets = [a for a in assets if a.get("status") == status]
        assets = assets[:limit]

    return {
        "assets": assets,
        "count": len(assets),
        "filters": {
            "chamber": chamber,
            "type": asset_type,
            "status": status
        }
    }


@router.get("/{device_id}")
async def get_asset(device_id: str):
    asset = await asset_manager.get_asset(device_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {device_id} not found")
    return asset


@router.post("/")
async def create_asset(asset: Asset):
    result = await asset_manager.create_asset(asset)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Unknown error"))
    return result


@router.put("/{device_id}")
async def update_asset(device_id: str, update_data: Dict[str, Any]):
    success = await asset_manager.update_asset(device_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail=f"Asset {device_id} not found")
    return {"status": "success", "device_id": device_id, "updated": update_data}


@router.get("/{device_id}/maintenance-history")
async def get_maintenance_history(
    device_id: str,
    limit: int = Query(50, ge=1, le=500)
):
    records = await asset_manager.get_maintenance_history(device_id, limit)
    return {
        "device_id": device_id,
        "records": records,
        "count": len(records)
    }


@router.post("/maintenance")
async def record_maintenance(record: MaintenanceRecord):
    result = await asset_manager.record_maintenance(record)
    return result


@router.get("/{device_id}/life-prediction")
async def get_life_prediction(device_id: str):
    prediction = await asset_manager.predict_remaining_life(device_id)
    if not prediction:
        raise HTTPException(status_code=404, detail=f"Asset {device_id} not found")
    return prediction.dict()


@router.post("/life-prediction/batch")
async def batch_predict_life():
    predictions = await asset_manager.batch_predict_life()
    return {
        "count": len(predictions),
        "predictions": [p.dict() for p in predictions]
    }


@router.get("/{device_id}/priority")
async def get_maintenance_priority(device_id: str):
    priority, score, reason = await asset_manager.calculate_maintenance_priority(device_id)
    return {
        "device_id": device_id,
        "priority": priority,
        "priority_score": score,
        "reason": reason
    }


@router.get("/maintenance-plans")
async def get_maintenance_plans(
    year: Optional[int] = None,
    month: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500)
):
    plans = await asset_manager.get_maintenance_plans(year, month)

    if status:
        plans = [p for p in plans if p.get("status") == status]

    return {
        "plans": plans,
        "count": len(plans),
        "filters": {
            "year": year,
            "month": month,
            "status": status
        }
    }


@router.get("/maintenance-plans/{plan_id}")
async def get_maintenance_plan(plan_id: str):
    plan = await asset_manager.get_maintenance_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return plan


@router.post("/maintenance-plans/generate")
async def generate_maintenance_plan(
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12)
):
    plan = await asset_manager.generate_monthly_maintenance_plan(year, month)
    return {
        "status": "success",
        "plan": plan.dict(exclude={"id"})
    }


@router.post("/maintenance-plans/{plan_id}/approve")
async def approve_maintenance_plan(plan_id: str):
    from bson import ObjectId

    result = await maintenance_plans_collection.update_one(
        {"plan_id": plan_id},
        {"$set": {"status": "approved", "approved_at": datetime.utcnow()}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    plan = await maintenance_plans_collection.find_one({"plan_id": plan_id})
    if plan and "tasks" in plan:
        for task in plan["tasks"]:
            if task.get("priority") == "critical":
                task_record = MaintenanceTask(**task)
                record = MaintenanceRecord(
                    record_id=f"record_{datetime.utcnow().strftime('%Y%m%d')}_{task['device_id']}",
                    device_id=task["device_id"],
                    maintenance_type=task["task_type"],
                    description=task["description"],
                    performed_by="system",
                    start_time=task["due_date"],
                    status="pending"
                )
                await maintenance_records_collection.insert_one(record.dict(exclude={"id"}))

    return {"status": "success", "plan_id": plan_id, "action": "approved"}


@router.post("/maintenance-plans/{plan_id}/execute")
async def execute_maintenance_task(
    plan_id: str,
    task_id: str,
    operator: str = "admin",
    notes: Optional[str] = None
):
    plan = await maintenance_plans_collection.find_one({"plan_id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    task_found = None
    for task in plan.get("tasks", []):
        if task.get("task_id") == task_id:
            task_found = task
            break

    if not task_found:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found in plan")

    result = await maintenance_records_collection.update_one(
        {"record_id": {"$regex": f".*{task['device_id']}$"}},
        {"$set": {
            "status": "completed",
            "end_time": datetime.utcnow(),
            "performed_by": operator,
            "notes": notes
        }}
    )

    await assets_collection.update_one(
        {"device_id": task["device_id"]},
        {
            "$set": {"last_maintenance_date": datetime.utcnow()},
            "$inc": {"maintenance_count": 1}
        }
    )

    return {
        "status": "success",
        "plan_id": plan_id,
        "task_id": task_id,
        "action": "executed"
    }


@router.get("/statistics")
async def get_asset_statistics():
    total_assets = await assets_collection.count_documents({})

    type_stats = await assets_collection.aggregate([
        {"$group": {
            "_id": "$type",
            "count": {"$sum": 1}
        }}
    ]).to_list(length=20)

    chamber_stats = await assets_collection.aggregate([
        {"$group": {
            "_id": "$chamber",
            "count": {"$sum": 1}
        }}
    ]).to_list(length=20)

    status_stats = await assets_collection.aggregate([
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]).to_list(length=10)

    now = datetime.utcnow()
    one_year_ago = now - timedelta(days=365)
    recent_maintenance = await maintenance_records_collection.count_documents({
        "start_time": {"$gte": one_year_ago}
    })

    predicted_lives = await life_predictions_collection.aggregate([
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$device_id",
            "latest": {"$first": "$$ROOT"}
        }}
    ]).to_list(length=1000)

    risk_distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for pl in predicted_lives:
        risk = pl["latest"].get("risk_level", "low")
        if risk in risk_distribution:
            risk_distribution[risk] += 1

    total_value = await assets_collection.aggregate([
        {"$group": {
            "_id": None,
            "total_value": {"$sum": "$purchase_cost"}
        }}
    ]).to_list(length=1)

    total_cost = total_value[0]["total_value"] if total_value else 0

    return {
        "total_assets": total_assets,
        "total_value": round(total_cost or 0, 2),
        "type_distribution": {t["_id"]: t["count"] for t in type_stats},
        "chamber_distribution": {c["_id"]: c["count"] for c in chamber_stats},
        "status_distribution": {s["_id"]: s["count"] for s in status_stats},
        "maintenance_last_year": recent_maintenance,
        "life_risk_distribution": risk_distribution,
        "total_life_predictions": len(predicted_lives)
    }


@router.get("/life-predictions")
async def get_life_predictions(
    risk_level: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    query = {}
    if risk_level:
        query["risk_level"] = risk_level

    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$device_id",
            "latest": {"$first": "$$ROOT"}
        }}
    ]

    results = await life_predictions_collection.aggregate(pipeline).to_list(length=limit)

    predictions = []
    for r in results:
        doc = serialize_document(r["latest"])
        if not risk_level or doc.get("risk_level") == risk_level:
            predictions.append(doc)

    return {
        "predictions": predictions,
        "count": len(predictions),
        "filter": {"risk_level": risk_level}
    }


@router.get("/reports/warranty")
async def get_warranty_report(days: int = Query(90, ge=1, le=365)):
    cutoff_date = datetime.utcnow() + timedelta(days=days)

    expiring_assets = await assets_collection.find({
        "warranty_end_date": {"$lte": cutoff_date},
        "status": "active"
    }).sort("warranty_end_date", 1).to_list(length=1000)

    return {
        "warning_days": days,
        "cutoff_date": cutoff_date.isoformat(),
        "expiring_assets": serialize_documents(expiring_assets),
        "count": len(expiring_assets)
    }


@router.get("/reports/maintenance-due")
async def get_maintenance_due_report(days: int = Query(30, ge=1, le=180)):
    assets = await assets_collection.find().to_list(length=1000)

    due_assets = []
    for asset in assets:
        last_maint = asset.get("last_maintenance_date")
        if not last_maint:
            if isinstance(asset.get("installation_date"), datetime):
                days_since_install = (datetime.utcnow() - asset["installation_date"]).days
            else:
                days_since_install = 90

            if days_since_install >= 60:
                due_assets.append({
                    "device_id": asset["device_id"],
                    "name": asset.get("name"),
                    "type": asset.get("type"),
                    "chamber": asset.get("chamber"),
                    "days_overdue": days_since_install - 60,
                    "reason": "从未维护"
                })
            continue

        if isinstance(last_maint, datetime):
            days_since = (datetime.utcnow() - last_maint).days
        else:
            days_since = (datetime.utcnow() - last_maint).days

        if days_since >= 90:
            due_assets.append({
                "device_id": asset["device_id"],
                "name": asset.get("name"),
                "type": asset.get("type"),
                "chamber": asset.get("chamber"),
                "days_since_last": days_since,
                "last_maintenance": last_maint.isoformat() if isinstance(last_maint, datetime) else str(last_maint),
                "reason": "超过维护周期"
            })

    due_assets.sort(key=lambda x: x.get("days_overdue", 0) + x.get("days_since_last", 0), reverse=True)

    return {
        "warning_days": days,
        "due_assets": due_assets,
        "count": len(due_assets)
    }


@router.get("/replacement-history")
async def get_device_replacement_history(
    device_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500)
):
    records = await asset_manager.get_device_replacement_history(device_id, limit)
    return {
        "records": records,
        "count": len(records),
        "filter": {"device_id": device_id}
    }


@router.get("/audit-logs")
async def get_asset_audit_logs(
    device_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    logs = await asset_manager.get_asset_audit_logs(device_id, action, limit)
    return {
        "logs": logs,
        "count": len(logs),
        "filters": {
            "device_id": device_id,
            "action": action
        }
    }


@router.post("/{device_id}/replace")
async def manual_device_replacement(
    device_id: str,
    replacement_data: Dict[str, Any]
):
    new_asset_data = replacement_data.get("new_asset", {})
    replacement_reason = replacement_data.get("reason", "manual_replacement")
    performed_by = replacement_data.get("performed_by", "user")

    success, replacement_record = await asset_manager.manual_device_replacement(
        device_id,
        new_asset_data,
        replacement_reason,
        performed_by
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to process device replacement"
        )

    return {
        "status": "success",
        "old_device_id": device_id,
        "new_device_id": replacement_record.new_device_id if replacement_record else None,
        "record_id": replacement_record.record_id if replacement_record else None
    }


@router.post("/scan-replacements")
async def scan_for_device_replacements():
    try:
        replaced_devices = await asset_manager.scan_for_device_replacements()
        return {
            "status": "success",
            "replaced_devices": replaced_devices,
            "count": len(replaced_devices)
        }
    except Exception as e:
        logger.error(f"Error scanning for device replacements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}/replacement-chain")
async def get_replacement_chain(device_id: str):
    try:
        chain = await asset_manager.get_replacement_chain(device_id)
        return {
            "device_id": device_id,
            "replacement_chain": chain,
            "chain_length": len(chain)
        }
    except Exception as e:
        logger.error(f"Error getting replacement chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))
