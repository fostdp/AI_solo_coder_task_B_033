from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from bson import ObjectId

from backend.models.database import PyObjectId


class DeviceType(str, Enum):
    ENV_SENSOR = "env_sensor"
    MANHOLE = "manhole"
    PUMP = "pump"
    FAN = "fan"


class DeviceStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    FAULT = "fault"


class AlertLevel(str, Enum):
    LEVEL1 = "level1"
    LEVEL2 = "level2"
    SECURITY = "security"


class Location(BaseModel):
    type: str = "Point"
    coordinates: List[float]


class SensorData(BaseModel):
    device_id: str
    type: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    oxygen: Optional[float] = None
    methane: Optional[float] = None
    h2s: Optional[float] = None
    level: Optional[float] = None
    cover_open: Optional[bool] = None
    running: Optional[bool] = None
    speed: Optional[int] = None
    location: Optional[Location] = None


class Device(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    type: DeviceType
    chamber: str
    name: str
    status: DeviceStatus = DeviceStatus.NORMAL
    distance_km: float
    location: Location
    properties: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Alert(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    level: AlertLevel
    type: str
    message: str
    value: float
    threshold: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ControlCommand(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    command: str
    parameters: Dict[str, Any] = {}
    source: str = "automatic"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class OperationLog(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    action: str
    details: Dict[str, Any] = {}
    operator: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class HealthScore(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    score: float
    details: Dict[str, float]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class TunnelFeature(BaseModel):
    type: str
    properties: Dict[str, Any]
    geometry: Dict[str, Any]

    class Config:
        schema_extra = {
            "example": {
                "type": "Feature",
                "properties": {"name": "管廊段"},
                "geometry": {"type": "LineString", "coordinates": [[116.4, 39.9], [116.5, 39.9]]}
            }
        }


class FanControlParams(BaseModel):
    running: bool
    speed: int

    @validator('speed')
    def speed_between_0_and_100(cls, v):
        if v < 0 or v > 100:
            raise ValueError('Speed must be between 0 and 100')
        return v


class PumpControlParams(BaseModel):
    running: bool
