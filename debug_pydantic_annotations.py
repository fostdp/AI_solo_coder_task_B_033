from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

print("Testing __annotations__ approach with multiple fields...")

print("\n1. Multiple Optional fields with __annotations__:")
try:
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
            'location': Optional['Location'],
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
        def model_validate(cls, obj, **kwargs):
            if isinstance(obj, dict):
                obj = dict(obj)
                if "type" in obj and "data_type" not in obj:
                    obj["data_type"] = obj.pop("type")
            return super().model_validate(obj, **kwargs)
        
        def model_dump(self, **kwargs):
            data = super().model_dump(**kwargs)
            if "data_type" in data:
                data["type"] = data.pop("data_type")
            return data
        
        def dict(self, **kwargs):
            return self.model_dump(**kwargs)
    
    class Location(BaseModel):
        geo_type: str = "Point"
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
        def model_validate(cls, obj, **kwargs):
            if isinstance(obj, dict):
                obj = dict(obj)
                if "type" in obj and "geo_type" not in obj:
                    obj["geo_type"] = obj.pop("type")
            return super().model_validate(obj, **kwargs)
        
        def model_dump(self, **kwargs):
            data = super().model_dump(**kwargs)
            if "geo_type" in data:
                data["type"] = data.pop("geo_type")
            return data
        
        def dict(self, **kwargs):
            return self.model_dump(**kwargs)
    
    print("✓ SensorData and Location classes created successfully")
    
    # Test instantiation
    loc = Location(coordinates=[116.4, 39.9])
    print(f"  Location: type={loc.type}, coordinates={loc.coordinates}")
    
    sd = SensorData(
        device_id="sensor001",
        data_type="env_sensor",
        temperature=25.5,
        humidity=60.0,
        location=loc
    )
    print(f"  SensorData: device_id={sd.device_id}, type={sd.type}, temperature={sd.temperature}")
    print(f"  dict() output: {sd.dict()}")
    
    # Test model_validate with "type" field
    sd2 = SensorData.model_validate({
        "device_id": "sensor002",
        "type": "pump",
        "level": 80.0
    })
    print(f"  SensorData2: device_id={sd2.device_id}, type={sd2.type}, level={sd2.level}")
    
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()

print("\n2. Testing Alert class with __annotations__:")
try:
    class AlertLevel(str):
        LEVEL1 = "level1"
        LEVEL2 = "level2"
    
    class Alert(BaseModel):
        id = None
        device_id: str
        level: str
        alert_type: str
        message: str
        value: float
        threshold: float
        timestamp: datetime = Field(default_factory=datetime.utcnow)
        acknowledged: bool = False
        
        __annotations__ = {
            'id': Optional[Any],
            'device_id': str,
            'level': str,
            'alert_type': str,
            'message': str,
            'value': float,
            'threshold': float,
            'timestamp': datetime,
            'acknowledged': bool,
        }

        class Config:
            arbitrary_types_allowed = True
        
        @property
        def type(self) -> str:
            return self.alert_type
        
        @classmethod
        def model_validate(cls, obj, **kwargs):
            if isinstance(obj, dict):
                obj = dict(obj)
                if "type" in obj and "alert_type" not in obj:
                    obj["alert_type"] = obj.pop("type")
            return super().model_validate(obj, **kwargs)
        
        def model_dump(self, **kwargs):
            data = super().model_dump(**kwargs)
            if "alert_type" in data:
                data["type"] = data.pop("alert_type")
            return data
        
        def dict(self, **kwargs):
            return self.model_dump(**kwargs)
    
    print("✓ Alert class created successfully")
    
    alert = Alert(
        device_id="sensor001",
        level="level2",
        alert_type="fire",
        message="High temperature detected",
        value=85.0,
        threshold=60.0
    )
    print(f"  Alert: device_id={alert.device_id}, type={alert.type}, level={alert.level}")
    print(f"  dict() output: {alert.dict()}")
    
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()

print("\nAll tests completed!")
