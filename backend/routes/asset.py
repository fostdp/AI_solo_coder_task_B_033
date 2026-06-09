import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

from backend.models.schemas import Asset, MaintenanceRecord
from backend.modules.asset_manager import asset_manager

router = APIRouter(prefix="/api/asset", tags=["asset"])


@router.post("/")
async def create_asset(asset: Asset):
    result = await asset_manager.create_asset(asset)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to create asset"))
    return {
        "status": "success",
        **result
    }


@router.get("/")
async def get_assets(
    chamber: Optional[str] = None,
    type: Optional[str] = None
):
    assets = await asset_manager.get_all_assets(chamber=chamber, asset_type=type)
    return {
        "data": assets,
        "count": len(assets),
        "query": {
            "chamber": chamber,
            "type": type
        }
    }


@router.get("/{device_id}")
async def get_asset(device_id: str):
    asset = await asset_manager.get_asset(device_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {device_id} not found")
    return {
        "data": asset
    }


@router.put("/{device_id}")
async def update_asset(device_id: str, update_data: Dict[str, Any]):
    success = await asset_manager.update_asset(device_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail=f"Asset {device_id} not found")
    return {
        "status": "success",
        "message": f"Asset {device_id} updated successfully"
    }


@router.post("/maintenance")
async def record_maintenance(record: MaintenanceRecord):
    result = await asset_manager.record_maintenance(record)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to record maintenance"))
    return {
        "status": "success",
        **result
    }


@router.get("/{device_id}/maintenance")
async def get_maintenance_history(
    device_id: str,
    limit: int = Query(50, ge=1, le=200)
):
    records = await asset_manager.get_maintenance_history(device_id, limit=limit)
    return {
        "data": records,
        "count": len(records),
        "device_id": device_id
    }


@router.get("/{device_id}/life-prediction")
async def get_life_prediction(device_id: str):
    prediction = await asset_manager.predict_remaining_life(device_id)
    if not prediction:
        raise HTTPException(status_code=404, detail=f"Asset {device_id} not found")
    return {
        "data": prediction.dict()
    }


@router.get("/batch-life-prediction")
async def get_batch_life_prediction():
    predictions = await asset_manager.batch_predict_life()
    prediction_data = [p.dict() for p in predictions]
    return {
        "data": prediction_data,
        "count": len(prediction_data)
    }


@router.get("/maintenance-plan/{year}/{month}")
async def generate_maintenance_plan(year: int, month: int):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
    plan = await asset_manager.generate_monthly_maintenance_plan(year, month)
    return {
        "status": "success",
        "data": plan.dict()
    }


@router.get("/maintenance-plans")
async def get_maintenance_plans(
    year: Optional[int] = None,
    month: Optional[int] = None
):
    plans = await asset_manager.get_maintenance_plans(year=year, month=month)
    return {
        "data": plans,
        "count": len(plans),
        "query": {
            "year": year,
            "month": month
        }
    }


@router.get("/maintenance-plan/{plan_id}")
async def get_maintenance_plan(plan_id: str):
    plan = await asset_manager.get_maintenance_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Maintenance plan {plan_id} not found")
    return {
        "data": plan
    }
