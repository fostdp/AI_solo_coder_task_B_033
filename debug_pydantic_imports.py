print("Testing imports from schemas module...")

try:
    from typing import Optional, Dict, Any, List
    print("✓ typing imports OK")
except Exception as e:
    print(f"✗ typing imports failed: {e}")

try:
    from datetime import datetime
    print("✓ datetime imports OK")
except Exception as e:
    print(f"✗ datetime imports failed: {e}")

try:
    from pydantic import BaseModel, Field, validator
    print("✓ pydantic imports OK")
except Exception as e:
    print(f"✗ pydantic imports failed: {e}")

try:
    from enum import Enum
    print("✓ enum imports OK")
except Exception as e:
    print(f"✗ enum imports failed: {e}")

try:
    from bson import ObjectId
    print("✓ bson imports OK")
except Exception as e:
    print(f"✗ bson imports failed: {e}")

try:
    from backend.models.database import PyObjectId
    print("✓ PyObjectId imports OK")
except Exception as e:
    print(f"✗ PyObjectId imports failed: {e}")

print("\nTesting simple model with same imports...")

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class TestModel(BaseModel):
    device_id: str
    data_type: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    temperature: Optional[float] = None

print("✓ TestModel created successfully")

print("\nNow testing with Location class first...")

from typing import List

class Location(BaseModel):
    geo_type: str = Field(default="Point", description="GeoJSON type")
    coordinates: List[float]

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

print("✓ Location created successfully")

class SensorData(BaseModel):
    device_id: str
    data_type: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    temperature: Optional[float] = None
    location: Optional[Location] = None

    class Config:
        arbitrary_types_allowed = True

print("✓ SensorData created successfully")

print("\nAll tests passed!")
