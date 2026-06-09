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

structure_alerts_collection = db["structure_alerts"]
fiber_sensor_data_collection = db["fiber_sensor_data"]
inspection_robots_collection = db["inspection_robots"]
inspection_missions_collection = db["inspection_missions"]
robot_positions_collection = db["robot_positions"]
fire_alerts_collection = db["fire_alerts"]
fire_zone_status_collection = db["fire_zone_status"]
assets_collection = db["assets"]
maintenance_records_collection = db["maintenance_records"]
maintenance_plans_collection = db["maintenance_plans"]
life_predictions_collection = db["life_predictions"]
topology_map_collection = db["topology_map"]
robot_path_plans_collection = db["robot_path_plans"]
fire_alert_confirmations_collection = db["fire_alert_confirmations"]
heat_source_analysis_collection = db["heat_source_analysis"]
device_replacement_history_collection = db["device_replacement_history"]
asset_audit_logs_collection = db["asset_audit_logs"]


def serialize_document(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


def serialize_documents(docs):
    return [serialize_document(doc) for doc in docs]
