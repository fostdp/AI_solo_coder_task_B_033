from typing import Optional, Any
from pydantic import BaseModel, Field

print("Testing explicit type specification...")

print("\n1. Using Field with explicit type_ parameter:")
try:
    class Test1(BaseModel):
        data_type = Field(default=None, type_=Optional[str])
    print("✓ OK")
    t = Test1()
    print(f"  data_type = {t.data_type}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n2. Using __annotations__:")
try:
    class Test2(BaseModel):
        data_type = None
        __annotations__ = {"data_type": Optional[str]}
    print("✓ OK")
    t = Test2()
    print(f"  data_type = {t.data_type}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n3. Skipping Schema test (not available in this Pydantic version)")

print("\n4. Using Optional[str] without default, then setting default in __init__:")
try:
    class Test4(BaseModel):
        data_type: Optional[str]
        
        def __init__(self, **data):
            if 'data_type' not in data:
                data['data_type'] = None
            super().__init__(**data)
    print("✓ OK")
    t = Test4()
    print(f"  data_type = {t.data_type}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n5. Using Union[str, None] instead of Optional:")
try:
    from typing import Union
    class Test5(BaseModel):
        data_type: Union[str, None] = None
    print("✓ OK")
    t = Test5()
    print(f"  data_type = {t.data_type}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n6. Using type: ignore comment:")
try:
    class Test6(BaseModel):
        data_type: Optional[str] = None  # type: ignore
    print("✓ OK")
    t = Test6()
    print(f"  data_type = {t.data_type}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n7. Multiple Optional fields with type_ parameter:")
try:
    class Test7(BaseModel):
        device_id: str
        data_type = Field(default=None, type_=Optional[str])
        temperature = Field(default=None, type_=Optional[float])
        humidity = Field(default=None, type_=Optional[float])
    print("✓ OK")
    t = Test7(device_id="test123")
    print(f"  device_id = {t.device_id}")
    print(f"  data_type = {t.data_type}")
    print(f"  temperature = {t.temperature}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\nAll tests completed!")
