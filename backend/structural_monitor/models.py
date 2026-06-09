from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime


class FiberBreakInfo(BaseModel):
    is_break: bool
    break_position: Optional[float] = None
    strain_drop: Optional[float] = None
    severity: Optional[str] = None


class InterruptionInfo(BaseModel):
    is_interrupted: bool
    interruption_duration: Optional[float] = None
    last_timestamp: Optional[str] = None


class ProcessFiberDataResult(BaseModel):
    status: str
    risk_level: str
    alert: Optional[Dict[str, Any]] = None
    data: Dict[str, Any]
    fiber_break_info: FiberBreakInfo
    interruption_info: InterruptionInfo
