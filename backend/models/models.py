from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class DeviceType(str, Enum):
    ENV_SENSOR = "env_sensor"
    MANHOLE = "manhole"
    FAN = "fan"
    PUMP = "pump"


class DeviceStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    FAULT = "fault"
    OFFLINE = "offline"


class CabinType(str, Enum):
    POWER = "power"
    WATER = "water"
    GAS = "gas"


class EnvironmentData(BaseModel):
    device_id: str
    cabin: CabinType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    temperature: float
    humidity: float
    oxygen: float
    methane: float
    hydrogen_sulfide: float
    rssi: Optional[int] = None


class EnvironmentDataBatch(BaseModel):
    data: List[EnvironmentData]
    gateway_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ManholeData(BaseModel):
    device_id: str
    cabin: CabinType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_open: bool
    is_legal: bool = True
    battery_level: Optional[float] = None


class ManholeDataBatch(BaseModel):
    data: List[ManholeData]
    gateway_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FanData(BaseModel):
    device_id: str
    cabin: CabinType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_running: bool
    speed: int
    current: Optional[float] = None
    vibration: Optional[float] = None


class PumpData(BaseModel):
    device_id: str
    cabin: CabinType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_running: bool
    level: float
    flow_rate: Optional[float] = None
    current: Optional[float] = None


class AlarmType(str, Enum):
    GAS_LEVEL1 = "gas_level1"
    GAS_LEVEL2 = "gas_level2"
    SUFFOCATION = "suffocation"
    SECURITY = "security"
    TEMPERATURE = "temperature"
    EQUIPMENT = "equipment"


class AlarmLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Alarm(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    alarm_type: AlarmType
    level: AlarmLevel
    device_id: str
    cabin: CabinType
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None


class OperationHistory(BaseModel):
    device_id: str
    operation: str
    operator: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    parameters: Optional[dict] = None


class Device(BaseModel):
    device_id: str
    name: str
    type: DeviceType
    cabin: CabinType
    location: List[float]
    status: DeviceStatus = DeviceStatus.NORMAL
    description: Optional[str] = None
    last_update: Optional[datetime] = None
