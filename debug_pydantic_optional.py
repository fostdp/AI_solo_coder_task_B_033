from typing import Optional
from pydantic import BaseModel, Field

print("Testing Optional with and without default None...")

print("\n1. Optional[str] without default:")
try:
    class Test1(BaseModel):
        data_type: Optional[str]
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n2. Optional[str] with default None:")
try:
    class Test2(BaseModel):
        data_type: Optional[str] = None
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n3. Optional[str] with default empty string:")
try:
    class Test3(BaseModel):
        data_type: Optional[str] = ""
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n4. Optional[str] with Field(default=None):")
try:
    class Test4(BaseModel):
        data_type: Optional[str] = Field(default=None)
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n5. Optional[str] with Field(default=None, description='test'):")
try:
    class Test5(BaseModel):
        data_type: Optional[str] = Field(default=None, description="test")
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n6. str with default None:")
try:
    class Test6(BaseModel):
        data_type: str = None
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n7. Optional[float] with default None:")
try:
    class Test7(BaseModel):
        temperature: Optional[float] = None
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n8. Optional[str] with default None, but different field name:")
try:
    class Test8(BaseModel):
        my_field: Optional[str] = None
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n9. Two fields, first is Optional[str] = None:")
try:
    class Test9(BaseModel):
        data_type: Optional[str] = None
        temperature: Optional[float] = None
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\n10. Two fields, first is str, second is Optional[str] = None:")
try:
    class Test10(BaseModel):
        device_id: str
        data_type: Optional[str] = None
    print("✓ OK")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\nAll tests completed!")
