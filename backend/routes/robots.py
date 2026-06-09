import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta

from backend.models.schemas import RobotPosition, Waypoint
from backend.models.database import (
    inspection_robots_collection,
    inspection_missions_collection,
    robot_positions_collection,
    serialize_document,
    serialize_documents
)
from backend.modules import robot_inspector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/robots", tags=["robots"])


@router.get("/")
async def get_all_robots():
    robots = await robot_inspector.get_all_robots()
    return {
        "robots": robots,
        "count": len(robots)
    }


@router.get("/{robot_id}")
async def get_robot(robot_id: str):
    robot = await robot_inspector.get_robot(robot_id)
    if not robot:
        raise HTTPException(status_code=404, detail=f"Robot {robot_id} not found")
    return robot


@router.post("/{robot_id}/position")
async def update_robot_position(position: RobotPosition):
    result = await robot_inspector.update_robot_position(position)
    return result


@router.get("/{robot_id}/trajectory")
async def get_robot_trajectory(
    robot_id: str,
    hours: int = Query(1, ge=1, le=168)
):
    positions = await robot_inspector.get_robot_trajectory(robot_id, hours)
    return {
        "robot_id": robot_id,
        "period_hours": hours,
        "trajectory": positions,
        "count": len(positions)
    }


@router.post("/{robot_id}/pause")
async def pause_robot(robot_id: str):
    success = await robot_inspector.pause_robot(robot_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Robot {robot_id} not found")
    return {"status": "success", "robot_id": robot_id, "action": "paused"}


@router.post("/{robot_id}/resume")
async def resume_robot(robot_id: str):
    success = await robot_inspector.resume_robot(robot_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Robot {robot_id} not found")
    return {"status": "success", "robot_id": robot_id, "action": "resumed"}


@router.post("/{robot_id}/return")
async def return_to_base(robot_id: str):
    success = await robot_inspector.return_to_base(robot_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Robot {robot_id} not found")
    return {"status": "success", "robot_id": robot_id, "action": "returning_to_base"}


@router.get("/missions")
async def get_missions(
    status: Optional[str] = None,
    robot_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500)
):
    query = {}
    if status:
        query["status"] = status
    if robot_id:
        query["robot_id"] = robot_id

    missions = await inspection_missions_collection.find(query).sort(
        "start_time", -1
    ).limit(limit).to_list(length=limit)

    return {
        "missions": serialize_documents(missions),
        "count": len(missions),
        "query": query
    }


@router.get("/missions/active")
async def get_active_missions():
    missions = await robot_inspector.get_active_missions()
    return {
        "missions": missions,
        "count": len(missions)
    }


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    mission = await robot_inspector.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    return mission


@router.post("/missions/plan")
async def plan_inspection_mission(
    robot_id: str,
    start_km: float = Query(..., ge=0, le=15),
    end_km: float = Query(..., ge=0, le=15),
    chamber: str = "电力舱",
    inspection_points: Optional[str] = None
):
    if end_km < start_km:
        raise HTTPException(status_code=400, detail="end_km must be >= start_km")

    points = None
    if inspection_points:
        points = [float(p) for p in inspection_points.split(",")]

    try:
        mission = await robot_inspector.plan_path(
            robot_id=robot_id,
            start_km=start_km,
            end_km=end_km,
            chamber=chamber,
            inspection_points=points
        )
        return {
            "status": "success",
            "mission": mission.model_dump(exclude={"id"})
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/missions/{mission_id}/start")
async def start_mission(mission_id: str):
    success = await robot_inspector.start_mission(mission_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found or already started")
    return {"status": "success", "mission_id": mission_id, "action": "started"}


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    from bson import ObjectId

    mission = await inspection_missions_collection.find_one({"mission_id": mission_id})
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

    result = await inspection_missions_collection.update_one(
        {"mission_id": mission_id},
        {"$set": {
            "status": "cancelled",
            "end_time": datetime.utcnow()
        }}
    )

    if mission.get("robot_id"):
        await inspection_robots_collection.update_one(
            {"robot_id": mission["robot_id"]},
            {"$set": {
                "status": "idle",
                "mission_id": None
            }}
        )

    return {
        "status": "success",
        "mission_id": mission_id,
        "action": "cancelled",
        "modified_count": result.modified_count
    }


@router.get("/positions/latest")
async def get_latest_positions():
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$robot_id",
            "latest_position": {"$first": "$$ROOT"}
        }}
    ]

    results = await robot_positions_collection.aggregate(pipeline).to_list(length=10)

    positions = []
    for result in results:
        doc = serialize_document(result["latest_position"])
        positions.append(doc)

    return {
        "positions": positions,
        "count": len(positions)
    }


@router.get("/statistics")
async def get_robot_statistics():
    total_robots = await inspection_robots_collection.count_documents({})

    status_stats = await inspection_robots_collection.aggregate([
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]).to_list(length=10)

    mission_stats = await inspection_missions_collection.aggregate([
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]).to_list(length=10)

    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    today_missions = await inspection_missions_collection.count_documents({
        "start_time": {"$gte": today_start}
    })

    return {
        "total_robots": total_robots,
        "status_distribution": {s["_id"]: s["count"] for s in status_stats},
        "mission_distribution": {m["_id"]: m["count"] for m in mission_stats},
        "today_missions": today_missions
    }
