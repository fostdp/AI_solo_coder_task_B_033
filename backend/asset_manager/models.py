from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel


class ReplacementDetectionResult(BaseModel):
    detected: bool
    reasons: List[str] = []
    property_changes: Dict[str, Dict[str, Any]] = {}


class AssetSyncResult(BaseModel):
    success: bool
    old_device_id: str
    new_device_id: Optional[str] = None
    replacement_record: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AuditLogEntry(BaseModel):
    log_id: str
    device_id: str
    action: str
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    change_reason: Optional[str] = None
    performed_by: str
    timestamp: Optional[str] = None


class ReplacementChainEntry(BaseModel):
    device_id: str
    role: str
    related_device_id: Optional[str] = None
    replacement_time: Optional[str] = None
