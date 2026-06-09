from typing import Optional
from pydantic import BaseModel, Field

print("Testing simple Pydantic model...")

class TestModel1(BaseModel):
    data_type: Optional[str] = None

print("TestModel1 created successfully")

class TestModel2(BaseModel):
    data_type: Optional[str]

print("TestModel2 created successfully")

class TestModel3(BaseModel):
    data_type: Optional[str] = Field(default=None)

print("TestModel3 created successfully")

class TestModel4(BaseModel):
    data_type: Optional[str] = Field(default=None, alias="type")

print("TestModel4 created successfully")

print("All tests passed!")
