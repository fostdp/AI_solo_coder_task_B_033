from typing import Optional
from pydantic import BaseModel, Field

print("Testing Pydantic version...")
import pydantic
print(f"Pydantic version: {pydantic.__version__}")

print("\nTesting simple Pydantic model without Optional...")

class TestModel1(BaseModel):
    data_type: str = "test"

print("TestModel1 created successfully")

class TestModel2(BaseModel):
    data_type: str

print("TestModel2 created successfully")

class TestModel3(BaseModel):
    data_type: Optional[str]

print("TestModel3 created successfully")

print("All tests passed!")
