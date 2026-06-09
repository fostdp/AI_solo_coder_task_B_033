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
    FIBER_SENSOR = "fiber_sensor"
    SMOKE_SENSOR = "smoke_sensor"
    INSPECTION_ROBOT = "inspection_robot"
    FIRE_DOOR = "fire_door"
    FIRE_EXTINGUISHER = "fire_extinguisher"


class DeviceStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    FAULT = "fault"


class AlertLevel(str, Enum):
    LEVEL1 = "level1"
    LEVEL2 = "level2"
    SECURITY = "security"
    FIRE = "fire"
    STRUCTURAL = "structural"


class Location(BaseModel):
    type_: str = Field(default="Point", alias="type", description="GeoJSON type")
    coordinates: List[float]

    class Config:
        allow_population_by_field_name = True


class SensorData(BaseModel):
    device_id: str
    type_: Optional[str] = Field(default=None, alias="type", description="Sensor data type")
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
    strain: Optional[float] = None
    temperature_rate: Optional[float] = None
    smoke_density: Optional[float] = None
    crack_width: Optional[float] = None
    fiber_temperature: Optional[float] = None
    robot_battery: Optional[float] = None
    robot_speed: Optional[float] = None
    distance_km: Optional[float] = None

    class Config:
        allow_population_by_field_name = True


class Device(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    type_: DeviceType = Field(alias="type", description="Device type")
    chamber: str
    name: str
    status: DeviceStatus = DeviceStatus.NORMAL
    distance_km: float
    location: Location
    properties: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True


class Alert(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    level: AlertLevel
    type_: str = Field(alias="type", description="Alert type")
    message: str
    value: float
    threshold: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True


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
    type_: str = Field(alias="type", description="GeoJSON feature type")
    properties: Dict[str, Any]
    geometry: Dict[str, Any]

    class Config:
        allow_population_by_field_name = True
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


class FiberSensorData(BaseModel):
    device_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    strain: float
    fiber_temperature: float
    crack_width: Optional[float] = None
    distance_km: float
    location: Location


class StructureHeatmapPoint(BaseModel):
    distance_km: float
    strain: float
    fiber_temperature: float
    risk_level: str
    location: Location


class StructureAlert(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    distance_km: float
    strain: float
    threshold: float
    crack_width: Optional[float] = None
    risk_level: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class InspectionRobot(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    robot_id: str
    name: str
    status: str
    battery: float
    current_distance_km: float
    location: Location
    current_waypoint: Optional[int] = None
    total_waypoints: Optional[int] = None
    mission_id: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Waypoint(BaseModel):
    distance_km: float
    location: Location
    action: str = "inspect"
    estimated_time: float
    waypoint_id: int


class InspectionMission(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    mission_id: str
    robot_id: str
    name: str
    waypoints: List[Waypoint]
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "pending"
    avoided_areas: List[Dict[str, Any]] = []
    priority: int = 1

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class RobotPosition(BaseModel):
    robot_id: str
    distance_km: float
    location: Location
    battery: float
    speed: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "moving"


class FireSensorData(BaseModel):
    device_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    temperature: float
    temperature_rate: float
    smoke_density: float
    location: Location


class FireAlert(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    alert_id: str
    chamber: str
    distance_km: float
    probability: float
    temperature: float
    smoke_density: float
    risk_level: str
    message: str
    is_equipment_overheat: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    actions_taken: List[str] = []

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class FireZoneStatus(BaseModel):
    zone_id: str
    chamber: str
    start_distance_km: float
    end_distance_km: float
    fire_door_status: str
    extinguisher_status: str
    temperature: float
    smoke_density: float


class Asset(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    device_id: str
    name: str
    type_: str = Field(alias="type", description="Asset type")
    manufacturer: str
    model: str
    serial_number: str
    installation_date: datetime
    design_life_years: float
    last_maintenance_date: Optional[datetime] = None
    purchase_cost: Optional[float] = None
    location: Location
    chamber: str
    specifications: Dict[str, Any] = {}
    status: str = "active"
    warranty_end_date: Optional[datetime] = None
    maintenance_count: int = 0
    failure_count: int = 0

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True


class MaintenanceRecord(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    record_id: str
    device_id: str
    maintenance_type: str
    description: str
    performed_by: str
    start_time: datetime
    end_time: Optional[datetime] = None
    parts_replaced: List[str] = []
    cost: Optional[float] = None
    notes: Optional[str] = None
    status: str = "pending"

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class RemainingLifePrediction(BaseModel):
    device_id: str
    predicted_life_years: float
    confidence: float
    key_factors: List[str]
    risk_level: str
    recommendation: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MaintenancePlan(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    plan_id: str
    month: str
    year: int
    tasks: List[Dict[str, Any]] = []
    total_tasks: int = 0
    priority_distribution: Dict[str, int] = {}
    estimated_cost: float = 0.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "draft"

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class MaintenanceTask(BaseModel):
    task_id: str
    device_id: str
    device_name: str
    task_type: str
    priority: str
    description: str
    due_date: datetime
    estimated_duration_hours: float
    parts_needed: List[str] = []
    risk_level: str
    reason: str
