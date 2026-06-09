from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class FireProbabilityRequest(BaseModel):
    temperature: float = Field(..., description="环境温度 (°C)")
    temp_rate: float = Field(..., description="温度变化率 (°C/min)")
    smoke_density: float = Field(..., description="烟雾密度 (%)")
    temp_smoke_correlation: float = Field(0.0, description="温度-烟雾相关性", ge=-1.0, le=1.0)


class FireProbabilityResponse(BaseModel):
    success: bool
    fire_probability: Optional[float] = None
    risk_level: Optional[str] = None
    factors: Optional[Dict[str, bool]] = None
    processing_time_ms: Optional[float] = None
    error: Optional[str] = None


class InferenceServiceStatus(BaseModel):
    status: str
    port: Optional[int] = None
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    requests_processed: Optional[int] = None
    average_response_time_ms: Optional[float] = None
