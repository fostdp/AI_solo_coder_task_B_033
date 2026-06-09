import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import redis.asyncio as redis
import json
import random

from backend.config import settings
from backend.models.database import (
    assets_collection,
    maintenance_records_collection,
    maintenance_plans_collection,
    life_predictions_collection,
    devices_collection,
    sensor_data_collection,
    alerts_collection,
    device_replacement_history_collection,
    asset_audit_logs_collection
)
from backend.models.schemas import (
    Asset,
    MaintenanceRecord,
    MaintenancePlan,
    RemainingLifePrediction,
    MaintenanceTask,
    DeviceReplacementRecord,
    AssetAuditLog
)

logger = logging.getLogger(__name__)


class LifePredictionModel:
    def predict(self, asset_data: Dict[str, Any], sensor_history: List[Dict[str, Any]]) -> RemainingLifePrediction:
        design_life = asset_data.get("design_life_years", 10.0)
        installation_date = asset_data.get("installation_date", datetime.utcnow())
        if isinstance(installation_date, datetime):
            years_in_service = (datetime.utcnow() - installation_date).total_seconds() / (365 * 24 * 3600)
        else:
            years_in_service = (datetime.utcnow() - installation_date).total_seconds() / (365 * 24 * 3600)

        base_remaining = max(0, design_life - years_in_service)

        risk_factors = []
        life_factor = 1.0
        confidence = 0.7

        if sensor_history:
            temp_values = [s.get("temperature", 25) for s in sensor_history if s.get("temperature")]
            if temp_values:
                avg_temp = sum(temp_values) / len(temp_values)
                if avg_temp > 40:
                    life_factor *= 0.85
                    risk_factors.append("高温环境运行")
                elif avg_temp > 35:
                    life_factor *= 0.92
                    risk_factors.append("偏高温度运行")

            hum_values = [s.get("humidity", 50) for s in sensor_history if s.get("humidity")]
            if hum_values:
                avg_hum = sum(hum_values) / len(hum_values)
                if avg_hum > 85:
                    life_factor *= 0.88
                    risk_factors.append("高湿环境运行")

        maintenance_count = asset_data.get("maintenance_count", 0)
        if years_in_service > 0:
            maintenance_frequency = maintenance_count / years_in_service
            if maintenance_frequency < 2:
                life_factor *= 0.9
                risk_factors.append("维护频次不足")

        failure_count = asset_data.get("failure_count", 0)
        if failure_count > 5:
            life_factor *= 0.85
            risk_factors.append("历史故障多发")
        elif failure_count > 2:
            life_factor *= 0.93
            risk_factors.append("存在故障历史")

        last_maintenance = asset_data.get("last_maintenance_date")
        if last_maintenance:
            if isinstance(last_maintenance, datetime):
                days_since_maintenance = (datetime.utcnow() - last_maintenance).days
            else:
                days_since_maintenance = (datetime.utcnow() - last_maintenance).days

            if days_since_maintenance > 365:
                life_factor *= 0.85
                risk_factors.append("超期未维护")
                confidence -= 0.1
            elif days_since_maintenance > 180:
                life_factor *= 0.95
                risk_factors.append("维护周期临近")

        predicted_life = base_remaining * life_factor

        if predicted_life < 1:
            risk_level = "critical"
            recommendation = "建议立即更换设备，已到达使用寿命末期"
        elif predicted_life < 3:
            risk_level = "high"
            recommendation = "建议列入近期更换计划，缩短维护周期"
        elif predicted_life < 5:
            risk_level = "medium"
            recommendation = "按计划维护，密切监测运行状态"
        else:
            risk_level = "low"
            recommendation = "正常维护即可，运行状态良好"

        return RemainingLifePrediction(
            device_id=asset_data.get("device_id", ""),
            predicted_life_years=round(predicted_life, 1),
            confidence=round(confidence, 2),
            key_factors=risk_factors,
            risk_level=risk_level,
            recommendation=recommendation
        )


class AssetManager:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.life_model = LifePredictionModel()
        self.running = False
        self.asset_snapshots: Dict[str, Dict[str, Any]] = {}
        self.replacement_detection_enabled = settings.ASSET_REPLACEMENT_SERIAL_CHANGE
        self.auto_sync_enabled = settings.ASSET_REPLACEMENT_AUTO_SYNC
        self.audit_log_enabled = settings.ASSET_REPLACEMENT_AUDIT_LOG_ENABLED

    async def connect_redis(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB
        )
        logger.info("Asset Manager connected to Redis")

    async def disconnect_redis(self):
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Asset Manager disconnected from Redis")

    async def create_asset(self, asset: Asset) -> Dict[str, Any]:
        existing = await assets_collection.find_one({"device_id": asset.device_id})
        if existing:
            return {"status": "error", "message": f"Asset {asset.device_id} already exists"}

        result = await assets_collection.insert_one(asset.model_dump(exclude={"id"}))
        return {"status": "success", "asset_id": str(result.inserted_id)}

    async def get_asset(self, device_id: str) -> Optional[Dict[str, Any]]:
        asset = await assets_collection.find_one({"device_id": device_id})
        from backend.models.database import serialize_document
        return serialize_document(asset)

    async def get_all_assets(self, chamber: Optional[str] = None,
                             asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        query = {}
        if chamber:
            query["chamber"] = chamber
        if asset_type:
            query["type"] = asset_type

        assets = await assets_collection.find(query).to_list(length=1000)
        from backend.models.database import serialize_documents
        return serialize_documents(assets)

    async def update_asset(self, device_id: str, update_data: Dict[str, Any]) -> bool:
        old_asset = await assets_collection.find_one({"device_id": device_id})
        if not old_asset:
            return False
        
        if self.audit_log_enabled:
            for field_name, new_value in update_data.items():
                old_value = old_asset.get(field_name)
                if old_value != new_value:
                    await self._create_audit_log(
                        device_id=device_id,
                        action="update",
                        field_name=field_name,
                        old_value=old_value,
                        new_value=new_value,
                        change_reason="asset_update",
                        performed_by="system"
                    )
        
        if self.replacement_detection_enabled:
            replacement_detected = await self._detect_device_replacement(old_asset, update_data)
            if replacement_detected:
                logger.info(f"Device replacement detected for {device_id}")
                if self.auto_sync_enabled:
                    await self._sync_asset_ledger(device_id, old_asset, update_data)
        
        result = await assets_collection.update_one(
            {"device_id": device_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def record_maintenance(self, record: MaintenanceRecord) -> Dict[str, Any]:
        result = await maintenance_records_collection.insert_one(record.model_dump(exclude={"id"}))

        await assets_collection.update_one(
            {"device_id": record.device_id},
            {
                "$set": {"last_maintenance_date": record.end_time or datetime.utcnow()},
                "$inc": {"maintenance_count": 1}
            }
        )

        return {"status": "success", "record_id": str(result.inserted_id)}

    async def get_maintenance_history(self, device_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        records = await maintenance_records_collection.find(
            {"device_id": device_id}
        ).sort("start_time", -1).limit(limit).to_list(length=limit)

        from backend.models.database import serialize_documents
        return serialize_documents(records)

    async def predict_remaining_life(self, device_id: str) -> Optional[RemainingLifePrediction]:
        asset = await assets_collection.find_one({"device_id": device_id})
        if not asset:
            return None

        sensor_history = await sensor_data_collection.find({
            "device_id": device_id,
            "timestamp": {"$gte": datetime.utcnow() - timedelta(days=30)}
        }).sort("timestamp", -1).limit(1000).to_list(length=1000)

        prediction = self.life_model.predict(asset, sensor_history)

        await life_predictions_collection.insert_one(prediction.dict())

        return prediction

    async def batch_predict_life(self) -> List[RemainingLifePrediction]:
        assets = await assets_collection.find().to_list(length=1000)
        predictions = []

        for asset in assets:
            try:
                prediction = await self.predict_remaining_life(asset["device_id"])
                if prediction:
                    predictions.append(prediction)
            except Exception as e:
                logger.error(f"Error predicting life for {asset['device_id']}: {e}")

        return predictions

    async def calculate_maintenance_priority(self, device_id: str) -> Tuple[str, int, str]:
        asset = await assets_collection.find_one({"device_id": device_id})
        if not asset:
            return ("medium", 50, "无资产数据")

        prediction = await life_predictions_collection.find_one(
            {"device_id": device_id},
            sort=[("timestamp", -1)]
        )

        priority_score = 50
        priority_factors = []

        if prediction:
            risk_level = prediction.get("risk_level", "low")
            if risk_level == "critical":
                priority_score += 40
                priority_factors.append("使用寿命临界")
            elif risk_level == "high":
                priority_score += 25
                priority_factors.append("使用寿命临近")
            elif risk_level == "medium":
                priority_score += 10
                priority_factors.append("使用寿命中期")

        last_maintenance = asset.get("last_maintenance_date")
        if last_maintenance:
            if isinstance(last_maintenance, datetime):
                days_since = (datetime.utcnow() - last_maintenance).days
            else:
                days_since = (datetime.utcnow() - last_maintenance).days

            maintenance_interval = 90
            if days_since > maintenance_interval * 2:
                priority_score += 30
                priority_factors.append("超期未维护")
            elif days_since > maintenance_interval * 1.5:
                priority_score += 15
                priority_factors.append("维护周期临近")
            elif days_since > maintenance_interval:
                priority_score += 5
                priority_factors.append("到达维护周期")

        failure_count = asset.get("failure_count", 0)
        if failure_count >= 3:
            priority_score += 20
            priority_factors.append("故障多发")
        elif failure_count >= 1:
            priority_score += 10
            priority_factors.append("有故障历史")

        recent_alerts = await alerts_collection.count_documents({
            "device_id": device_id,
            "timestamp": {"$gte": datetime.utcnow() - timedelta(days=30)}
        })
        if recent_alerts >= 3:
            priority_score += 15
            priority_factors.append("告警多发")
        elif recent_alerts >= 1:
            priority_score += 5
            priority_factors.append("有告警历史")

        device = await devices_collection.find_one({"device_id": device_id})
        if device and device.get("status") == "fault":
            priority_score += 25
            priority_factors.append("当前故障")
        elif device and device.get("status") == "warning":
            priority_score += 10
            priority_factors.append("预警状态")

        priority_score = min(100, max(0, priority_score))

        if priority_score >= 80:
            priority = "critical"
        elif priority_score >= 60:
            priority = "high"
        elif priority_score >= 40:
            priority = "medium"
        else:
            priority = "low"

        reason = "、".join(priority_factors) if priority_factors else "运行正常"
        return (priority, priority_score, reason)

    async def generate_monthly_maintenance_plan(self, year: int, month: int) -> MaintenancePlan:
        assets = await assets_collection.find().to_list(length=1000)

        tasks = []
        for asset in assets:
            try:
                device_id = asset["device_id"]
                priority, priority_score, reason = await self.calculate_maintenance_priority(device_id)

                device = await devices_collection.find_one({"device_id": device_id})

                task_type = self._determine_maintenance_type(asset, priority)

                due_date = datetime(year, month, 1)
                if priority == "critical":
                    due_date += timedelta(days=random.randint(1, 5))
                elif priority == "high":
                    due_date += timedelta(days=random.randint(3, 10))
                elif priority == "medium":
                    due_date += timedelta(days=random.randint(10, 20))
                else:
                    due_date += timedelta(days=random.randint(20, 28))

                parts_needed = self._determine_parts_needed(asset.get("type"), task_type)

                task = MaintenanceTask(
                    task_id=f"task_{datetime.utcnow().strftime('%Y%m%d')}_{device_id}",
                    device_id=device_id,
                    device_name=asset.get("name", device_id),
                    task_type=task_type,
                    priority=priority,
                    description=f"{task_type} - {reason}",
                    due_date=due_date,
                    estimated_duration_hours=self._estimate_duration(asset.get("type"), task_type),
                    parts_needed=parts_needed,
                    risk_level=priority,
                    reason=reason
                )
                tasks.append((priority_score, task))

            except Exception as e:
                logger.error(f"Error generating task for {asset.get('device_id')}: {e}")

        tasks.sort(key=lambda x: -x[0])

        priority_distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        estimated_cost = 0.0

        plan_tasks = []
        for score, task in tasks:
            task_dict = task.dict()
            task_dict["priority_score"] = score
            plan_tasks.append(task_dict)

            if task.priority in priority_distribution:
                priority_distribution[task.priority] += 1

            estimated_cost += self._estimate_cost(asset, task.task_type)

        plan = MaintenancePlan(
            plan_id=f"plan_{year}_{month:02d}",
            month=f"{year}-{month:02d}",
            year=year,
            tasks=plan_tasks,
            total_tasks=len(plan_tasks),
            priority_distribution=priority_distribution,
            estimated_cost=round(estimated_cost, 2),
            status="generated"
        )

        await maintenance_plans_collection.insert_one(plan.model_dump(exclude={"id"}))

        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:maintenance:plan_generated",
                json.dumps({
                    "plan_id": plan.plan_id,
                    "total_tasks": plan.total_tasks,
                    "priority_distribution": priority_distribution,
                    "estimated_cost": plan.estimated_cost
                })
            )

        return plan

    def _determine_maintenance_type(self, asset: Dict[str, Any], priority: str) -> str:
        asset_type = asset.get("type", "")
        if priority == "critical":
            return "紧急检修"
        elif priority == "high":
            if "sensor" in asset_type or "光纤" in asset.get("name", ""):
                return "校准检测"
            else:
                return "全面检修"
        elif priority == "medium":
            return "定期维护"
        else:
            return "常规巡检"

    def _determine_parts_needed(self, asset_type: str, task_type: str) -> List[str]:
        parts_map = {
            "env_sensor": ["电池", "密封圈", "传感器探头"],
            "fan": ["轴承", "皮带", "润滑油", "过滤网"],
            "pump": ["机械密封", "轴承", "O型圈"],
            "fiber_sensor": ["光纤跳线", "清洁工具"],
            "smoke_sensor": ["电池", "防尘罩"],
            "manhole": ["密封圈", "固定螺栓"],
            "fire_door": ["密封条", "门锁机构"],
            "fire_extinguisher": ["灭火剂", "压力表"],
            "inspection_robot": ["电池组", "滚轮", "清洁刷"]
        }

        parts = parts_map.get(asset_type, [])
        if task_type in ["全面检修", "紧急检修"]:
            return parts
        elif task_type == "定期维护":
            return parts[:2] if len(parts) > 2 else parts
        else:
            return []

    def _estimate_duration(self, asset_type: str, task_type: str) -> float:
        duration_map = {
            "紧急检修": 4.0,
            "全面检修": 2.0,
            "校准检测": 1.5,
            "定期维护": 1.0,
            "常规巡检": 0.5
        }
        base = duration_map.get(task_type, 1.0)

        if asset_type in ["fan", "pump"]:
            base *= 1.5

        return base

    def _estimate_cost(self, asset: Dict[str, Any], task_type: str) -> float:
        cost_map = {
            "紧急检修": 2000,
            "全面检修": 1000,
            "校准检测": 500,
            "定期维护": 300,
            "常规巡检": 100
        }
        base = cost_map.get(task_type, 200)

        if asset.get("type") in ["fan", "pump"]:
            base *= 2

        return base

    async def get_maintenance_plans(self, year: Optional[int] = None,
                                    month: Optional[int] = None) -> List[Dict[str, Any]]:
        query = {}
        if year:
            query["year"] = year
        if month:
            query["month"] = f"{year}-{month:02d}" if year else {"$regex": f"-{month:02d}$"}

        plans = await maintenance_plans_collection.find(query).sort(
            "generated_at", -1
        ).to_list(length=50)

        from backend.models.database import serialize_documents
        return serialize_documents(plans)

    async def get_maintenance_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        plan = await maintenance_plans_collection.find_one({"plan_id": plan_id})
        from backend.models.database import serialize_document
        return serialize_document(plan)

    async def start_life_prediction_service(self):
        self.running = True
        logger.info("Life Prediction Service started")

        while self.running:
            try:
                await asyncio.sleep(24 * 3600)
                logger.info("Starting daily life prediction...")
                predictions = await self.batch_predict_life()
                logger.info(f"Completed life prediction for {len(predictions)} assets")
            except Exception as e:
                logger.error(f"Life prediction service error: {e}")
                await asyncio.sleep(3600)

        logger.info("Life Prediction Service stopped")

    async def start_monthly_plan_generator(self):
        self.running = True
        logger.info("Monthly Plan Generator started")

        while self.running:
            try:
                now = datetime.utcnow()
                if now.day == 25 and now.hour == 2:
                    next_month = now + timedelta(days=7)
                    year = next_month.year
                    month = next_month.month

                    logger.info(f"Generating maintenance plan for {year}-{month:02d}...")
                    plan = await self.generate_monthly_maintenance_plan(year, month)
                    logger.info(f"Generated plan {plan.plan_id} with {plan.total_tasks} tasks")

                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"Monthly plan generator error: {e}")
                await asyncio.sleep(3600)

        logger.info("Monthly Plan Generator stopped")

    async def _detect_device_replacement(
        self,
        old_asset: Dict[str, Any],
        update_data: Dict[str, Any]
    ) -> bool:
        detection_reasons = []
        
        if "serial_number" in update_data and settings.ASSET_REPLACEMENT_SERIAL_CHANGE:
            old_serial = old_asset.get("serial_number", "")
            new_serial = update_data["serial_number"]
            if old_serial and new_serial and old_serial != new_serial:
                detection_reasons.append(f"序列号变更: {old_serial} -> {new_serial}")
        
        if "device_id" in update_data:
            old_device_id = old_asset.get("device_id", "")
            new_device_id = update_data["device_id"]
            if old_device_id and new_device_id and old_device_id != new_device_id:
                detection_reasons.append(f"设备ID变更: {old_device_id} -> {new_device_id}")
        
        if "installation_date" in update_data:
            old_install_date = old_asset.get("installation_date")
            new_install_date = update_data["installation_date"]
            if old_install_date and new_install_date:
                if isinstance(old_install_date, datetime):
                    old_dt = old_install_date
                else:
                    old_dt = datetime.fromisoformat(str(old_install_date).replace('Z', '+00:00'))
                if isinstance(new_install_date, datetime):
                    new_dt = new_install_date
                else:
                    new_dt = datetime.fromisoformat(str(new_install_date).replace('Z', '+00:00'))
                days_diff = abs((new_dt - old_dt).days)
                if days_diff > settings.ASSET_REPLACEMENT_INSTALL_DATE_THRESHOLD_DAYS and new_dt > old_dt:
                    detection_reasons.append(f"安装日期异常变更: {days_diff}天")
        
        property_change_count = 0
        key_properties = ["manufacturer", "model", "specifications"]
        for prop in key_properties:
            if prop in update_data:
                old_val = str(old_asset.get(prop, ""))
                new_val = str(update_data[prop])
                if old_val and new_val and old_val != new_val:
                    property_change_count += 1
        
        if property_change_count >= len(key_properties) * settings.ASSET_REPLACEMENT_PROPERTY_CHANGE_THRESHOLD:
            detection_reasons.append(f"关键属性突变: {property_change_count}项变更")
        
        if detection_reasons:
            logger.info(f"Device replacement detected for {old_asset.get('device_id')}: {', '.join(detection_reasons)}")
            return True
        
        return False

    async def _sync_asset_ledger(
        self,
        device_id: str,
        old_asset: Dict[str, Any],
        update_data: Dict[str, Any],
        replacement_reason: str = "auto_detected"
    ) -> Optional[DeviceReplacementRecord]:
        try:
            old_serial = old_asset.get("serial_number", "")
            new_serial = update_data.get("serial_number", old_serial)
            new_device_id = update_data.get("device_id", device_id)
            
            new_asset_data = dict(old_asset)
            new_asset_data.update(update_data)
            new_asset_data["device_id"] = new_device_id
            new_asset_data["status"] = "active"
            new_asset_data["installation_date"] = datetime.utcnow()
            new_asset_data["maintenance_count"] = 0
            new_asset_data["failure_count"] = 0
            new_asset_data["last_maintenance_date"] = None
            
            if "_id" in new_asset_data:
                del new_asset_data["_id"]
            
            new_asset = Asset(**new_asset_data)
            await assets_collection.insert_one(new_asset.model_dump(exclude={"id"}))
            
            old_status_update = {
                "status": "decommissioned",
                "decommissioned_date": datetime.utcnow(),
                "replaced_by": new_device_id
            }
            await assets_collection.update_one(
                {"device_id": device_id},
                {"$set": old_status_update}
            )
            
            if self.audit_log_enabled:
                await self._create_audit_log(
                    device_id=device_id,
                    action="decommission",
                    field_name="status",
                    old_value=old_asset.get("status", "active"),
                    new_value="decommissioned",
                    change_reason=f"设备更换，新设备: {new_device_id}",
                    performed_by="system"
                )
                await self._create_audit_log(
                    device_id=new_device_id,
                    action="create",
                    field_name=None,
                    old_value=None,
                    new_value=new_asset_data,
                    change_reason=f"设备更换，替换旧设备: {device_id}",
                    performed_by="system"
                )
            
            property_changes = {}
            for key in update_data:
                old_val = old_asset.get(key)
                new_val = update_data[key]
                if old_val != new_val:
                    property_changes[key] = {"old": old_val, "new": new_val}
            
            record_id = f"replace_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{device_id}"
            replacement_record = DeviceReplacementRecord(
                record_id=record_id,
                old_device_id=device_id,
                new_device_id=new_device_id,
                old_serial_number=old_serial,
                new_serial_number=new_serial,
                replacement_reason=replacement_reason,
                property_changes=property_changes
            )
            
            await device_replacement_history_collection.insert_one(replacement_record.model_dump(exclude={"id"}))
            
            if self.redis_client:
                await self.redis_client.publish(
                    "tunnel:asset:replacement",
                    json.dumps({
                        "record_id": record_id,
                        "old_device_id": device_id,
                        "new_device_id": new_device_id,
                        "replacement_reason": replacement_reason,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                )
            
            logger.info(f"Asset ledger synced: {device_id} replaced by {new_device_id}")
            return replacement_record
            
        except Exception as e:
            logger.error(f"Error syncing asset ledger for {device_id}: {e}")
            return None

    async def _create_audit_log(
        self,
        device_id: str,
        action: str,
        field_name: Optional[str],
        old_value: Optional[Any],
        new_value: Optional[Any],
        change_reason: Optional[str],
        performed_by: str
    ) -> AssetAuditLog:
        log_id = f"audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{device_id}"
        
        audit_log = AssetAuditLog(
            log_id=log_id,
            device_id=device_id,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            change_reason=change_reason,
            performed_by=performed_by
        )
        
        try:
            await asset_audit_logs_collection.insert_one(audit_log.model_dump(exclude={"id"}))
        except Exception as e:
            logger.error(f"Error creating audit log for {device_id}: {e}")
        
        return audit_log

    async def get_device_replacement_history(
        self,
        device_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        query = {}
        if device_id:
            query["$or"] = [
                {"old_device_id": device_id},
                {"new_device_id": device_id}
            ]
        
        records = await device_replacement_history_collection.find(
            query
        ).sort("replacement_time", -1).limit(limit).to_list(length=limit)
        
        from backend.models.database import serialize_documents
        return serialize_documents(records)

    async def get_asset_audit_logs(
        self,
        device_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        query = {}
        if device_id:
            query["device_id"] = device_id
        if action:
            query["action"] = action
        
        logs = await asset_audit_logs_collection.find(
            query
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        from backend.models.database import serialize_documents
        return serialize_documents(logs)

    async def manual_device_replacement(
        self,
        old_device_id: str,
        new_asset_data: Dict[str, Any],
        replacement_reason: str,
        performed_by: str
    ) -> Tuple[bool, Optional[DeviceReplacementRecord]]:
        old_asset = await assets_collection.find_one({"device_id": old_device_id})
        if not old_asset:
            return False, None
        
        new_serial = new_asset_data.get("serial_number", "")
        if not new_serial:
            return False, None
        
        update_data = new_asset_data
        
        if self.audit_log_enabled:
            await self._create_audit_log(
                device_id=old_device_id,
                action="manual_replacement_start",
                field_name=None,
                old_value=old_asset,
                new_value=new_asset_data,
                change_reason=replacement_reason,
                performed_by=performed_by
            )
        
        replacement_record = await self._sync_asset_ledger(
            old_device_id,
            old_asset,
            update_data,
            replacement_reason
        )
        
        if replacement_record:
            await device_replacement_history_collection.update_one(
                {"record_id": replacement_record.record_id},
                {"$set": {"performed_by": performed_by}}
            )
            return True, replacement_record
        
        return False, None

    async def scan_for_device_replacements(self) -> List[str]:
        replaced_devices = []
        assets = await assets_collection.find({"status": "active"}).to_list(length=1000)
        
        for asset in assets:
            device_id = asset.get("device_id")
            if not device_id:
                continue
            
            try:
                device = await devices_collection.find_one({"device_id": device_id})
                if device:
                    device_serial = device.get("properties", {}).get("serial_number", "")
                    asset_serial = asset.get("serial_number", "")
                    
                    if device_serial and asset_serial and device_serial != asset_serial:
                        logger.info(f"Serial mismatch detected for {device_id}: asset={asset_serial}, device={device_serial}")
                        
                        update_data = {
                            "serial_number": device_serial,
                            "manufacturer": device.get("properties", {}).get("manufacturer", asset.get("manufacturer", "")),
                            "model": device.get("properties", {}).get("model", asset.get("model", ""))
                        }
                        
                        replaced = await self._detect_device_replacement(asset, update_data)
                        if replaced and self.auto_sync_enabled:
                            await self._sync_asset_ledger(
                                device_id, asset, update_data, "serial_mismatch_scan"
                            )
                            replaced_devices.append(device_id)
            
            except Exception as e:
                logger.error(f"Error scanning {device_id} for replacement: {e}")
                continue
        
        logger.info(f"Device replacement scan completed: {len(replaced_devices)} replacements found")
        return replaced_devices

    async def get_replacement_chain(self, device_id: str) -> List[Dict[str, Any]]:
        chain = []
        visited = set()
        
        current_id = device_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            record = await device_replacement_history_collection.find_one({
                "new_device_id": current_id
            })
            if not record:
                break
            chain.insert(0, {
                "device_id": record["old_device_id"],
                "role": "predecessor",
                "replaced_by": record["new_device_id"],
                "replacement_time": record.get("replacement_time")
            })
            current_id = record["old_device_id"]
        
        current_id = device_id
        visited_successor = set()
        while current_id and current_id not in visited_successor:
            visited_successor.add(current_id)
            record = await device_replacement_history_collection.find_one({
                "old_device_id": current_id
            })
            if not record:
                break
            chain.append({
                "device_id": record["new_device_id"],
                "role": "successor",
                "replaced": record["old_device_id"],
                "replacement_time": record.get("replacement_time")
            })
            current_id = record["new_device_id"]
        
        return chain

    async def start_replacement_scan_service(self):
        self.running = True
        logger.info("Device Replacement Scan Service started")

        while self.running:
            try:
                await asyncio.sleep(24 * 3600)
                logger.info("Starting daily device replacement scan...")
                replacements = await self.scan_for_device_replacements()
                logger.info(f"Completed device replacement scan: {len(replacements)} replacements found")
            except Exception as e:
                logger.error(f"Device replacement scan service error: {e}")
                await asyncio.sleep(3600)

        logger.info("Device Replacement Scan Service stopped")


asset_manager = AssetManager()
