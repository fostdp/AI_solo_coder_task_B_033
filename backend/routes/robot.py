import logging
from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from backend.models.schemas import RobotPosition
from backend.modules.robot_inspector import robot_inspector

router = APIRouter(prefix="/api/robot", tags=["robot"])


class PlanMissionRequest(BaseModel):
    robot_id: str
    start_km: float
    end_km: float
    chamber: str
    inspection_points: Optional[List[float]] = None


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
        raise HTTPException(status_code=404, detail="Robot not found")
    return {
        "robot": robot
    }


@router.post("/plan")
async def create_inspection_plan(request: PlanMissionRequest):
    try:
        mission = await robot_inspector.plan_path(
            robot_id=request.robot_id,
            start_km=request.start_km,
            end_km=request.end_km,
            chamber=request.chamber,
            inspection_points=request.inspection_points
        )
        return {
            "status": "success",
            "mission": mission.model_dump(exclude={"id"})
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/mission/{mission_id}/start")
async def start_mission(mission_id: str):
    result = await robot_inspector.start_mission(mission_id)
    if not result:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {
        "status": "success",
        "mission_id": mission_id
    }


@router.post("/{robot_id}/pause")
async def pause_robot(robot_id: str):
    result = await robot_inspector.pause_robot(robot_id)
    if not result:
        raise HTTPException(status_code=404, detail="Robot not found")
    return {
        "status": "success",
        "robot_id": robot_id,
        "message": "Robot paused"
    }


@router.post("/{robot_id}/resume")
async def resume_robot(robot_id: str):
    result = await robot_inspector.resume_robot(robot_id)
    if not result:
        raise HTTPException(status_code=404, detail="Robot not found")
    return {
        "status": "success",
        "robot_id": robot_id,
        "message": "Robot resumed"
    }


@router.post("/{robot_id}/return")
async def return_to_base(robot_id: str):
    result = await robot_inspector.return_to_base(robot_id)
    if not result:
        raise HTTPException(status_code=404, detail="Robot not found")
    return {
        "status": "success",
        "robot_id": robot_id,
        "message": "Robot returning to base"
    }


@router.get("/missions")
async def get_active_missions():
    missions = await robot_inspector.get_active_missions()
    return {
        "missions": missions,
        "count": len(missions)
    }


@router.get("/mission/{mission_id}")
async def get_mission(mission_id: str):
    mission = await robot_inspector.get_mission(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {
        "mission": mission
    }


@router.get("/{robot_id}/trajectory")
async def get_robot_trajectory(
    robot_id: str,
    hours: int = Query(1, ge=1, le=168)
):
    trajectory = await robot_inspector.get_robot_trajectory(robot_id, hours)
    return {
        "robot_id": robot_id,
        "period_hours": hours,
        "trajectory": trajectory,
        "count": len(trajectory)
    }


@router.post("/position")
async def update_robot_position(position: RobotPosition):
    result = await robot_inspector.update_robot_position(position)
    return {
        "status": "success",
        **result
    }
