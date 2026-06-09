from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field


class PathPlanningRequest(BaseModel):
    request_id: str
    robot_id: str
    start_km: float
    end_km: float
    chamber: str
    inspection_points: Optional[List[float]] = None
    weight_override: Optional[Dict[str, float]] = None
    topology_map_data: Optional[Dict[str, Any]] = None


class PathPlanningResponse(BaseModel):
    request_id: str
    success: bool
    path: Optional[List[str]] = None
    total_distance: Optional[float] = None
    total_energy: Optional[float] = None
    total_time: Optional[float] = None
    safety_score: Optional[float] = None
    path_score: Optional[float] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None


class ProcessStatus(BaseModel):
    status: str
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    requests_processed: Optional[int] = None
    average_response_time_ms: Optional[float] = None
