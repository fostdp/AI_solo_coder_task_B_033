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
    geo_type = "Point"
    coordinates: List[float]
    
    __annotations__ = {
        'geo_type': str,
        'coordinates': List[float],
    }

    class Config:
        arbitrary_types_allowed = True
    
    @property
    def type(self) -> str:
        return self.geo_type
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "type" in obj and "geo_type" not in obj:
                obj["geo_type"] = obj.pop("type")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "geo_type" in data:
            data["type"] = data.pop("geo_type")
        return data


class SensorData(BaseModel):
    device_id: str
    data_type = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    temperature = None
    humidity = None
    oxygen = None
    methane = None
    h2s = None
    level = None
    cover_open = None
    running = None
    speed = None
    location = None
    strain = None
    temperature_rate = None
    smoke_density = None
    crack_width = None
    fiber_temperature = None
    robot_battery = None
    robot_speed = None
    distance_km = None
    
    __annotations__ = {
        'device_id': str,
        'data_type': Optional[str],
        'timestamp': datetime,
        'temperature': Optional[float],
        'humidity': Optional[float],
        'oxygen': Optional[float],
        'methane': Optional[float],
        'h2s': Optional[float],
        'level': Optional[float],
        'cover_open': Optional[bool],
        'running': Optional[bool],
        'speed': Optional[int],
        'location': Optional[Location],
        'strain': Optional[float],
        'temperature_rate': Optional[float],
        'smoke_density': Optional[float],
        'crack_width': Optional[float],
        'fiber_temperature': Optional[float],
        'robot_battery': Optional[float],
        'robot_speed': Optional[float],
        'distance_km': Optional[float],
    }

    class Config:
        arbitrary_types_allowed = True
    
    @property
    def type(self) -> Optional[str]:
        return self.data_type
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "type" in obj and "data_type" not in obj:
                obj["data_type"] = obj.pop("type")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "data_type" in data:
            data["type"] = data.pop("data_type")
        return data


class Device(BaseModel):
    id = None
    device_id: str
    device_type: DeviceType
    chamber: str
    name: str
    status: DeviceStatus = DeviceStatus.NORMAL
    distance_km: float
    location: Location
    properties: Dict[str, Any] = {}
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'device_id': str,
        'device_type': DeviceType,
        'chamber': str,
        'name': str,
        'status': DeviceStatus,
        'distance_km': float,
        'location': Location,
        'properties': Dict[str, Any],
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @property
    def type(self) -> DeviceType:
        return self.device_type
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
            if "type" in obj and "device_type" not in obj:
                obj["device_type"] = obj.pop("type")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "device_type" in data:
            data["type"] = data.pop("device_type")
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class Alert(BaseModel):
    id = None
    device_id: str
    level: AlertLevel
    alert_type: str
    message: str
    value: float
    threshold: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'device_id': str,
        'level': AlertLevel,
        'alert_type': str,
        'message': str,
        'value': float,
        'threshold': float,
        'timestamp': datetime,
        'acknowledged': bool,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @property
    def type(self) -> str:
        return self.alert_type
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
            if "type" in obj and "alert_type" not in obj:
                obj["alert_type"] = obj.pop("type")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "alert_type" in data:
            data["type"] = data.pop("alert_type")
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class ControlCommand(BaseModel):
    id = None
    device_id: str
    command: str
    parameters: Dict[str, Any] = {}
    source: str = "automatic"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'device_id': str,
        'command': str,
        'parameters': Dict[str, Any],
        'source': str,
        'timestamp': datetime,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class OperationLog(BaseModel):
    id = None
    device_id: str
    action: str
    details: Dict[str, Any] = {}
    operator: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'device_id': str,
        'action': str,
        'details': Dict[str, Any],
        'operator': str,
        'timestamp': datetime,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class HealthScore(BaseModel):
    id = None
    score: float
    details: Dict[str, float]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'score': float,
        'details': Dict[str, float],
        'timestamp': datetime,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class TunnelFeature(BaseModel):
    feature_type: str
    properties: Dict[str, Any]
    geometry: Dict[str, Any]
    
    __annotations__ = {
        'feature_type': str,
        'properties': Dict[str, Any],
        'geometry': Dict[str, Any],
    }

    class Config:
        arbitrary_types_allowed = True
        schema_extra = {
            "example": {
                "type": "Feature",
                "properties": {"name": "管廊段"},
                "geometry": {"type": "LineString", "coordinates": [[116.4, 39.9], [116.5, 39.9]]}
            }
        }
    
    @property
    def type(self) -> str:
        return self.feature_type
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "type" in obj and "feature_type" not in obj:
                obj["feature_type"] = obj.pop("type")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "feature_type" in data:
            data["type"] = data.pop("feature_type")
        return data


class FanControlParams(BaseModel):
    running: bool
    speed: int
    
    __annotations__ = {
        'running': bool,
        'speed': int,
    }

    @validator('speed')
    def speed_between_0_and_100(cls, v):
        if v < 0 or v > 100:
            raise ValueError('Speed must be between 0 and 100')
        return v


class PumpControlParams(BaseModel):
    running: bool
    
    __annotations__ = {
        'running': bool,
    }


class FiberSensorData(BaseModel):
    device_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    strain: float
    fiber_temperature: float
    crack_width = None
    distance_km: float
    location: Location
    
    __annotations__ = {
        'device_id': str,
        'timestamp': datetime,
        'strain': float,
        'fiber_temperature': float,
        'crack_width': Optional[float],
        'distance_km': float,
        'location': Location,
    }


class StructureHeatmapPoint(BaseModel):
    distance_km: float
    strain: float
    fiber_temperature: float
    risk_level: str
    location: Location
    
    __annotations__ = {
        'distance_km': float,
        'strain': float,
        'fiber_temperature': float,
        'risk_level': str,
        'location': Location,
    }


class StructureAlert(BaseModel):
    id = None
    device_id: str
    distance_km: float
    strain: float
    threshold: float
    crack_width = None
    risk_level: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'device_id': str,
        'distance_km': float,
        'strain': float,
        'threshold': float,
        'crack_width': Optional[float],
        'risk_level': str,
        'message': str,
        'timestamp': datetime,
        'acknowledged': bool,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class InspectionRobot(BaseModel):
    id = None
    robot_id: str
    name: str
    status: str
    battery: float
    current_distance_km: float
    location: Location
    current_waypoint = None
    total_waypoints = None
    mission_id = None
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'robot_id': str,
        'name': str,
        'status': str,
        'battery': float,
        'current_distance_km': float,
        'location': Location,
        'current_waypoint': Optional[int],
        'total_waypoints': Optional[int],
        'mission_id': Optional[str],
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class Waypoint(BaseModel):
    distance_km: float
    location: Location
    action: str = "inspect"
    estimated_time: float
    waypoint_id: int
    
    __annotations__ = {
        'distance_km': float,
        'location': Location,
        'action': str,
        'estimated_time': float,
        'waypoint_id': int,
    }


class InspectionMission(BaseModel):
    id = None
    mission_id: str
    robot_id: str
    name: str
    waypoints: List[Waypoint]
    start_time = None
    end_time = None
    status: str = "pending"
    avoided_areas: List[Dict[str, Any]] = []
    priority: int = 1
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'mission_id': str,
        'robot_id': str,
        'name': str,
        'waypoints': List[Waypoint],
        'start_time': Optional[datetime],
        'end_time': Optional[datetime],
        'status': str,
        'avoided_areas': List[Dict[str, Any]],
        'priority': int,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class RobotPosition(BaseModel):
    robot_id: str
    distance_km: float
    location: Location
    battery: float
    speed: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "moving"
    
    __annotations__ = {
        'robot_id': str,
        'distance_km': float,
        'location': Location,
        'battery': float,
        'speed': float,
        'timestamp': datetime,
        'status': str,
    }


class FireSensorData(BaseModel):
    device_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    temperature: float
    temperature_rate: float
    smoke_density: float
    location: Location
    
    __annotations__ = {
        'device_id': str,
        'timestamp': datetime,
        'temperature': float,
        'temperature_rate': float,
        'smoke_density': float,
        'location': Location,
    }


class FireAlert(BaseModel):
    id = None
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
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'alert_id': str,
        'chamber': str,
        'distance_km': float,
        'probability': float,
        'temperature': float,
        'smoke_density': float,
        'risk_level': str,
        'message': str,
        'is_equipment_overheat': bool,
        'timestamp': datetime,
        'acknowledged': bool,
        'actions_taken': List[str],
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class FireZoneStatus(BaseModel):
    zone_id: str
    chamber: str
    start_distance_km: float
    end_distance_km: float
    fire_door_status: str
    extinguisher_status: str
    temperature: float
    smoke_density: float
    
    __annotations__ = {
        'zone_id': str,
        'chamber': str,
        'start_distance_km': float,
        'end_distance_km': float,
        'fire_door_status': str,
        'extinguisher_status': str,
        'temperature': float,
        'smoke_density': float,
    }


class Asset(BaseModel):
    id = None
    device_id: str
    name: str
    asset_type: str
    manufacturer: str
    model: str
    serial_number: str
    installation_date: datetime
    design_life_years: float
    last_maintenance_date = None
    purchase_cost = None
    location: Location
    chamber: str
    specifications: Dict[str, Any] = {}
    status: str = "active"
    warranty_end_date = None
    maintenance_count: int = 0
    failure_count: int = 0
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'device_id': str,
        'name': str,
        'asset_type': str,
        'manufacturer': str,
        'model': str,
        'serial_number': str,
        'installation_date': datetime,
        'design_life_years': float,
        'last_maintenance_date': Optional[datetime],
        'purchase_cost': Optional[float],
        'location': Location,
        'chamber': str,
        'specifications': Dict[str, Any],
        'status': str,
        'warranty_end_date': Optional[datetime],
        'maintenance_count': int,
        'failure_count': int,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @property
    def type(self) -> str:
        return self.asset_type
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
            if "type" in obj and "asset_type" not in obj:
                obj["asset_type"] = obj.pop("type")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "asset_type" in data:
            data["type"] = data.pop("asset_type")
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class MaintenanceRecord(BaseModel):
    id = None
    record_id: str
    device_id: str
    maintenance_type: str
    description: str
    performed_by: str
    start_time: datetime
    end_time = None
    parts_replaced: List[str] = []
    cost = None
    notes = None
    status: str = "pending"
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'record_id': str,
        'device_id': str,
        'maintenance_type': str,
        'description': str,
        'performed_by': str,
        'start_time': datetime,
        'end_time': Optional[datetime],
        'parts_replaced': List[str],
        'cost': Optional[float],
        'notes': Optional[str],
        'status': str,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class RemainingLifePrediction(BaseModel):
    device_id: str
    predicted_life_years: float
    confidence: float
    key_factors: List[str]
    risk_level: str
    recommendation: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'device_id': str,
        'predicted_life_years': float,
        'confidence': float,
        'key_factors': List[str],
        'risk_level': str,
        'recommendation': str,
        'timestamp': datetime,
    }


class MaintenancePlan(BaseModel):
    id = None
    plan_id: str
    month: str
    year: int
    tasks: List[Dict[str, Any]] = []
    total_tasks: int = 0
    priority_distribution: Dict[str, int] = {}
    estimated_cost: float = 0.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "draft"
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'plan_id': str,
        'month': str,
        'year': int,
        'tasks': List[Dict[str, Any]],
        'total_tasks': int,
        'priority_distribution': Dict[str, int],
        'estimated_cost': float,
        'generated_at': datetime,
        'status': str,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


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
    
    __annotations__ = {
        'task_id': str,
        'device_id': str,
        'device_name': str,
        'task_type': str,
        'priority': str,
        'description': str,
        'due_date': datetime,
        'estimated_duration_hours': float,
        'parts_needed': List[str],
        'risk_level': str,
        'reason': str,
    }


class TopologyNode(BaseModel):
    node_id: str
    distance_km: float
    chamber: str
    location: Location
    node_type: str = "normal"
    connections: List[str] = []
    properties: Dict[str, Any] = {}
    
    __annotations__ = {
        'node_id': str,
        'distance_km': float,
        'chamber': str,
        'location': Location,
        'node_type': str,
        'connections': List[str],
        'properties': Dict[str, Any],
    }


class TopologyEdge(BaseModel):
    edge_id: str
    from_node: str
    to_node: str
    distance: float
    safety_score: float = 1.0
    energy_cost: float = 1.0
    time_cost: float = 1.0
    properties: Dict[str, Any] = {}
    
    __annotations__ = {
        'edge_id': str,
        'from_node': str,
        'to_node': str,
        'distance': float,
        'safety_score': float,
        'energy_cost': float,
        'time_cost': float,
        'properties': Dict[str, Any],
    }


class TopologyMap(BaseModel):
    id = None
    map_id: str
    name: str
    nodes: List[TopologyNode] = []
    edges: List[TopologyEdge] = []
    branch_points: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'map_id': str,
        'name': str,
        'nodes': List[TopologyNode],
        'edges': List[TopologyEdge],
        'branch_points': List[str],
        'created_at': datetime,
        'updated_at': datetime,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class PathPlanningResult(BaseModel):
    plan_id: str
    robot_id: str
    start_node: str
    end_node: str
    waypoints: List[Waypoint] = []
    total_distance: float
    total_energy: float
    total_time: float
    safety_score: float
    path_score: float
    attempt_count: int
    status: str = "success"
    fallback_reason = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'plan_id': str,
        'robot_id': str,
        'start_node': str,
        'end_node': str,
        'waypoints': List[Waypoint],
        'total_distance': float,
        'total_energy': float,
        'total_time': float,
        'safety_score': float,
        'path_score': float,
        'attempt_count': int,
        'status': str,
        'fallback_reason': Optional[str],
        'timestamp': datetime,
    }


class BranchStabilityResult(BaseModel):
    node_id: str
    stability_score: float
    sensor_readings: Dict[str, float] = {}
    sensor_weights: Dict[str, float] = {}
    is_stable: bool
    recommended_path = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'node_id': str,
        'stability_score': float,
        'sensor_readings': Dict[str, float],
        'sensor_weights': Dict[str, float],
        'is_stable': bool,
        'recommended_path': Optional[str],
        'timestamp': datetime,
    }


class HeatSourceFeature(BaseModel):
    device_id: str
    temperature_max: float
    temperature_min: float
    temperature_mean: float
    temperature_std: float
    temp_distribution_score: float
    duration_minutes: float
    smoke_mean: float
    temp_smoke_correlation: float
    fluctuation_frequency: float
    is_periodic: bool = False
    
    __annotations__ = {
        'device_id': str,
        'temperature_max': float,
        'temperature_min': float,
        'temperature_mean': float,
        'temperature_std': float,
        'temp_distribution_score': float,
        'duration_minutes': float,
        'smoke_mean': float,
        'temp_smoke_correlation': float,
        'fluctuation_frequency': float,
        'is_periodic': bool,
    }


class WeldingDetectionResult(BaseModel):
    device_id: str
    is_welding: bool
    confidence: float
    temp_fluctuation_score: float
    periodicity_score: float
    smoke_level_score: float
    reasons: List[str] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'device_id': str,
        'is_welding': bool,
        'confidence': float,
        'temp_fluctuation_score': float,
        'periodicity_score': float,
        'smoke_level_score': float,
        'reasons': List[str],
        'timestamp': datetime,
    }


class FireAlertConfirmation(BaseModel):
    id = None
    confirmation_id: str
    alert_id: str
    chamber: str
    distance_km: float
    risk_level: str
    requires_confirmation: bool = True
    confirmed: bool = False
    confirmed_by = None
    confirmed_at = None
    confirmation_result = None
    timeout_seconds: int = 300
    auto_upgraded: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'confirmation_id': str,
        'alert_id': str,
        'chamber': str,
        'distance_km': float,
        'risk_level': str,
        'requires_confirmation': bool,
        'confirmed': bool,
        'confirmed_by': Optional[str],
        'confirmed_at': Optional[datetime],
        'confirmation_result': Optional[str],
        'timeout_seconds': int,
        'auto_upgraded': bool,
        'created_at': datetime,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class DeviceReplacementRecord(BaseModel):
    id = None
    record_id: str
    old_device_id: str
    new_device_id: str
    old_serial_number: str
    new_serial_number: str
    replacement_reason: str
    replacement_time: datetime = Field(default_factory=datetime.utcnow)
    performed_by = None
    old_asset_status: str = "decommissioned"
    new_asset_status: str = "active"
    property_changes: Dict[str, Any] = {}
    notes = None
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'record_id': str,
        'old_device_id': str,
        'new_device_id': str,
        'old_serial_number': str,
        'new_serial_number': str,
        'replacement_reason': str,
        'replacement_time': datetime,
        'performed_by': Optional[str],
        'old_asset_status': str,
        'new_asset_status': str,
        'property_changes': Dict[str, Any],
        'notes': Optional[str],
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data


class AssetAuditLog(BaseModel):
    id = None
    log_id: str
    device_id: str
    action: str
    field_name = None
    old_value = None
    new_value = None
    change_reason = None
    performed_by: str = "system"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    __annotations__ = {
        'id': Optional[PyObjectId],
        'log_id': str,
        'device_id': str,
        'action': str,
        'field_name': Optional[str],
        'old_value': Optional[Any],
        'new_value': Optional[Any],
        'change_reason': Optional[str],
        'performed_by': str,
        'timestamp': datetime,
    }

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    @classmethod
    def parse_obj(cls, obj):
        if isinstance(obj, dict):
            obj = dict(obj)
            if "_id" in obj and "id" not in obj:
                obj["id"] = obj.pop("_id")
        return super().parse_obj(obj)
    
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if "id" in data:
            data["_id"] = data.pop("id")
        return data
