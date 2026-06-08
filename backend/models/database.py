from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime

from backend.config import settings


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.MONGODB_DB]

devices_collection = db["devices"]
sensor_data_collection = db["sensor_data"]
alerts_collection = db["alerts"]
control_commands_collection = db["control_commands"]
operation_logs_collection = db["operation_logs"]
tunnel_route_collection = db["tunnel_route"]
health_scores_collection = db["health_scores"]


def serialize_document(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


def serialize_documents(docs):
    return [serialize_document(doc) for doc in docs]
